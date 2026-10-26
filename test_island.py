"""Üst kenar adası testleri: görünüm mantığı, onay kimliği, eski soruya cevap reddi, anahtar, uçtan uca onay (gerçek Brain,
sahte araç), Qt duman testi (ekransız). Gerçek ekranda görünüm/konum [HW] doğrulaması ayrıca kullanıcıdan istenir."""
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
import island  # noqa: E402
import ui_state  # noqa: E402
from dashboard import server, state  # noqa: E402
from skills import _confirm as confirm  # noqa: E402

HERE = Path(__file__).resolve().parent
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
      island.ACTIVE_PX > 2 * island.MASCOT_PX and "if animate and not REDUCED" in (HERE / "island.py").read_text(encoding="utf-8"))
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

# ---------------------------------------------------------------- uçtan uca: gerçek Brain, sahte riskli araç
import brain as B  # noqa: E402

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
    p = subprocess.run([sys.executable, str(HERE / "island.py"), url, "--parent", str(dead.pid)], capture_output=True, text=True, timeout=30, env=env)
    check("Qt adası ekransız açılır, çizer ve Jarvis yokken kendiliğinden kapanır", p.returncode == 0 and "Traceback" not in p.stderr, p.stderr[-400:])
    confirm.cancel()
    d3.stop()
else:
    print("ATLA Qt yok: duman testi atlandı")

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
