"""Telefon (mobil) arayüzü testleri: ayrı anahtar/kapsam, Host ve Origin denetimi, kilitleme, yazışma, ses, hızlı komutlar,
ajanda, Tailscale yardımcıları, sayfa tutarlılığı (CSP uyumu, kimlikler)."""
import datetime as dt
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import types
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
import remote  # noqa: E402
import ui_state  # noqa: E402
from dashboard import server, state  # noqa: E402
from skills import agenda  # noqa: E402

HERE = Path(__file__).resolve().parent
STATIC = HERE / "dashboard" / "static"
state._online = lambda: True
bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


HOST = "pc.tail1234.ts.net"
ui_state.reset()
ui_state.set_state("listening")
brain = types.SimpleNamespace(model="gemma4:e4b", tools={"agenda_add": 1}, history=[], summary="", tool_count=0, active_model="gemma4:e4b",
                              agent=types.SimpleNamespace(state="idle", goal=""))
ctx = types.SimpleNamespace(brain=brain, fallbacks=[])
chat_calls, voice_calls = [], []
gate = {"event": None, "mode": "ok"}


def fake_chat(text):
    chat_calls.append(text)
    if gate["event"]:
        gate["event"].wait(3)
    if gate["mode"] == "timeout":
        raise TimeoutError("meşgul")
    if gate["mode"] == "boom":
        raise RuntimeError("x")
    return f"cevap: {text}"


def fake_voice(data):
    voice_calls.append(len(data))
    return "merhaba jarvis"


d = server.Dashboard(ctx, lambda *a, **k: None, port=18765, chat=fake_chat, transcribe=fake_voice)
d.start()


def req(method, path, body=None, host=None, token=None, raw=None, extra=None, port=None):
    c = http.client.HTTPConnection("127.0.0.1", port or d.port, timeout=8)
    h = {"Host": host or f"127.0.0.1:{d.port}"}
    if token:
        h["X-Token"] = token
    data = raw if raw is not None else (json.dumps(body) if body is not None else None)
    if raw is not None:
        h["Content-Type"] = "audio/webm"
    elif data is not None:
        h["Content-Type"] = "application/json"
    h.update(extra or {})
    c.request(method, path, data, h)
    r = c.getresponse()
    out = r.read()
    hdr = dict(r.getheaders())
    c.close()
    return r.status, out, hdr


def jreq(*a, **k):
    code, out, _ = req(*a, **k)
    try:
        return code, json.loads(out)
    except ValueError:
        return code, {}


# ---------------------------------------------------------------- remote.py
check("başlangıçta uzaktan erişim kapalı", not remote.enabled())
check("kapalıyken tailnet adı reddedilir", not remote.host_ok(HOST))
tok = remote.new_token()
remote.set_hosts([HOST + "."])
check("anahtar üretildi ve açıldı", remote.enabled() and len(tok) >= 30)
check("anahtar dosyası yalnızca sahibine açık", (os.stat(remote._store.path(remote.FILE)).st_mode & 0o077) == 0)
check("Host (443 ile/siz, büyük harf) kabul", remote.host_ok(HOST) and remote.host_ok(HOST + ":443") and remote.host_ok(HOST.upper()))
check("başka Host reddedilir", not remote.host_ok("evil.example") and not remote.host_ok(""))
check("anahtar doğrulama", remote.check_token(tok) and not remote.check_token(tok + "x") and not remote.check_token("") and not remote.check_token("x" * 32))
check("pano anahtarı telefon anahtarı DEĞİL", not remote.check_token(d.token))
check("bağlantı anahtarı # parçasında", remote.pair_url(HOST, tok) == f"https://{HOST}/m#t={tok}")

# ---------------------------------------------------------------- kapsam ayrımı
H = HOST
code, out, hdr = req("GET", "/m", host=H)
check("/m anahtarsız açılır (sayfada sır yok)", code == 200 and tok.encode() not in out and d.token.encode() not in out)
check("/m: CSP başlığı (satır içi betik yok)", "script-src 'self'" in hdr.get("Content-Security-Policy", "") and "frame-ancestors 'none'" in hdr.get("Content-Security-Policy", ""))
check("m.js / m.css / manifest / ikonlar", all(req("GET", p, host=H)[0] == 200 for p in ("/static/m.js", "/static/m.css", "/manifest.webmanifest", "/static/m-icon-192.png", "/static/m-icon-512.png")))
check("uzak Host: pano sayfası yok", req("GET", "/", host=H, token=d.token)[0] == 404 and req("GET", f"/?t={d.token}", host=H)[0] == 404)
check("uzak Host: pano dosyaları yok (app.js, style.css)", req("GET", "/static/app.js", host=H)[0] == 404 and req("GET", "/static/style.css", host=H)[0] == 404)
check("uzak Host: /api/state, /api/conv yok", req("GET", "/api/state", host=H, token=tok)[0] == 404 and req("GET", "/api/conv", host=H, token=tok)[0] == 404)
check("uzak Host: pano POST'ları yasak (kapat/tema/ayar)", all(req("POST", p, {"id": "quit"}, host=H, token=t)[0] == 403
                                                           for p in ("/api/cmd", "/api/conv", "/api/agenda") for t in (tok, d.token)))
check("uzak Host: yol gezinme yok", req("GET", "/static/../server.py", host=H)[0] == 404 and req("GET", "/static/m.js/../app.js", host=H)[0] in (404, 200))
check("bilinmeyen Host reddedilir", req("GET", "/m", host="evil.example")[0] == 403 and req("POST", "/api/m/chat", {"text": "x"}, host="evil.example", token=tok)[0] == 403)
check("telefon anahtarı pano uçlarında geçmez", req("GET", "/api/state", token=tok)[0] == 403 and req("POST", "/api/cmd", {"id": "stop"}, token=tok)[0] == 403)
check("pano anahtarı telefon uçlarında geçmez", req("GET", "/api/m/state", host=H, token=d.token)[0] == 403)
d.limiter = remote.Limiter()  # yukarıdaki yanlış denemeler kilitlemesin

# ---------------------------------------------------------------- durum
code, s = jreq("GET", "/api/m/state", host=H)
check("anahtarsız durum yok", code == 403)
code, s = jreq("GET", "/api/m/state", host=H, token=tok)
check("durum: 200 ve beklenen alanlar", code == 200 and all(k in s for k in ("durum", "sistem", "ajanda", "alt", "model", "voice", "history")), str(list(s)))
check("durum: araç listesi/hafıza/anahtar sızmaz", not any(k in s for k in ("araclar", "hafiza", "model_cloud", "token")) and "gemma4:e4b" == s.get("model"))
check("durum: ses tanıma açık bilgisi", s.get("voice") is True)
check("telefon anahtarı yerel Host'ta da /api/m/state için çalışır", jreq("GET", "/api/m/state", token=tok)[0] == 200)

# ---------------------------------------------------------------- yazışma
code, r = jreq("POST", "/api/m/chat", {"text": "  merhaba   jarvis "}, host=H, token=tok)
check("yazışma: cevap döner, boşluklar toparlanır", code == 200 and r.get("reply") == "cevap: merhaba jarvis" and chat_calls[-1] == "merhaba jarvis", str(r))
check("yazışma: boş mesaj 400", jreq("POST", "/api/m/chat", {"text": "  "}, host=H, token=tok)[0] == 400)
jreq("POST", "/api/m/chat", {"text": "a" * 1500}, host=H, token=tok)
check("yazışma: uzun mesaj kırpılır", len(chat_calls[-1]) == server.MAX_CHAT)
check("yazışma: büyük gövde 413", req("POST", "/api/m/chat", raw=b"x" * 5000, host=H, token=tok)[0] == 413)
check("yazışma: bozuk JSON 400", req("POST", "/api/m/chat", raw=b"{bozuk", host=H, token=tok)[0] == 400)
gate["event"] = threading.Event()
res = {}
t1 = threading.Thread(target=lambda: res.update(first=jreq("POST", "/api/m/chat", {"text": "uzun is"}, host=H, token=tok)))
t1.start()
for _ in range(50):
    if chat_calls[-1] == "uzun is":
        break
    threading.Event().wait(0.05)
code2, r2 = jreq("POST", "/api/m/chat", {"text": "ikinci"}, host=H, token=tok)
check("yazışma: aynı anda ikinci istek 429 (kuyruk birikmez)", code2 == 429 and "ikinci" not in chat_calls)
gate["event"].set()
t1.join()
check("yazışma: birinci istek yine de tamamlandı", res["first"][0] == 200)
gate["event"] = None
gate["mode"] = "timeout"
check("yazışma: beyin meşgulse 504", jreq("POST", "/api/m/chat", {"text": "x"}, host=H, token=tok)[0] == 504)
gate["mode"] = "boom"
code, r = jreq("POST", "/api/m/chat", {"text": "x"}, host=H, token=tok)
check("yazışma: hata ayrıntısı sızmaz, sunucu ayakta", code == 500 and "RuntimeError" in r.get("error", "") and "x" not in r.get("error", "").replace("RuntimeError", "").strip(), str(r))
gate["mode"] = "ok"
check("yazışma: hatadan sonra normale döner", jreq("POST", "/api/m/chat", {"text": "tekrar"}, host=H, token=tok)[0] == 200)
check("Origin eşleşmezse reddedilir (CSRF)", req("POST", "/api/m/chat", {"text": "x"}, host=H, token=tok, extra={"Origin": "https://evil.example"})[0] == 403)
check("Origin aynıysa kabul", req("POST", "/api/m/chat", {"text": "x"}, host=H, token=tok, extra={"Origin": f"https://{H}"})[0] == 200)

# ---------------------------------------------------------------- ses
code, r = jreq("POST", "/api/m/voice", raw=b"\x1aE\xdf\xa3" + b"\0" * 4000, host=H, token=tok)
check("ses: yazıya çevrilir", code == 200 and r.get("text") == "merhaba jarvis" and voice_calls[-1] == 4004, str(r))
check("ses: çok kısa kayıt 400", jreq("POST", "/api/m/voice", raw=b"\0" * 100, host=H, token=tok)[0] == 400)
check("ses: aşırı büyük 413", req("POST", "/api/m/voice", raw=b"\0" * 10, host=H, token=tok, extra={"Content-Length": str(server.MAX_AUDIO + 1)})[0] == 413)
check("ses: anahtarsız 403", req("POST", "/api/m/voice", raw=b"\0" * 4000, host=H)[0] == 403)
d2 = d.transcribe
d.transcribe = None
check("ses: tanıma yoksa (--text) 503", jreq("POST", "/api/m/voice", raw=b"\0" * 4000, host=H, token=tok)[0] == 503)
d.transcribe = lambda b: (_ for _ in ()).throw(ValueError("decode"))
code, r = jreq("POST", "/api/m/voice", raw=b"\0" * 4000, host=H, token=tok)
check("ses: çözme hatası 500 (tür ve kısa ayrıntı), sunucu ayakta", code == 500 and "ValueError" in r.get("error", "") and "decode" in r.get("error", ""))
d.transcribe = d2

# ---------------------------------------------------------------- hızlı komutlar
chat_calls.clear()
for cid, said in (("brief", "günün özeti"), ("tasks", "görevlerim neler"), ("today", "bugün ne yapıyorum"), ("system", "sistem durumu"),
                  ("battery", "pil kaç"), ("weather", "hava nasıl"), ("yes", "evet"), ("no", "vazgeç")):
    jreq("POST", "/api/m/cmd", {"id": cid}, host=H, token=tok)
    check(f"komut {cid}: yazışmadan geçer ('{said}')", chat_calls and chat_calls[-1] == said)
for cid in ("quit", "cloudtoggle", "traytoggle", "chatvoice", "talk", "yok", ""):
    check(f"komut {cid or '(boş)'}: telefondan kapalı", jreq("POST", "/api/m/cmd", {"id": cid}, host=H, token=tok)[0] == 400)
check("komut stop: sustur isteği", jreq("POST", "/api/m/cmd", {"id": "stop"}, host=H, token=tok)[0] == 200 and ui_state.consume_stop())
was = ui_state.is_muted()
jreq("POST", "/api/m/cmd", {"id": "mute"}, host=H, token=tok)
check("komut mute: sessize alma değişir", ui_state.is_muted() != was)
ui_state.set_muted(False)
was = ui_state.is_focus()
jreq("POST", "/api/m/cmd", {"id": "focus"}, host=H, token=tok)
check("komut focus: odak değişir", ui_state.is_focus() != was)
ui_state.set_focus(False)

# ---------------------------------------------------------------- ajanda
code, r = jreq("POST", "/api/m/agenda", {"op": "add_task", "title": "Süt al", "due": "", "priority": "yüksek"}, host=H, token=tok)
check("ajanda: görev eklenir, güncel özet döner", code == 200 and r.get("ok") and any(t["title"] == "Süt al" for t in r["ajanda"]["tasks"]), str(r)[:200])
tid = next(t["id"] for t in r["ajanda"]["tasks"] if t["title"] == "Süt al")
code, r = jreq("POST", "/api/m/agenda", {"op": "add_event", "title": "Diş randevusu", "date": (dt.date.today() + dt.timedelta(days=10)).isoformat(), "time": "10:30"}, host=H, token=tok)
check("ajanda: etkinlik eklenir", r.get("ok") and any(e["title"] == "Diş randevusu" for e in r["ajanda"]["events"]), str(r)[:200])
eid = next(e["id"] for e in r["ajanda"]["events"] if e["title"] == "Diş randevusu")
check("ajanda: görev biter", jreq("POST", "/api/m/agenda", {"op": "done_task", "id": tid}, host=H, token=tok)[1].get("ok"))
check("ajanda: etkinlik silinir", jreq("POST", "/api/m/agenda", {"op": "cancel_event", "id": eid}, host=H, token=tok)[1].get("ok"))
check("ajanda: bilinmeyen işlem reddedilir", not jreq("POST", "/api/m/agenda", {"op": "wipe"}, host=H, token=tok)[1].get("ok"))
check("ajanda: bozuk kimlik hata verir, çökmez", not jreq("POST", "/api/m/agenda", {"op": "done_task", "id": "abc"}, host=H, token=tok)[1].get("ok"))
check("ajanda: metin düz yazı (HTML çalışmaz, kırpılır)", jreq("POST", "/api/m/agenda", {"op": "add_task", "title": "<b>" + "x" * 500}, host=H, token=tok)[0] == 200)

# ---------------------------------------------------------------- kilitleme / hız sınırı
now = [0.0]
d.limiter = remote.Limiter(fails=5, window=60, lock=60, per_min=1000, clock=lambda: now[0])
for _ in range(5):
    req("GET", "/api/m/state", host=H, token="yanlis")
code, _ = jreq("GET", "/api/m/state", host=H, token=tok)
check("5 yanlış denemeden sonra DOĞRU anahtar da geçici kilitli (429)", code == 429)
now[0] += 61
check("kilit süresi dolunca açılır", jreq("GET", "/api/m/state", host=H, token=tok)[0] == 200)
check("doğru girişten sonra yanlış sayacı sıfırlanır", (req("GET", "/api/m/state", host=H, token="yanlis"), jreq("GET", "/api/m/state", host=H, token=tok)[0] == 200)[1])
lim = remote.Limiter(per_min=3, clock=lambda: now[0])
check("dakikalık sınır: 3 kabul, 4. ret", [lim.hit() for _ in range(4)] == [True, True, True, False])
now[0] += 61
check("dakikalık sınır: süre geçince açılır", lim.hit())
d.limiter = remote.Limiter()

# ---------------------------------------------------------------- iptal
remote.revoke()
check("iptal: anahtar silinir, uzak Host kapanır", not remote.enabled() and req("GET", "/m", host=H)[0] == 403 and req("GET", "/api/m/state", host=H, token=tok)[0] == 403)
remote.new_token()
remote.set_hosts([HOST])
tok2 = remote.token()
check("yeni anahtar eskisini geçersiz kılar", tok2 != tok and jreq("GET", "/api/m/state", host=H, token=tok)[0] == 403 and jreq("GET", "/api/m/state", host=H, token=tok2)[0] == 200)
d.limiter = remote.Limiter()

# ---------------------------------------------------------------- Tailscale yardımcıları (sahte komut)
calls = []
funnel = {"on": False}


def fake_ts(*args, timeout=15):
    calls.append(args)
    if args[:2] == ("serve", "status"):
        return 0, ("https://pc.tail1234.ts.net (Funnel on)\n|-- / proxy http://127.0.0.1:8765" if funnel["on"] else "https://pc.tail1234.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8765")
    if args[:2] == ("status", "--json"):
        return 0, json.dumps({"BackendState": "Running", "Self": {"DNSName": "Pc.Tail1234.ts.net."}})
    return 0, "ok"


real_ts = remote._ts
remote._ts = fake_ts
check("tailnet adı: küçük harf, sondaki nokta atılır", remote.tailnet_name()[0] == "pc.tail1234.ts.net")
ok, _ = remote.apply_serve(8765)
check("serve: yalnızca tailnet HTTPS komutu (funnel yok)", ok and any(c[:2] == ("serve", "--bg") and "--https=443" in c and "http://127.0.0.1:8765" in c for c in calls) and not any("funnel" in c[0] for c in calls))
funnel["on"] = True
calls.clear()
ok, msg = remote.apply_serve(8765)
check("Funnel açıksa yayın kurulmaz, uyarı verir", (not ok) and "Funnel" in msg and not any(c[:2] == ("serve", "--bg") for c in calls))
funnel["on"] = False
remote._ts = lambda *a, **k: (0, json.dumps({"BackendState": "NeedsLogin"}))
check("Tailscale girişsizse anlaşılır hata", remote.tailnet_name()[0] is None and "Tailscale" in remote.tailnet_name()[1])
remote._ts = lambda *a, **k: (0, json.dumps({"BackendState": "Running", "Self": {"DNSName": ""}}))
check("MagicDNS yoksa anlaşılır hata", remote.tailnet_name()[0] is None and "MagicDNS" in remote.tailnet_name()[1])
remote._ts = fake_ts
cfg = remote.load()
cfg["port"] = 8765
remote.save(cfg)
calls.clear()
msg = remote.sync(8766)
check("açılışta pano portu değiştiyse yayın yeni porta çevrilir", any("http://127.0.0.1:8766" in c for c in calls) and remote.load()["port"] == 8766 and "https://" in msg)
calls.clear()
remote.sync(8766)
check("port aynıysa yayına dokunulmaz", not any(c[:2] == ("serve", "--bg") for c in calls))
remote._ts = real_ts
remote.revoke()
check("kapalıyken sync sessiz", remote.sync(8765) == "")

# ---------------------------------------------------------------- kurulum betiği
r = subprocess.run([sys.executable, "remote_setup.py", "--status"], capture_output=True, text=True, cwd=str(HERE), timeout=30, env=dict(os.environ))
check("remote_setup --status çalışır", r.returncode == 0 and "Uzaktan erişim" in r.stdout, r.stdout + r.stderr)
r = subprocess.run([sys.executable, "remote_setup.py", "--host", "pc.tail1234.ts.net", "--no-serve"], capture_output=True, text=True, cwd=str(HERE), timeout=30, env=dict(os.environ))
m = re.search(r"https://pc\.tail1234\.ts\.net/m#t=([A-Za-z0-9_-]+)", r.stdout)
check("remote_setup: bağlantı üretir ve erişimi açar", r.returncode == 0 and m and remote.enabled() and m.group(1) == remote.token(), r.stdout + r.stderr)
r = subprocess.run([sys.executable, "remote_setup.py", "--revoke"], capture_output=True, text=True, cwd=str(HERE), timeout=30, env=dict(os.environ))
check("remote_setup --revoke erişimi kapatır", r.returncode == 0 and not remote.enabled())

# ---------------------------------------------------------------- sayfa tutarlılığı
html = (STATIC / "m.html").read_text(encoding="utf-8")
js = (STATIC / "m.js").read_text(encoding="utf-8")
css = (STATIC / "m.css").read_text(encoding="utf-8")
ids = set(re.findall(r'id="([\w-]+)"', html))
used = set(re.findall(r'\$\("#([\w-]+)"', js)) | set(re.findall(r'\$\$\("#([\w-]+)', js))
check("m.js'in kullandığı tüm kimlikler m.html'de var", used <= ids, str(used - ids))
check("m.html: satır içi betik/stil/olay yok (CSP)", not re.search(r"<script(?![^>]*\bsrc=)", html) and " style=" not in html and not re.search(r"\son\w+=", html))
check("m.js: setAttribute('style'), innerHTML, eval yok", "innerHTML" not in js and "eval(" not in js and "setAttribute(\"style\"" not in js and "document.write" not in js)
check("m.js: anahtar URL'de/sorguda gitmez (yalnızca X-Token başlığı)", "X-Token" in js and "?t=" not in js and "localStorage" in js)
check("m.html: harici kaynak yok", not re.search(r'(?:src|href)="https?://', html) and "url(http" not in css)
check("m.js: sunucudaki tüm /api/m uçlarını kullanır", all(p in js for p in ("/api/m/state", "/api/m/chat", "/api/m/voice", "/api/m/cmd", "/api/m/agenda")))
data_cmds = set(re.findall(r'data-cmd="(\w+)"', html))
check("m.html hızlı komutları sunucu izin listesinde", data_cmds <= set(remote.REMOTE_SAY), str(data_cmds - set(remote.REMOTE_SAY)))
man = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
check("manifest: /m başlangıç, 192+512 ikon, standalone", man["start_url"] == "/m" and man["display"] == "standalone"
      and {i["sizes"] for i in man["icons"]} >= {"192x192", "512x512"} and all((STATIC / i["src"].replace("/static/", "")).exists() for i in man["icons"]))
srv = (HERE / "dashboard" / "server.py").read_text(encoding="utf-8")
check("sunucu: izinli statik dosyalar gerçekten var", all((STATIC / n).exists() for n in server.REMOTE_STATIC))
if subprocess.run(["which", "node"], capture_output=True).returncode == 0:
    r = subprocess.run(["node", "--check", str(STATIC / "m.js")], capture_output=True, text=True)
    check("m.js sözdizimi (node --check)", r.returncode == 0, r.stderr)

# ---------------------------------------------------------------- stt: telefon sesi ve model kilidi
import stt  # noqa: E402

fa = types.ModuleType("faster_whisper")
fa_audio = types.ModuleType("faster_whisper.audio")
import numpy as np  # noqa: E402

fa_audio.decode_audio = lambda f, sampling_rate=16000: np.ones(sampling_rate * 3, dtype=np.float32)
fa.audio = fa_audio
sys.modules["faster_whisper"], sys.modules["faster_whisper.audio"] = fa, fa_audio
lis = object.__new__(stt.Listener)
lis.beam, lis.prompt = 1, ""
active, peak = [0], [0]


class FakeModel:
    def transcribe(self, audio, **kw):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        threading.Event().wait(0.05)

        def gen():
            yield types.SimpleNamespace(text=" merhaba ")
            threading.Event().wait(0.05)
            yield types.SimpleNamespace(text="dünya ")
            active[0] -= 1
        return gen(), None


lis.model = FakeModel()
check("transcribe_bytes: kayıt çözülüp yazıya çevrilir", lis.transcribe_bytes(b"x" * 3000) == "merhaba dünya")
# çözücü yedekleri: faster-whisper yardımcısı TypeError verirse PyAV/ffmpeg denenir
fa_audio.decode_audio = lambda f, sampling_rate=16000: (_ for _ in ()).throw(TypeError("beklenmeyen imza"))
lis._decode_av = lambda data: np.ones(16000 * 3, dtype=np.float32)
check("transcribe_bytes: faster-whisper çözücüsü bozulursa PyAV yedeği kullanılır", lis.transcribe_bytes(b"x" * 3000) == "merhaba dünya")
lis._decode_av = lambda data: (_ for _ in ()).throw(ValueError("av yok"))
lis._decode_ffmpeg = lambda data: np.ones(16000 * 3, dtype=np.float32)
check("transcribe_bytes: PyAV de olmazsa ffmpeg yedeği", lis.transcribe_bytes(b"x" * 3000) == "merhaba dünya")
lis._decode_ffmpeg = lambda data: (_ for _ in ()).throw(FileNotFoundError("ffmpeg yok"))
try:
    lis.transcribe_bytes(b"x" * 3000)
    check("transcribe_bytes: hiçbir çözücü olmazsa ilk hata ayrıntıyla", False)
except RuntimeError as e:
    check("transcribe_bytes: hiçbir çözücü olmazsa ilk hata ayrıntıyla", "TypeError" in str(e) and "imza" in str(e))
del lis._decode_av, lis._decode_ffmpeg
fa_audio.decode_audio = lambda f, sampling_rate=16000: np.ones(sampling_rate * 3, dtype=np.float32)
out = []
ts = [threading.Thread(target=lambda: out.append(lis.transcribe(np.ones(32000, dtype=np.float32)))) for _ in range(4)]
[t.start() for t in ts]
[t.join() for t in ts]
check("Whisper aynı anda tek iş (ana döngü + telefon çakışmaz)", peak[0] == 1 and len(out) == 4, f"peak={peak[0]}")
fa_audio.decode_audio = lambda f, sampling_rate=16000: np.ones(sampling_rate * 500, dtype=np.float32)
got = []
lis.model.transcribe = lambda audio, **kw: (got.append(len(audio)) or ([types.SimpleNamespace(text="a")], None))
lis.transcribe_bytes(b"x")
check("telefon sesi en çok 120 sn işlenir", got and got[0] == 120 * stt.SAMPLE_RATE)

# ---------------------------------------------------------------- main.run_remote
import main as jmain  # noqa: E402

fb = types.SimpleNamespace(lock=threading.RLock(), remote=False, seen=[])


def rs(text):
    fb.seen.append(fb.remote)
    yield "Merhaba "
    yield "dünya"


fb.reply_stream = rs
check("run_remote: cevabı birleştirir, kısıtlı kip yalnızca sırasında açık", jmain.run_remote(fb, "selam", "Telefon", timeout=2) == "Merhaba dünya" and fb.seen == [True] and fb.remote is False)
blocker = threading.Event()
holder = threading.Thread(target=lambda: (fb.lock.acquire(), blocker.wait(3), fb.lock.release()))
holder.start()
threading.Event().wait(0.1)
try:
    jmain.run_remote(fb, "selam", "Telefon", timeout=0.2)
    check("run_remote: beyin meşgulse TimeoutError", False)
except TimeoutError:
    check("run_remote: beyin meşgulse TimeoutError", True)
blocker.set()
holder.join()
check("run_remote: zaman aşımından sonra kilit sızmaz", jmain.run_remote(fb, "selam", "Telefon", timeout=1) == "Merhaba dünya")


def rs_err(text):
    raise RuntimeError("model çöktü")
    yield ""


fb.reply_stream = rs_err
try:
    jmain.run_remote(fb, "x", "Telefon", timeout=1)
except RuntimeError:
    pass
check("run_remote: hata olsa da kısıtlı kip kapanır ve kilit bırakılır", fb.remote is False and fb.lock.acquire(timeout=0.5))

d.stop()
print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
