"""Pano sunucusu: yalnızca 127.0.0.1, her açılışta rastgele anahtar, Host denetimi.

/            -> arayüz (anahtar ?t= ile gelmeli)
/static/*    -> css/js
/api/state   -> pano durumu (JSON)
/api/agenda  -> POST takvim/görev ekle-sil-bitir (kimlikle)
/api/conv    -> GET ?q= konuşma günlüğü/arama, POST sil / süre ayarı
/api/cmd     -> POST {"id": "..."} ya da {"say": "metin"}: Jarvis'e komut gönderir
Onay kapıları aynen geçerli: tehlikeli işlemler panodan da 'evet' denmeden yapılmaz.
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import convlog
import ui_state
from skills import _store, agenda

from . import state as st

STATIC = Path(__file__).with_name("static")
MAX_BODY = 2048
MAX_SAY = 300

# Hızlı komut düğmeleri: kimlik -> ("say", Jarvis'e söylenecek cümle) | ("act", eylem adı)
COMMANDS = {
    "brief": ("say", "günün özeti"),
    "tasks": ("say", "görevlerim neler"),
    "today": ("say", "bugün ne yapıyorum"),
    "system": ("say", "sistem durumu"),
    "battery": ("say", "pil kaç"),
    "weather": ("say", "hava nasıl"),
    "yes": ("say", "evet"),
    "no": ("say", "vazgeç"),
    "stop": ("act", "stop"),
    "mute": ("act", "mute"),
    "focus": ("act", "focus"),
    "talk": ("act", "talk"),
    "chatvoice": ("act", "chatvoice"),
    "quit": ("act", "quit"),
}


class Dashboard:
    def __init__(self, ctx, submit, port: int | None = None, quit=None):
        """ctx: .brain taşıyan nesne; submit(text): komutu Jarvis'in sırasına koyar."""
        self.ctx, self.submit, self.quit = ctx, submit, quit
        self.token = secrets.token_urlsafe(16)
        self.httpd = None
        want = port or int(os.environ.get("JARVIS_DASH_PORT", "8765"))
        for p in range(want, want + 20):
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", p), self._handler())
                break
            except OSError:
                continue
        if not self.httpd:
            raise RuntimeError("Pano için boş port bulunamadı")
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self) -> str:
        st.SAMPLER.is_alive() or st.SAMPLER.start()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        _store.save("dashboard.json", {"url": self.url})
        return self.url

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()

    # ------------------------------------------------------------ komutlar
    def run_command(self, cid: str = "", say: str = "", chat: bool = False, theme: str = "") -> dict:
        if theme:
            return {"ok": ui_state.set_theme(theme)}
        if say:
            say = " ".join(say.split())[:MAX_SAY]
            st.feed("KOMUT", f"Panodan: {say}")
            if chat and not ui_state.chat_voice():
                self.submit(say, silent=True)  # Yazışma sekmesi, sesli cevap kapalı: yalnızca yazıyla cevap
            else:
                self.submit(say)
            return {"ok": True}
        item = COMMANDS.get(cid)
        if not item:
            return {"ok": False, "error": "bilinmeyen komut"}
        kind, val = item
        if kind == "say":
            st.feed("KOMUT", f"Panodan: {val}")
            self.submit(val)
        elif val == "stop":
            ui_state.request_stop()
        elif val == "mute":
            ui_state.set_muted(not ui_state.is_muted())
        elif val == "focus":
            ui_state.set_focus(not ui_state.is_focus())
        elif val == "quit":
            if not self.quit:
                return {"ok": False, "error": "kapatma bağlı değil"}
            st.feed("UYARI", "Jarvis kapatılıyor…")
            self.quit()
        elif val == "chatvoice":
            ui_state.set_chat_voice(not ui_state.chat_voice())
        elif val == "talk":
            ui_state.request_listen()
        return {"ok": True}

    # ------------------------------------------------------------ takvim/görev düğmeleri (kimlikle, onay kapısı gerekmez:
    # kullanıcı bunu kendi elleriyle pano üzerinde yapıyor; model araya girmiyor)
    def agenda_op(self, d: dict) -> dict:
        op = str(d.get("op", ""))
        title = " ".join(str(d.get("title", "")).split())[:120]
        try:
            if op == "add_task":
                msg = agenda.add_task(title, str(d.get("due", ""))[:10], str(d.get("priority", "orta")))
            elif op == "add_event":
                msg = agenda.add_event(title, str(d.get("date", ""))[:10], str(d.get("time", ""))[:5])
            elif op == "done_task":
                msg = "Görev bitti olarak işaretlendi." if agenda.done_task_id(int(d.get("id", 0))) else "Hata: görev bulunamadı."
            elif op == "delete_task":
                msg = "Görev silindi." if agenda.delete_task_id(int(d.get("id", 0))) else "Hata: görev bulunamadı."
            elif op == "cancel_event":
                msg = "Etkinlik silindi." if agenda.cancel_event_id(int(d.get("id", 0))) else "Hata: etkinlik bulunamadı."
            else:
                return {"ok": False, "msg": "Bilinmeyen işlem."}
        except (TypeError, ValueError):
            return {"ok": False, "msg": "Hata: geçersiz değer."}
        ok = not msg.startswith(("Hata", "Ne zaman", "Bu saat", "Görevin ne", "Etkinliğin ne"))
        if ok and op.startswith("add"):
            st.feed("GÖREV", f"Panodan eklendi: {title}")
        return {"ok": ok, "msg": msg}

    def conv_op(self, d: dict) -> dict:
        op = str(d.get("op", ""))
        try:
            if op == "delete":
                return {"ok": convlog.delete(int(d.get("id", 0)))}
            if op == "delete_range":
                return {"ok": True, "n": convlog.delete_between(float(d.get("from", 0)), float(d.get("to", 0)))}
            if op == "delete_day":
                return {"ok": True, "n": convlog.delete_day(str(d.get("day", ""))[:10])}
            if op == "clear":
                return {"ok": True, "n": convlog.clear()}
            if op == "retention":
                return {"ok": True, "days": convlog.set_retention(int(d.get("days", 30)))}
        except (TypeError, ValueError):
            pass
        return {"ok": False}

    def conv_list(self, q: str) -> dict:
        items = convlog.query(q[:100], limit=400)
        return {"items": [{"id": i["id"], "ts": i["ts"], "who": i["who"], "text": i["text"]} for i in items],
                "retention": convlog.retention_days(), "total": convlog.count(), "q": q}

    def conv_sessions(self, q: str) -> dict:
        return {"sessions": convlog.sessions(q[:100]), "retention": convlog.retention_days(), "total": convlog.count(), "q": q}

    def conv_range(self, a: float, b: float) -> dict:
        return {"items": [{"id": i["id"], "ts": i["ts"], "who": i["who"], "text": i["text"]} for i in convlog.between(a, min(b, 9e12))]}

    # ------------------------------------------------------------ HTTP
    def _handler(self):
        dash = self

        class H(BaseHTTPRequestHandler):
            server_version = "JarvisPano"

            def log_message(self, *a):  # sessiz
                pass

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").lower()
                return host in (f"127.0.0.1:{dash.port}", f"localhost:{dash.port}")

            def _token_ok(self, given: str) -> bool:
                return hmac.compare_digest(given or "", dash.token)

            def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj):
                self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

            def do_GET(self):  # noqa: N802
                if not self._host_ok():
                    return self._json(403, {"error": "host"})
                path, _, query = self.path.partition("?")
                if path == "/":
                    token = dict(p.split("=", 1) for p in query.split("&") if "=" in p).get("t", "")
                    if not self._token_ok(token):
                        return self._json(403, {"error": "anahtar"})
                    return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path == "/favicon.ico":
                    return self._send(204, b"", "image/x-icon")
                if path.startswith("/static/"):
                    f = (STATIC / path[len("/static/"):]).resolve()
                    if STATIC.resolve() not in f.parents or not f.is_file():
                        return self._json(404, {"error": "yok"})
                    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                    return self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text") or "javascript" in ctype else ""))
                if path in ("/api/conv", "/api/sessions"):
                    if not self._token_ok(self.headers.get("X-Token", "")):
                        return self._json(403, {"error": "anahtar"})
                    from urllib.parse import parse_qs  # noqa: PLC0415
                    qs = parse_qs(query)
                    q = (qs.get("q") or [""])[0]
                    if path == "/api/sessions":
                        return self._json(200, dash.conv_sessions(q))
                    if "from" in qs:
                        try:
                            return self._json(200, dash.conv_range(float(qs["from"][0]), float((qs.get("to") or ["9e12"])[0])))
                        except ValueError:
                            return self._json(400, {"error": "bozuk istek"})
                    return self._json(200, dash.conv_list(q))
                if path == "/api/state":
                    if not self._token_ok(self.headers.get("X-Token", "")):
                        return self._json(403, {"error": "anahtar"})
                    return self._json(200, st.build_state(dash.ctx))
                return self._json(404, {"error": "yok"})

            def do_POST(self):  # noqa: N802
                if not self._host_ok() or not self._token_ok(self.headers.get("X-Token", "")):
                    return self._json(403, {"error": "yasak"})
                if self.path not in ("/api/cmd", "/api/agenda", "/api/conv"):
                    return self._json(404, {"error": "yok"})
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > MAX_BODY:
                        return self._json(413, {"error": "büyük"})
                    data = json.loads(self.rfile.read(n) or b"{}")
                    if not isinstance(data, dict):
                        raise ValueError
                except (ValueError, OSError):
                    return self._json(400, {"error": "bozuk istek"})
                if self.path == "/api/agenda":
                    return self._json(200, dash.agenda_op(data))
                if self.path == "/api/conv":
                    return self._json(200, dash.conv_op(data))
                return self._json(200, dash.run_command(str(data.get("id", "")), str(data.get("say", "")), bool(data.get("chat")), str(data.get("theme", ""))))

        return H
