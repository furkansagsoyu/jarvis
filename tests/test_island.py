"""Üst kenar adası testleri: görünüm mantığı, onay kimliği, eski soruya cevap reddi, anahtar, uçtan uca onay (gerçek Brain,
sahte araç), Qt duman testi (ekransız). Gerçek ekranda görünüm/konum [HW] doğrulaması ayrıca kullanıcıdan istenir."""
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri

import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
try:
    import ollama  # noqa: F401
except ImportError:
    sys.modules["ollama"] = types.ModuleType("ollama")
from desktop import island  # noqa: E402
from desktop import ui_state  # noqa: E402
from dashboard import server, state  # noqa: E402
from skills import _confirm as confirm  # noqa: E402

HERE = Path(__file__).resolve().parent.parent   # depo kökü
bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


def req(d, method, path, body=None, token=True):
    c = http.client.HTTPConnection("127.0.0.1", d.port, timeout=5)
    h = {"Host": f"127.0.0.1:{d.port}", "Content-Type": "application/json"}
    if token:
        h["X-Token"] = d.token
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse()
    out = r.read()
    c.close()
    return r.status, (json.loads(out) if out else {})


# ---------------------------------------------------------------- görünüm (Qt'siz)
v = island.view({"state": "listening", "label": "Dinliyor", "kind": "", "id": ""})
check("boşta: küçük hap, düğme yok, yeşil", not v["buttons"] and v["width"] == island.NARROW and v["text"] == "Dinliyor" and v["color"] == island.COLORS["listening"])
v = island.view({"state": "thinking", "label": "Düşünüyor", "kind": "confirm", "question": "a.txt çöpe atılacak.", "id": "c7", "left": 42})
check("onay: geniş, Evet/Hayır, soru ve kalan süre", v["buttons"] and v["width"] == island.WIDE and v["qid"] == "c7" and v["title"] == "Onay bekliyor · 42 sn" and "çöpe" in v["text"])
v = island.view({"state": "speaking", "label": "Konuşuyor", "kind": "plan", "question": "x " * 200, "id": "pteam1", "left": 0})
check("plan: başlık 'Plan onayı', uzun soru kısaltılır", v["title"] == "Plan onayı" and len(v["text"]) <= island.MAX_Q and v["text"].endswith("…"))
check("uyanınca/düşünürken/konuşurken ada büyür (active), maskot ortada; boşta küçük hap (compact)",
      all(island.view({"state": st, "label": "X", "kind": "", "id": "", "mascot": m})["mode"] == "active"
          and island.view({"state": st, "label": "X", "kind": "", "id": "", "mascot": m})["width"] == island.ACTIVE_W
          for st, m in (("recording", "listening"), ("thinking", "thinking"), ("speaking", "speaking")))
      and island.view({"state": "listening", "label": "Dinliyor", "kind": "", "id": "", "mascot": "idle"})["mode"] == "compact")
check("onay her zaman soru + düğmeli görünüm (konuşurken bile)",
      island.view({"state": "speaking", "kind": "confirm", "id": "c3", "question": "q", "mascot": "alert"})["mode"] == "confirm"
      and island.view(None)["mode"] == "compact")
check("etkin halde büyük maskot (ACTIVE_PX > MASCOT_PX), geçiş animasyonlu ve hareket azaltmada kapalı",
      island.ACTIVE_PX > 2 * island.MASCOT_PX and "if animate and not REDUCED" in (HERE / "desktop" / "island.py").read_text(encoding="utf-8"))
check("kimliksiz bekleyen durum düğme göstermez", not island.view({"state": "listening", "kind": "confirm", "id": ""})["buttons"])
check("Jarvis'e ulaşılamıyor: gri, düğmesiz", island.view(None)["color"] == island.COLORS["stopped"] and not island.view(None)["buttons"])
for url in ("http://example.com:8765/?t=x", "http://192.168.1.5:8765/?t=x"):
    try:
        island.Client(url)
        ok = False
    except ValueError:
        ok = True
    check(f"ada yalnızca yerel sunucuya bağlanır ({url.split('/')[2]})", ok)
check("anahtar adresten okunur", island.Client("http://127.0.0.1:8765/?t=abc").token == "abc")

# ---------------------------------------------------------------- onay kimliği
confirm.cancel()
check("bekleyen yokken bilgi yok", confirm.pending_info() is None)
confirm.request("a.txt çöpe atılacak.", lambda: "atıldı")
i1 = confirm.pending_info()
confirm.request("b.txt çöpe atılacak.", lambda: "atıldı")
i2 = confirm.pending_info()
check("her bekleyen işlem yeni kimlik alır; bilgi yalnızca görüntü (run yok)", i2["id"] == i1["id"] + 1 and set(i2) == {"id", "text", "left"} and i2["text"] == "b.txt çöpe atılacak.")
check("pending_info onay VERMEZ", confirm.has_pending())
confirm.cancel()

# ---------------------------------------------------------------- anlık durum
ui_state.reset()
ui_state.set_state("listening")
team = types.SimpleNamespace(state="idle", plan_expires=0.0)
agent = types.SimpleNamespace(state="idle", plan_expires=0.0)
ctx = types.SimpleNamespace(brain=types.SimpleNamespace(team=team, agent=agent))
s0 = state.island_snapshot(ctx)
check("boşta anlık durum: kind boş", s0["kind"] == "" and s0["state"] == "listening" and s0["label"] == "Dinliyor")
confirm.request("a.txt çöpe atılacak.", lambda: "atıldı")
s1 = state.island_snapshot(ctx)
check("onay bekliyor: kind confirm, soru, id", s1["kind"] == "confirm" and s1["question"] == "a.txt çöpe atılacak." and s1["id"].startswith("c") and 0 < s1["left"] <= confirm.TTL)
confirm.cancel()
ui_state.add_turn("jarvis", "Ekip planım şöyle. 1. Araştırma. Başlayayım mı?")
team.state, team.plan_expires = "plan", time.time() + 100
s2 = state.island_snapshot(ctx)
check("ekip planı: kind plan, soru son Jarvis cümlesi", s2["kind"] == "plan" and "Başlayayım mı" in s2["question"] and s2["id"].startswith("pteam"))
team.plan_expires = time.time() - 1
check("süresi dolmuş plan gösterilmez", state.island_snapshot(ctx)["kind"] == "")
team.state = "idle"
ui_state.set_muted(True)
check("sessizdeyken durum 'muted'", state.island_snapshot(ctx)["state"] == "muted")
ui_state.set_muted(False)
check("pano 'pending' bayrağı ekip planını da sayar",
      (team.__setattr__("state", "plan") or state._durum(ctx)["pending"]) is True)
team.state = "idle"

# ---------------------------------------------------------------- sunucu uçları
sent = []
d = server.Dashboard(ctx, lambda t, silent=False: sent.append(t), port=8960)
d.start()
code, _ = req(d, "GET", "/api/island", token=False)
code2, _ = req(d, "POST", "/api/island/answer", {"answer": "yes", "id": "c1"}, token=False)
check("anahtarsız ada uçları reddedilir (403)", code == 403 and code2 == 403 and not sent)
confirm.request("a.txt çöpe atılacak.", lambda: "atıldı")
code, snap = req(d, "GET", "/api/island")
check("GET /api/island: soru ve id", code == 200 and snap["kind"] == "confirm" and snap["id"])
_, r = req(d, "POST", "/api/island/answer", {"answer": "evet", "id": snap["id"]})
check("bozuk cevap reddedilir", not r["ok"] and not sent)
confirm.request("b.txt çöpe atılacak.", lambda: "atıldı")   # soru değişti
_, r = req(d, "POST", "/api/island/answer", {"answer": "yes", "id": snap["id"]})
check("ESKİ soruya Evet yeni işlemi onaylamaz (id uyuşmaz)", not r["ok"] and "güncel" in r["error"] and not sent and confirm.has_pending())
_, snap = req(d, "GET", "/api/island")
_, r = req(d, "POST", "/api/island/answer", {"answer": "no", "id": snap["id"]})
check("güncel soruya Hayır: sesli cevapla aynı yoldan 'hayır' iletilir", r["ok"] and sent == ["hayır"])
confirm.cancel()
_, r = req(d, "POST", "/api/island/answer", {"answer": "yes", "id": snap["id"]})
check("bekleyen yokken cevap iletilmez", not r["ok"] and sent == ["hayır"])
check("onay kendisi sunucuda VERİLMEZ (yalnızca metin iletilir)", "approve" not in Path(server.__file__).read_text())

# ---------------------------------------------------------------- Ayarlar > ADA
check("ada ayarları varsayılanı", ui_state.island_settings() == ui_state.ISLAND_DEFAULTS)
_, r1 = req(d, "POST", "/api/cmd", {"island": {"key": "size", "value": "large"}})
_, r2 = req(d, "POST", "/api/cmd", {"island": {"key": "size", "value": "dev"}})
_, r3 = req(d, "POST", "/api/cmd", {"island": {"key": "enabled", "value": "false"}})
_, r4 = req(d, "POST", "/api/cmd", {"island": {"key": "shell", "value": True}})
code5, _ = req(d, "POST", "/api/cmd", {"island": {"key": "size", "value": "small"}}, token=False)
check("API: geçerli ayar kaydedilir; geçersiz değer/tip/anahtar ve anahtarsız istek reddedilir",
      r1["ok"] and not r2["ok"] and not r3["ok"] and not r4["ok"] and code5 == 403 and ui_state.island_settings()["size"] == "large")
for k, v in (("position", "right"), ("mascot", False), ("on_top", False), ("theme", "amber")):
    ui_state.set_island(k, v)
st_json = json.loads((Path(os.environ["JARVIS_DATA"]) / "settings.json").read_text(encoding="utf-8"))
check("ayarlar settings.json'da kalır (yeniden başlatınca korunur)", st_json["island"] == {"enabled": True, "on_top": False, "mascot": False,
                                                                                      "position": "right", "size": "large", "theme": "amber",
                                                                                      "autohide": True})
check("ada anlık durumu ve pano durumu ayarları taşır", state.island_snapshot(ctx)["cfg"]["position"] == "right" and state._durum(ctx)["island"]["size"] == "large")
ui_state.set_island("theme", "auto")
ui_state.set_theme("violet")
check("tema 'panoyu izle' iken adanın teması panonunki", state.island_snapshot(ctx)["cfg"]["theme"] == "violet")
ui_state.set_theme("cyan")
check("bozuk settings.json ada ayarı varsayılana düşer", (Path(os.environ["JARVIS_DATA"]) / "settings.json").write_text('{"island": {"size": 7, "enabled": "x"}}') and
      ui_state.island_settings() == ui_state.ISLAND_DEFAULTS)
check("konum: üst orta / sol / sağ (ekran kenarından 12 px)",
      island.geometry_for({"position": "center"}, 200, 0, 0, 1920) == (860, 6) and island.geometry_for({"position": "left"}, 200, 0, 0, 1920) == (12, 6)
      and island.geometry_for({"position": "right"}, 200, 0, 0, 1920) == (1708, 6) and island.geometry_for({}, 200, 100, 30, 1000) == (500, 36))
check("boyut: küçük/normal/büyük ölçeği", island.scaled({"size": "small"}, 100) == 85 and island.scaled({}, 100) == 100 and island.scaled({"size": "large"}, 100) == 125)
check("maskot rengi temayı izler; uyarı/hata kendi rengini korur",
      b"#ffb23f" in island.mascot_svg("idle", 0, 0, "amber") and b"#0b78b5" in island.mascot_svg("speaking", 0, 0, "light")
      and b"#f59e0b" in island.mascot_svg("alert", 0, 0, "violet") and b"#f43f5e" in island.mascot_svg("error", 0, 0, "green"))
check("her pano temasının ada paleti var", set(ui_state.THEMES) <= set(island.PALETTES))
check("görünüm ayarları adaya geçer", island.view({"state": "listening", "mascot": "idle", "cfg": {"size": "small"}})["cfg"] == {"size": "small"})
ui_state.set_island("enabled", True)
# otomatik gizlenme: beklemede saklan, "Hey Jarvis"te gel, cevaptan HIDE_AFTER sn sonra yine saklan
SS, H = island.should_show, island.HIDE_AFTER
idle = {"mode": "compact", "mascot": "idle", "cfg": {}}
check("beklemede: son konuşmadan HIDE_AFTER sn sonra saklanır, öncesinde görünür", SS(idle, 100.0, 100.0 + H - 0.1) and not SS(idle, 100.0, 100.0 + H + 0.1))
check("'Hey Jarvis' (dinliyor/düşünüyor/konuşuyor) her zaman görünür", all(SS({"mode": "active", "mascot": m, "cfg": {}}, 0.0, 1e6) for m in ("listening", "thinking", "speaking")))
check("onay sorusu, uyarı ve hata saklı kalmaz (soruyu kaçırmazsın)", SS({"mode": "confirm", "mascot": "alert", "cfg": {}}, 0.0, 1e6)
      and SS({"mode": "compact", "mascot": "error", "cfg": {}}, 0.0, 1e6))
check("'Otomatik gizlen' kapalıysa hep görünür", SS({**idle, "cfg": {"autohide": False}}, 0.0, 1e6))
check("autohide ayarı doğrulanır ve kaydedilir", not ui_state.set_island("autohide", "evet") and ui_state.set_island("autohide", False)
      and ui_state.island_settings()["autohide"] is False and ui_state.set_island("autohide", True))
src = (HERE / "desktop" / "island.py").read_text(encoding="utf-8")
check("kayma: gelirken yaylanır (OutBack), giderken yukarı kayıp gizlenir; hareket azaltmada animasyonsuz",
      "def slide_in" in src and "def slide_out" in src and "curve.OutBack" in src and "curve.InCubic" in src and "if REDUCED:" in src)

# ---------------------------------------------------------------- uçtan uca: gerçek Brain, sahte riskli araç
from core import brain as B  # noqa: E402

done = []
schema = {"type": "function", "function": {"name": "trash_file", "description": "dosyayı çöpe atar",
                                           "parameters": {"type": "object", "properties": {"name": {"type": "string"}}}}}
b = B.Brain(tools={"trash_file": (schema, lambda name="": confirm.request(f"{name} çöpe atılacak.", lambda: done.append(name) or "Çöpe attım."))})
b.tools["trash_file"][1](name="rapor.txt")       # araç bekleyen işlem kaydeder (model değil kullanıcı onaylar)
replies = []
d2 = server.Dashboard(types.SimpleNamespace(brain=b), lambda t, silent=False: replies.append(" ".join(b.reply_stream(t))), port=8970)
d2.start()
_, snap = req(d2, "GET", "/api/island")
_, r = req(d2, "POST", "/api/island/answer", {"answer": "yes", "id": snap["id"]})
check("uçtan uca: adadaki Evet -> Brain 'evet' -> işlem çalışır", r["ok"] and done == ["rapor.txt"] and "Çöpe attım" in replies[-1], str(replies))
d.stop()
d2.stop()

# ---------------------------------------------------------------- Qt duman testi (ekransız)
try:
    import qtpy  # noqa: F401
    have_qt = True
except Exception:  # noqa: BLE001
    have_qt = False
if have_qt:
    d3 = server.Dashboard(ctx, lambda t, silent=False: None, port=8980)
    url = d3.start()
    confirm.request("deneme işlemi.", lambda: "ok")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "DISPLAY": os.environ.get("DISPLAY", ":0")}
    p = subprocess.run([sys.executable, str(HERE / "desktop" / "island.py"), url, "--parent", str(dead.pid)], capture_output=True, text=True, timeout=30, env=env)
    check("Qt adası ekransız açılır, çizer ve Jarvis yokken kendiliğinden kapanır", p.returncode == 0 and "Traceback" not in p.stderr, p.stderr[-400:])
    confirm.cancel()
    d3.stop()
else:
    print("ATLA Qt yok: duman testi atlandı")

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
