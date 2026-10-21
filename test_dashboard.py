"""Komut Merkezi panosu testleri: güvenlik (anahtar, Host, yol gezinme), komutlar, durum, hata yalıtımı."""
import datetime as dt
import http.client
import json
import os
import sys
import tempfile
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
import ui_state  # noqa: E402
from dashboard import server, state  # noqa: E402
from skills import agenda, weather  # noqa: E402

# Testler gerçek ağa çıkmasın (yavaş internette panoyu bekletip testi düşürüyordu)
weather._get = lambda url: ({"results": [{"latitude": 1, "longitude": 2}]} if "geocoding" in url else {"current": {"temperature_2m": 17.6}})
state._online = lambda: True

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


def req(d, method, path, body=None, token=True, host=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", d.port, timeout=5)
    h = {"Host": host or f"127.0.0.1:{d.port}"}
    if token:
        h["X-Token"] = d.token
    data = raw if raw is not None else (json.dumps(body) if body is not None else None)
    if data is not None:
        h["Content-Type"] = "application/json"
    c.request(method, path, data, h)
    r = c.getresponse()
    out = r.read()
    c.close()
    return r.status, out


# ---- veri: bugün 3 etkinlik, 3 görev (biri gecikmiş)
real_now = agenda._now
agenda._now = lambda: dt.datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
agenda.add_event("Sabah toplantısı", dt.date.today().isoformat(), "08:30")
agenda.add_event("<img src=x onerror=alert(1)>", dt.date.today().isoformat(), "23:50")
agenda.add_task("Gecikmiş iş", (dt.date.today() - dt.timedelta(days=2)).isoformat(), "yüksek")
agenda.add_task("Bugünkü iş", dt.date.today().isoformat(), "orta")
agenda.add_task("Tarihsiz", "", "düşük")
agenda._now = real_now
ui_state.reset()
ui_state.set_state("listening")
ui_state.add_turn("sen", "merhaba")

brain = types.SimpleNamespace(model="gemma4:e4b", tools={"browser_open": 1, "agenda_add": 1, "mouse_click": 1}, history=[1, 2],
                              summary="", tool_count=5, active_model="qwen3:8b", agent=types.SimpleNamespace(state="plan", goal="x"))
ctx = types.SimpleNamespace(brain=brain, fallbacks=["qwen3:8b"])
sent, silents, quits = [], [], []
d = server.Dashboard(ctx, lambda t, silent=False: (sent.append(t), silents.append(silent)), port=8899, quit=lambda: quits.append(1))
d.start()

# ---- güvenlik
check("anahtarsız ana sayfa 403", req(d, "GET", "/", token=False)[0] == 403)
check("yanlış anahtarla ana sayfa 403", req(d, "GET", "/?t=yanlis", token=False)[0] == 403)
s, body = req(d, "GET", f"/?t={d.token}", token=False)
check("doğru anahtarla arayüz geliyor", s == 200 and b"JARVIS" in body and b"app.js" in body)
check("anahtarsız /api/state 403", req(d, "GET", "/api/state", token=False)[0] == 403)
check("yanlış Host (DNS yeniden bağlama) 403", req(d, "GET", "/api/state", host="evil.example:80")[0] == 403)
check("anahtarsız komut 403", req(d, "POST", "/api/cmd", {"id": "brief"}, token=False)[0] == 403)
check("yol gezinme engelli", req(d, "GET", "/static/../server.py", token=False)[0] == 404
      and req(d, "GET", "/static/%2e%2e/server.py", token=False)[0] == 404)
check("static dosyalar anahtarsız gelir", req(d, "GET", "/static/style.css", token=False)[0] == 200)
check("sunucu yalnızca 127.0.0.1", d.httpd.server_address[0] == "127.0.0.1")

# ---- komutlar
check("brief -> 'günün özeti'", req(d, "POST", "/api/cmd", {"id": "brief"})[0] == 200 and sent[-1] == "günün özeti")
check("görevler/sistem/pil/hava kimlikleri", all(req(d, "POST", "/api/cmd", {"id": i})[0] == 200 for i in ("tasks", "system", "battery", "weather", "today")) and sent[-1] == "bugün ne yapıyorum")
check("bilinmeyen komut reddedilir", json.loads(req(d, "POST", "/api/cmd", {"id": "rm_rf"})[1])["ok"] is False and sent[-1] == "bugün ne yapıyorum")
n = len(sent)
req(d, "POST", "/api/cmd", {"say": "  saat   kaç  " + "x" * 500})
check("serbest metin kısaltılır, boşluklar toplanır", len(sent) == n + 1 and sent[-1].startswith("saat kaç x") and len(sent[-1]) <= server.MAX_SAY)
check("çok büyük gövde 413", req(d, "POST", "/api/cmd", raw="{" + " " * 5000 + "}")[0] == 413)
check("bozuk JSON 400", req(d, "POST", "/api/cmd", raw="{not json")[0] == 400)
check("JSON olmayan nesne 400", req(d, "POST", "/api/cmd", raw="[1,2]")[0] == 400)
ui_state.set_muted(False)
req(d, "POST", "/api/cmd", {"id": "mute"})
check("mute düğmesi sessize alır", ui_state.is_muted())
req(d, "POST", "/api/cmd", {"id": "mute"})
check("mute tekrar açar", not ui_state.is_muted())
req(d, "POST", "/api/cmd", {"id": "focus"})
check("odak modu açılır", ui_state.is_focus())
req(d, "POST", "/api/cmd", {"id": "focus"})
check("odak modu kapanır", not ui_state.is_focus())
req(d, "POST", "/api/cmd", {"id": "stop"})
check("sustur isteği", ui_state.consume_stop() is True)
req(d, "POST", "/api/cmd", {"id": "talk"})
check("konuş isteği bir kez tüketilir", ui_state.consume_listen() is True and ui_state.consume_listen() is False)
check("evet/hayır düğmeleri metin olarak gider", (req(d, "POST", "/api/cmd", {"id": "yes"}), sent[-1])[1] == "evet"
      and (req(d, "POST", "/api/cmd", {"id": "no"}), sent[-1])[1] == "vazgeç")

req(d, "POST", "/api/cmd", {"say": "merhaba", "chat": True})
check("Yazışma: sesli cevap açıkken normal gider", sent[-1] == "merhaba" and silents[-1] is False)
req(d, "POST", "/api/cmd", {"id": "chatvoice"})
check("sesli cevap kapatılır (kalıcı ayar)", ui_state.chat_voice() is False)
req(d, "POST", "/api/cmd", {"say": "selam", "chat": True})
check("Yazışma: kapalıyken sessiz (silent) gider", sent[-1] == "selam" and silents[-1] is True)
req(d, "POST", "/api/cmd", {"say": "sesli komut"})
check("sohbet dışı (düğme/ses) komutlar etkilenmez", silents[-1] is False)
req(d, "POST", "/api/cmd", {"id": "brief"})
check("hızlı komut düğmeleri her zaman sesli", silents[-1] is False)
check("durum chat_voice alanı", json.loads(req(d, "GET", "/api/state")[1])["durum"]["chat_voice"] is False)
req(d, "POST", "/api/cmd", {"id": "chatvoice"})
check("sesli cevap tekrar açılır", ui_state.chat_voice() is True)

# ---- tema ve kapatma
check("varsayılan tema cyan", ui_state.theme() == "cyan")
check("geçerli tema kaydedilir", json.loads(req(d, "POST", "/api/cmd", {"theme": "amber"})[1])["ok"] and ui_state.theme() == "amber"
      and json.loads(req(d, "GET", "/api/state")[1])["durum"]["theme"] == "amber")
check("geçersiz tema reddedilir (ayar bozulmaz)", json.loads(req(d, "POST", "/api/cmd", {"theme": "<script>"})[1])["ok"] is False and ui_state.theme() == "amber")
check("tüm temalar kabul", all(json.loads(req(d, "POST", "/api/cmd", {"theme": t})[1])["ok"] for t in ui_state.THEMES))
ui_state.set_theme("cyan")
check("kapatma komutu bağlı fonksiyonu çağırır", req(d, "POST", "/api/cmd", {"id": "quit"})[0] == 200 and quits == [1])
check("anahtarsız kapatma yapılmaz", req(d, "POST", "/api/cmd", {"id": "quit"}, token=False)[0] == 403 and quits == [1])
d2 = server.Dashboard(ctx, lambda t: None, port=8920)
check("kapatma bağlı değilse hata (çökmez)", d2.run_command("quit")["ok"] is False)
d2.httpd.server_close()

# ---- durum
s, body = req(d, "GET", "/api/state")
st = json.loads(body)
check("durum JSON hatasız (tüm sağlayıcılar)", s == 200 and not st.get("hatalar"), st.get("hatalar"))
check("durum: dinliyor + son konuşma", st["durum"]["state"] == "listening" and st["durum"]["turns"][-1]["text"] == "merhaba")
check("onay bekleyen plan 'pending' görünür", st["durum"]["pending"] is True)
check("sistem: cpu/ram/disk sayı", isinstance(st["sistem"]["ram"]["total"], float) and st["sistem"]["disk"]["total"] > 0)
check("model: aktif model yedek (qwen3:8b), araç sayısı", [m["name"] for m in st["model"]["llm"] if m["active"]] == ["qwen3:8b"] and st["model"]["tool_calls"] == 5)
check("ajanda: açık 3, geciken 1", st["ajanda"]["open_tasks"] == 3 and st["ajanda"]["overdue"] == 1)
check("ajanda: bugünün etkinlikleri saat sırasıyla", [e["time"] for e in st["ajanda"]["events_today"]] == ["08:30", "23:50"])
check("akış: geciken görev uyarısı", any(i["level"] == "UYARI" and "gecik" in i["text"] for i in st["akis"]))
check("ajanlar: gerçek yetenekler Hazır, çoklu ajan Yakında", {a["name"]: a["status"] for a in st["ajanlar"]}["Tarayıcı"] == "Hazır"
      and {a["name"]: a["status"] for a in st["ajanlar"]}["Kodlama Ajanı"] == "Yakında")
check("ajan planı onay bekliyor görünür", {a["name"]: a["status"] for a in st["ajanlar"]}["Ajan Modu"] == "Plan onayı bekliyor")
check("hafıza sayısı", st["hafiza"]["count"] == 0 and st["hafiza"]["turns"] == 1)

# ---- hata yalıtımı + eklenebilirlik
state.PROVIDERS["bozuk"] = lambda c: 1 / 0
state.provider("yeni")(lambda c: {"merhaba": 1})
st2 = state.build_state(ctx)
check("bozuk sağlayıcı yalnızca kendini boşaltır", st2["bozuk"] is None and "bozuk" in st2["hatalar"] and st2["sistem"] and st2["yeni"] == {"merhaba": 1})
del state.PROVIDERS["bozuk"], state.PROVIDERS["yeni"]

# ---- XSS: dinamik veri yalnızca textContent ile yazılır
js = open(os.path.join(os.path.dirname(server.__file__), "static", "app.js"), encoding="utf-8").read()
check("app.js: innerHTML yalnızca sayısal ölçerde (1 kez)", js.count("innerHTML") == 1 and "stroke-dasharray" in js.split("innerHTML")[1][:200])
check("app.js: eval/document.write yok", "eval(" not in js and "document.write" not in js)
check("etkinlik başlığındaki HTML ham metin kalır", "<img src=x" in json.dumps(st["ajanda"], ensure_ascii=False))
check("harici adres yok (ağsız çalışır)", "http://" not in js.replace("http://www.w3.org/2000/svg", "") and "https://" not in js
      and "//cdn" not in open(os.path.join(os.path.dirname(server.__file__), "static", "index.html"), encoding="utf-8").read())

# ---- takvim/görev düğmeleri (kimlikle)
def post(path, body):
    s_, b_ = req(d, "POST", path, body)
    return s_, json.loads(b_)


s_, r = post("/api/agenda", {"op": "add_task", "title": "  Panodan   görev ", "due": "", "priority": "yüksek"})
snap = agenda.snapshot()
tid = next(t["id"] for t in snap["all_tasks"] if t["title"].startswith("Panodan"))
check("panodan görev ekleme (başlık temizlenir, öncelik)", r["ok"] and next(t for t in snap["all_tasks"] if t["id"] == tid)["priority"] == "yüksek")
check("görev bitir", post("/api/agenda", {"op": "done_task", "id": tid})[1]["ok"] and all(t["id"] != tid for t in agenda.snapshot()["all_tasks"]))
check("olmayan görev hata verir", post("/api/agenda", {"op": "delete_task", "id": 99999})[1]["ok"] is False)
check("geçersiz tarih reddedilir", post("/api/agenda", {"op": "add_task", "title": "x", "due": "yarın"})[1]["ok"] is False)
check("boş başlık reddedilir", post("/api/agenda", {"op": "add_task", "title": "   "})[1]["ok"] is False)
check("id sayı değilse hata (çökmez)", post("/api/agenda", {"op": "done_task", "id": "abc"})[1]["ok"] is False)
tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
r = post("/api/agenda", {"op": "add_event", "title": "Diş randevusu", "date": tomorrow, "time": "10:30"})[1]
ev = next(e for e in agenda.snapshot()["events"] if e["title"] == "Diş randevusu")
check("panodan etkinlik ekleme", r["ok"] and ev["date"] == tomorrow and ev["time"] == "10:30")
check("etkinlik silme", post("/api/agenda", {"op": "cancel_event", "id": ev["id"]})[1]["ok"] and all(e["title"] != "Diş randevusu" for e in agenda.snapshot()["events"]))
check("geçmiş saate etkinlik reddedilir", post("/api/agenda", {"op": "add_event", "title": "x", "date": "2020-01-01", "time": "10:00"})[1]["ok"] is False)
check("bilinmeyen agenda işlemi", post("/api/agenda", {"op": "drop_all"})[1]["ok"] is False)
check("anahtarsız agenda/conv 403", req(d, "POST", "/api/agenda", {"op": "add_task"}, token=False)[0] == 403
      and req(d, "GET", "/api/conv", token=False)[0] == 403)

# ---- konuşma günlüğü: kayıt, arama, silme, saklama
import convlog  # noqa: E402

convlog.clear()
ui_state.add_turn("sen", "İstanbul'da hava nasıl")
ui_state.add_turn("jarvis", "Hava açık, 18 derece.")
ui_state.add_turn("sen", "saat kaç")
s_, r = req(d, "GET", "/api/conv")
r = json.loads(r)
check("add_turn kalıcı günlüğe yazar", r["total"] == 3 and r["items"][0]["text"] == "saat kaç")
r = json.loads(req(d, "GET", "/api/conv?q=%C4%B0stanbul")[1])
check("arama Türkçe büyük/küçük harf duyarsız (İstanbul/istanbul)", len(r["items"]) == 1)
r = json.loads(req(d, "GET", "/api/conv?q=" + "hava")[1])
check("arama birden çok eşleşme", len(r["items"]) == 2)
first = json.loads(req(d, "GET", "/api/conv")[1])["items"][-1]
check("tek kayıt silme", post("/api/conv", {"op": "delete", "id": first["id"]})[1]["ok"] and convlog.count() == 2)
old = {"id": 1, "ts": __import__("time").time() - 40 * 86400, "who": "sen", "text": "eski kayıt"}
with open(convlog._p(), "a", encoding="utf-8") as f:
    f.write(json.dumps(old, ensure_ascii=False) + "\n")
check("varsayılan 30 gün: eski kayıt otomatik silinir", convlog.prune(force=True) == 1 and convlog.count() == 2)
with open(convlog._p(), "a", encoding="utf-8") as f:
    f.write(json.dumps(old, ensure_ascii=False) + "\n")
check("süre 0 (süresiz): eski kayıt kalır", post("/api/conv", {"op": "retention", "days": 0})[1]["days"] == 0 and convlog.count() == 3)
post("/api/conv", {"op": "retention", "days": 7})
check("süre 7 güne inince eski silinir", convlog.count() == 2 and convlog.retention_days() == 7)
today = __import__("time").strftime("%Y-%m-%d")
check("güne göre silme", post("/api/conv", {"op": "delete_day", "day": today})[1]["n"] == 2 and convlog.count() == 0)
ui_state.add_turn("sen", "a")
check("tümünü sil", post("/api/conv", {"op": "clear"})[1]["n"] == 1 and convlog.count() == 0)
check("bozuk işlem çökertmez", post("/api/conv", {"op": "delete", "id": "x"})[1]["ok"] is False)
post("/api/conv", {"op": "retention", "days": 30})
ui_state.add_turn("sen", "sohbet satırı")
st3 = json.loads(req(d, "GET", "/api/state")[1])
check("durum: konuşma günlüğü son mesajlar + saklama süresi", st3["konusma"]["recent"][-1]["text"] == "sohbet satırı" and st3["konusma"]["retention"] == 30)

# ---- sohbet listesi (gün/saat) ve tek sohbetin geçmişi
import time as _t  # noqa: E402

convlog.clear()
base = _t.time() - 3 * 86400
rows = [(0, "sen", "yarın toplantı ekle"), (10, "jarvis", "Ekledim."), (60, "sen", "hava nasıl"),          # sohbet 1
        (7200, "sen", "sistem durumu"), (7205, "jarvis", "İşlemci yüzde 10."),                           # sohbet 2 (2 saat sonra)
        (12000, "sen", "teşekkürler")]                                                                  # 30 dk'dan uzun boşluk -> sohbet 3
with open(convlog._p(), "w", encoding="utf-8") as f:
    for i, (dt_, w, t) in enumerate(reversed(rows)):  # dosya sırası karışık olsa da doğru bölünmeli
        f.write(json.dumps({"id": i + 1, "ts": base + dt_, "who": w, "text": t}, ensure_ascii=False) + "\n")
ss = json.loads(req(d, "GET", "/api/sessions")[1])["sessions"]
check("30 dk'dan uzun boşluk yeni sohbet başlatır (3 sohbet, yeniden eskiye)", [x["count"] for x in ss] == [1, 2, 3])
check("sohbet başlığı ilk kullanıcı mesajı", ss[2]["title"] == "yarın toplantı ekle" and ss[1]["title"] == "sistem durumu")
check("sohbet saati/gün bilgisi (start/end)", abs(ss[2]["start"] - base) < 1 and abs(ss[2]["end"] - (base + 60)) < 1)
ss_q = json.loads(req(d, "GET", "/api/sessions?q=HAVA")[1])["sessions"]
check("sohbet araması: eşleşen sohbet + satır özeti", len(ss_q) == 1 and ss_q[0]["snippet"] == "hava nasıl")
r = json.loads(req(d, "GET", f"/api/conv?from={ss[2]['start']}&to={ss[2]['end']}")[1])
check("sohbete tıklayınca o sohbetin mesajları (eskiden yeniye)", [m["text"] for m in r["items"]] == ["yarın toplantı ekle", "Ekledim.", "hava nasıl"])
check("bozuk aralık 400", req(d, "GET", "/api/conv?from=abc")[0] == 400)
check("sohbeti sil (aralık)", post("/api/conv", {"op": "delete_range", "from": ss[2]["start"], "to": ss[2]["end"]})[1]["n"] == 3
      and [x["count"] for x in json.loads(req(d, "GET", "/api/sessions")[1])["sessions"]] == [1, 2])
convlog.clear()

# ---- araçlar listesi, sıcaklık
from skills import load_skills  # noqa: E402

brain.tools = load_skills()
brain.tool_stats = {"get_time": 2}
state._cache.clear()
st4 = json.loads(req(d, "GET", "/api/state")[1])
tools = {a["name"]: a for a in st4["araclar"]}
check("araçlar: ad, açıklama, kategori, kullanım sayısı", len(tools) >= 30 and tools["get_time"]["uses"] == 2 and tools["get_time"]["desc"]
      and tools["agenda_add"]["category"] == "Takvim ve görevler" and tools["get_system_status"]["category"] == "Donanım")
check("araçlar: kategorisiz 'Diğer' yok", all(a["category"] != "Diğer" for a in st4["araclar"]))
from skills import weather  # noqa: E402

weather._get = lambda url: ({"results": [{"latitude": 1, "longitude": 2}]} if "geocoding" in url else {"current": {"temperature_2m": 17.6}})
check("hava: yalnızca derece (tam sayı)", weather.current_temp() == 18)
weather._get = lambda url: (_ for _ in ()).throw(OSError("ağ yok"))
check("hava: ağ yoksa None (pano '—' gösterir)", weather.current_temp() is None)

d.stop()
# yavaş ağ: pano durumu ağı beklemez (bağlantısı olmayan/yavaş internette istek takılmasın)
import threading as _th  # noqa: E402
import time as _t  # noqa: E402
_gate = _th.Event()
state._cache.clear()
weather._get = lambda url: (_gate.wait(5), {"results": [{"latitude": 1, "longitude": 2}]} if "geocoding" in url else {"current": {"temperature_2m": 20.4}})[1]
state._online = lambda: (_gate.wait(5), True)[1]
_t0 = _t.time()
_slow = state.build_state(types.SimpleNamespace(brain=None))
check("yavaş ağda pano durumu beklemez (<1 sn), sıcaklık boş", _t.time() - _t0 < 1.0 and _slow["alt"]["temp"] == "")
_gate.set()
_t.sleep(0.5)
state._cache.pop("temp", None)
_fast = state.build_state(types.SimpleNamespace(brain=None))
_t.sleep(0.5)
_fast = state.build_state(types.SimpleNamespace(brain=None))
check("ağ gelince sıcaklık arka planda dolar", _fast["alt"]["temp"] == "20°C", str(_fast["alt"]))

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
