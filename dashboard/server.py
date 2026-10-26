"""Pano sunucusu: yalnızca 127.0.0.1, her açılışta rastgele anahtar, Host denetimi.

/            -> arayüz (anahtar ?t= ile gelmeli)
/static/*    -> css/js
/api/state   -> pano durumu (JSON)
/api/agenda  -> POST takvim/görev ekle-sil-bitir (kimlikle)
/api/conv    -> GET ?q= konuşma günlüğü/arama, POST sil / süre ayarı
/api/cmd     -> POST {"id": "..."} ya da {"say": "metin"}: Jarvis'e komut gönderir
/api/island  -> GET üst kenar adası için hafif durum; POST /api/island/answer {"answer": "yes"|"no", "id"}: bekleyen
                onaya Evet/Hayır (yalnızca gösterilen soru hâlâ bekliyorsa; sesli "evet/hayır" ile aynı yoldan geçer)
Onay kapıları aynen geçerli: tehlikeli işlemler panodan da 'evet' denmeden yapılmaz.

Telefon (uzak) kapsamı: /m sayfası ve /api/m/* uçları. Yalnızca remote.py'deki ayrı kalıcı anahtarla ve
yalnızca tailnet Host adıyla açılır; yukarıdaki yerel uçlar uzak Host'tan ASLA erişilemez.
/api/m/state    -> GET  telefon özeti (durum, sistem, ajanda, son konuşma)
/api/m/chat     -> POST {"text"}: yazışma (Telegram ile aynı kısıtlı kip)
/api/m/voice    -> POST ham ses: bilgisayardaki Whisper ile yazıya çevirir
/api/m/cmd      -> POST {"id"}: kısıtlı hızlı komutlar
/api/m/agenda   -> POST görev/takvim işlemleri
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core import convlog
from connect import remote
from desktop import ui_state
from skills import _store, agenda

from . import state as st

STATIC = Path(__file__).with_name("static")
ASSETS = {"cekirdek.svg": Path(__file__).resolve().parent.parent / "assets" / "cekirdek.svg"}  # /static/ altından sunulan proje varlıkları
MAX_BODY = 2048
MAX_SAY = 300
MAX_CHAT = 600
MAX_AUDIO = 4 * 1024 * 1024  # ~ bir iki dakikalık opus/aac kaydı
REMOTE_STATIC = {"m.css", "m.js", "m-icon-192.png", "m-icon-512.png"}
M_CSP = ("default-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; "
         "style-src 'self'; script-src 'self'; manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

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
    "traytoggle": ("act", "traytoggle"),
    "cloudtoggle": ("act", "cloudtoggle"),
    "quit": ("act", "quit"),
}


class Dashboard:
    def __init__(self, ctx, submit, port: int | None = None, quit=None, chat=None, transcribe=None):
        """ctx: .brain taşıyan nesne; submit(text): komutu Jarvis'in sırasına koyar.
        chat(text) -> cevap metni (telefon yazışması, bloklar); transcribe(bytes) -> yazı (telefon sesi)."""
        self.ctx, self.submit, self.quit = ctx, submit, quit
        self.chat, self.transcribe = chat, transcribe
        self.limiter = remote.Limiter()
        self._chat_busy = threading.Lock()
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
    def run_command(self, cid: str = "", say: str = "", chat: bool = False, theme: str = "", island: dict | None = None) -> dict:
        if theme:
            return {"ok": ui_state.set_theme(theme)}
        if island is not None:   # Ayarlar > ADA ve tepsi menüsü: {"key": ..., "value": ...}
            return {"ok": isinstance(island, dict) and ui_state.set_island(str(island.get("key", "")), island.get("value"))}
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
        elif val == "traytoggle":
            ui_state.set_close_to_tray(not ui_state.close_to_tray())
        elif val == "cloudtoggle":
            ui_state.set_cloud_enabled(not ui_state.cloud_enabled())
        elif val == "talk":
            ui_state.request_listen()
        return {"ok": True}

    def island_answer(self, answer: str, qid: str) -> dict:
        """Adadaki Evet/Hayır: kullanıcının sesli cevabıyla AYNI yoldan (submit -> brain.reply_stream -> classify) geçer.
        Onay kapısı değişmez; yalnızca ekranda gösterilen soru hâlâ bekliyorsa (aynı id) iletilir."""
        if answer not in ("yes", "no"):
            return {"ok": False, "error": "bozuk cevap"}
        cur = st.island_snapshot(self.ctx)
        if not cur["kind"] or cur["id"] != qid:
            return {"ok": False, "error": "soru güncel değil"}
        word = "evet" if answer == "yes" else "hayır"
        st.feed("KOMUT", f"Adadan: {word}")
        self.submit(word)
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
            elif op == "schedule_delete":   # yalnızca yerel pano (telefonun REMOTE_AGENDA_OPS listesinde yok)
                from core import scheduler  # noqa: PLC0415
                msg = "Zamanlanmış görev silindi." if scheduler.remove(int(d.get("id", 0))) else "Hata: zamanlanmış görev bulunamadı."
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

    # ------------------------------------------------------------ telefon (uzak) kapsamı
    def _prov(self, name: str):
        try:
            return st.PROVIDERS[name](self.ctx)
        except Exception:  # noqa: BLE001  (bir bölüm hatası tüm özeti düşürmesin)
            return None

    def m_state(self) -> dict:
        durum = self._prov("durum") or {}
        sistem = self._prov("sistem") or {}
        model = self._prov("model") or {}
        alt = self._prov("alt") or {}
        active = next((m["name"] for m in model.get("llm", []) if m.get("active")), "")
        hist = []
        try:
            hist = [{"id": i["id"], "who": i["who"], "text": i["text"], "ts": i["ts"]} for i in convlog.recent(40)]
        except Exception:  # noqa: BLE001
            pass
        return {
            "now": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "durum": {k: durum.get(k) for k in ("state", "label", "muted", "focus", "pending")},
            "sistem": {"cpu": sistem.get("cpu"), "cpu_temp": sistem.get("cpu_temp"), "ram": sistem.get("ram"),
                       "disk": sistem.get("disk"), "gpu": sistem.get("gpu")},
            "model": active,
            "ajanda": agenda.snapshot(max_tasks=100),
            "alt": {"online": alt.get("online"), "temp": alt.get("temp"), "city": alt.get("city")},
            "voice": self.transcribe is not None,
            "history": hist,
        }

    def _pending(self) -> bool:
        return bool((self._prov("durum") or {}).get("pending"))

    def m_chat(self, text: str) -> tuple[int, dict]:
        text = " ".join(str(text or "").split())[:MAX_CHAT]
        if not text:
            return 400, {"ok": False, "error": "boş mesaj"}
        if not self.chat:
            return 503, {"ok": False, "error": "yazışma bağlı değil"}
        if not self._chat_busy.acquire(blocking=False):
            return 429, {"ok": False, "error": "Jarvis başka bir isteği yanıtlıyor"}
        try:
            st.feed("KOMUT", f"Telefondan: {text[:80]}")
            try:
                reply = self.chat(text)
            except TimeoutError:
                return 504, {"ok": False, "error": "Jarvis şu an meşgul (bilgisayarda bir iş sürüyor); biraz sonra dene"}
            except Exception as exc:  # noqa: BLE001
                return 500, {"ok": False, "error": f"{type(exc).__name__}"}
            return 200, {"ok": True, "reply": reply, "pending": self._pending()}
        finally:
            self._chat_busy.release()

    def m_voice(self, data: bytes) -> tuple[int, dict]:
        if not self.transcribe:
            return 503, {"ok": False, "error": "Ses tanıma kapalı (Jarvis --text kipinde)"}
        if len(data) < 800:
            return 400, {"ok": False, "error": "kayıt çok kısa"}
        try:
            text = self.transcribe(data)
        except Exception as exc:  # noqa: BLE001
            print(f"[pano] telefon sesi hatası: {type(exc).__name__}: {exc}", flush=True)
            return 500, {"ok": False, "error": f"ses çözülemedi ({type(exc).__name__}: {str(exc)[:100]})"}
        return 200, {"ok": True, "text": text}

    def m_cmd(self, d: dict) -> tuple[int, dict]:
        cid = str(d.get("id", ""))
        if cid in remote.REMOTE_SAY:
            return self.m_chat(remote.REMOTE_SAY[cid])
        if cid in remote.REMOTE_ACT:
            return 200, self.run_command(cid)
        return 400, {"ok": False, "error": "bu komut telefondan kullanılamaz"}

    def m_agenda(self, d: dict) -> dict:
        if str(d.get("op", "")) not in remote.REMOTE_AGENDA_OPS:
            return {"ok": False, "msg": "Bilinmeyen işlem."}
        r = self.agenda_op(d)
        r["ajanda"] = agenda.snapshot(max_tasks=100)
        return r

    # ------------------------------------------------------------ HTTP
    def _handler(self):
        dash = self

        class H(BaseHTTPRequestHandler):
            server_version = "JarvisPano"
            timeout = 30  # yarım kalan/yavaş istek bağlantıyı sonsuza dek tutmasın

            def log_message(self, *a):  # sessiz
                pass

            def _host(self) -> str:
                return (self.headers.get("Host") or "").lower()

            def _host_ok(self) -> bool:
                return self._host() in (f"127.0.0.1:{dash.port}", f"localhost:{dash.port}")

            def _scope(self) -> str:
                """'local' (127.0.0.1 pano), 'remote' (tailnet adı, telefon) ya da '' (reddet)."""
                if self._host_ok():
                    return "local"
                if remote.host_ok(self._host()):
                    return "remote"
                return ""

            def _token_ok(self, given: str) -> bool:
                # bayt karşılaştırması: ASCII dışı başlık TypeError fırlatıp isteği düşürmesin
                return hmac.compare_digest((given or "").encode("utf-8", "replace"), dash.token.encode("utf-8"))

            def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj):
                self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

            # ---- telefon kapsamı: ayrı kalıcı anahtar, kilit, hız sınırı
            def _m_auth(self) -> bool:
                if dash.limiter.locked():
                    self._json(429, {"error": "çok fazla yanlış deneme; bir dakika bekle"})
                    return False
                if not remote.check_token(self.headers.get("X-Token", "")):
                    dash.limiter.fail()
                    self._json(403, {"error": "anahtar"})
                    return False
                dash.limiter.good()
                if not dash.limiter.hit():
                    self._json(429, {"error": "çok sık istek"})
                    return False
                return True

            def _m_static(self, path: str) -> bool:
                """/m ve telefon sayfasının gizli bilgi taşımayan dosyaları (anahtarsız; anahtar yalnızca API'de)."""
                if path in ("/m", "/m/"):
                    return self._send(200, (STATIC / "m.html").read_bytes(), "text/html; charset=utf-8",
                                      {"Content-Security-Policy": M_CSP}) or True
                if path == "/manifest.webmanifest":
                    return self._send(200, (STATIC / "manifest.webmanifest").read_bytes(), "application/manifest+json; charset=utf-8") or True
                if path.startswith("/static/") and path[len("/static/"):] in REMOTE_STATIC:
                    f = STATIC / path[len("/static/"):]
                    if f.is_file():
                        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                        self._send(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text") or "javascript" in ctype else ""))
                        return True
                return False

            def do_GET(self):  # noqa: N802
                scope = self._scope()
                if not scope:
                    return self._json(403, {"error": "host"})
                path, _, query = self.path.partition("?")
                if self._m_static(path):
                    return None
                if path == "/api/m/state":
                    if not self._m_auth():
                        return None
                    return self._json(200, dash.m_state())
                if scope != "local":  # uzak Host yalnızca yukarıdaki telefon uçlarını görür
                    return self._json(404, {"error": "yok"})
                if path == "/":
                    token = dict(p.split("=", 1) for p in query.split("&") if "=" in p).get("t", "")
                    if not self._token_ok(token):
                        return self._json(403, {"error": "anahtar"})
                    return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path == "/favicon.ico":
                    return self._send(204, b"", "image/x-icon")
                if path.startswith("/static/") and path[len("/static/"):] in ASSETS:   # maskot: assets/ tek kaynak (kopya yok)
                    f = ASSETS[path[len("/static/"):]]
                    return self._send(200, f.read_bytes(), "image/svg+xml; charset=utf-8") if f.is_file() else self._json(404, {"error": "yok"})
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
                if path == "/api/island":
                    if not self._token_ok(self.headers.get("X-Token", "")):
                        return self._json(403, {"error": "anahtar"})
                    return self._json(200, st.island_snapshot(dash.ctx))
                if path == "/api/state":
                    if not self._token_ok(self.headers.get("X-Token", "")):
                        return self._json(403, {"error": "anahtar"})
                    return self._json(200, st.build_state(dash.ctx))
                return self._json(404, {"error": "yok"})

            def _read_body(self, limit: int) -> bytes | None:
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if n < 0:
                    self._json(400, {"error": "bozuk istek"})
                    return None
                if n > limit:
                    self._json(413, {"error": "büyük"})
                    return None
                try:
                    return self.rfile.read(n) if n else b""
                except OSError:
                    self._json(400, {"error": "bozuk istek"})
                    return None

            def _read_json(self) -> dict | None:
                raw = self._read_body(MAX_BODY)
                if raw is None:
                    return None
                try:
                    data = json.loads(raw or b"{}")
                    if not isinstance(data, dict):
                        raise ValueError
                except ValueError:
                    self._json(400, {"error": "bozuk istek"})
                    return None
                return data

            def _origin_ok(self) -> bool:
                origin = self.headers.get("Origin")
                if not origin:
                    return True
                return origin.split("://", 1)[-1].lower() == self._host()

            def do_POST(self):  # noqa: N802
                scope = self._scope()
                if not scope:
                    return self._json(403, {"error": "yasak"})
                if self.path.startswith("/api/m/"):
                    if not self._origin_ok():
                        return self._json(403, {"error": "köken"})
                    if self.path not in ("/api/m/chat", "/api/m/voice", "/api/m/cmd", "/api/m/agenda"):
                        return self._json(404, {"error": "yok"})
                    if not self._m_auth():
                        return None
                    if self.path == "/api/m/voice":
                        raw = self._read_body(MAX_AUDIO)
                        if raw is None:
                            return None
                        code, obj = dash.m_voice(raw)
                        return self._json(code, obj)
                    data = self._read_json()
                    if data is None:
                        return None
                    if self.path == "/api/m/chat":
                        code, obj = dash.m_chat(data.get("text", ""))
                        return self._json(code, obj)
                    if self.path == "/api/m/cmd":
                        code, obj = dash.m_cmd(data)
                        return self._json(code, obj)
                    return self._json(200, dash.m_agenda(data))
                if scope != "local" or not self._token_ok(self.headers.get("X-Token", "")):
                    return self._json(403, {"error": "yasak"})
                if self.path not in ("/api/cmd", "/api/agenda", "/api/conv", "/api/island/answer"):
                    return self._json(404, {"error": "yok"})
                data = self._read_json()
                if data is None:
                    return None
                if self.path == "/api/agenda":
                    return self._json(200, dash.agenda_op(data))
                if self.path == "/api/conv":
                    return self._json(200, dash.conv_op(data))
                if self.path == "/api/island/answer":
                    return self._json(200, dash.island_answer(str(data.get("answer", "")), str(data.get("id", ""))))
                return self._json(200, dash.run_command(str(data.get("id", "")), str(data.get("say", "")), bool(data.get("chat")), str(data.get("theme", "")),
                                                        data.get("island") if "island" in data else None))

        return H
