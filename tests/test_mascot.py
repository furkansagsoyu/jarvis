"""Çekirdek maskotu testleri: durum -> data-state eşlemesi, pano/ada anlık durumunda maskot, SVG'nin sunulması ve sayfaya
gömülmeye uygunluğu (kapsamlı kurallar, çakışmayan adlar, prefers-reduced-motion), adadaki durağan sürüm."""
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri

import http.client
import os
import re
import sys
import tempfile
import time
import types
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
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


M = ui_state.mascot_state
STATES = ("idle", "listening", "thinking", "speaking", "alert", "error")
check("eşleme: bekleme/sessiz/kapalı/başlıyor -> idle", all(M(s) == "idle" for s in ("listening", "muted", "stopped", "starting")))
check("eşleme: uyandı/kayıt -> listening, düşünüyor -> thinking, konuşuyor -> speaking",
      M("recording") == "listening" and M("thinking") == "thinking" and M("speaking") == "speaking")
check("eşleme: bekleyen onay/plan -> alert (konuşurken bile)", M("speaking", pending=True) == "alert" and M("listening", pending=True) == "alert")
now = time.time()
check("eşleme: yeni hata -> error (onaydan da önce), süre geçince normale döner",
      M("thinking", True, now - 1, now) == "error" and M("thinking", False, now - ui_state.ERROR_SHOW - 1, now) == "thinking" and M("error") == "error")
check("eşleme hiçbir durumda tanımsız değer üretmez", all(M(s, p) in STATES for s in [*ui_state.STATES, "x"] for p in (False, True)))

# pano ve ada anlık durumu
ui_state.reset()
ui_state.set_state("recording")
ctx = types.SimpleNamespace(brain=types.SimpleNamespace(team=types.SimpleNamespace(state="idle"), agent=types.SimpleNamespace(state="idle")))
check("pano durumu maskotu taşır (recording -> listening)", state._durum(ctx)["mascot"] == "listening")
check("ada anlık durumu maskotu taşır", state.island_snapshot(ctx)["mascot"] == "listening")
confirm.request("deneme işlemi.", lambda: "ok")
check("onay beklerken pano ve ada maskotu alert", state._durum(ctx)["mascot"] == "alert" and state.island_snapshot(ctx)["mascot"] == "alert")
confirm.cancel()
ui_state.flag_error()
check("hata işaretinden sonra maskot error", state._durum(ctx)["mascot"] == "error")
ui_state.reset()
ui_state.set_muted(True)
check("sessizde maskot idle", state._durum(ctx)["mascot"] == "idle")
ui_state.set_muted(False)

# SVG: tek kaynak assets/, satır içi gömülmeye uygun
svg_text = (HERE / "assets" / "cekirdek.svg").read_text(encoding="utf-8")
root = ET.fromstring(svg_text)
check("SVG geçerli XML, kök sınıf 'cekirdek', data-state=idle", root.get("class") == "cekirdek" and root.get("data-state") == "idle")
css = svg_text[svg_text.index("<style>"):svg_text.index("</style>")]
rules = [r.strip() for r in re.findall(r"(?:^|[{}])([^{}]*){", css.replace("<style>", ""))
         if r.strip() and not re.match(r"^(@|\d|to\b|from\b)", r.strip())]   # @keyframes/@media önekleri ve kare yüzdeleri kural değil
check("tüm CSS kuralları maskot kapsamında (sayfadaki svg/ikonları etkilemez)", all(".cekirdek" in r for r in rules), str([r for r in rules if ".cekirdek" not in r]))
check("sayfayla çakışan adlar yok (--bg, .dots, genel animasyon adları)",
      not re.search(r"--bg\b|\.dots\b|@keyframes (?!ck-)", css) and 'id="halo"' not in svg_text and 'id="m"' not in svg_text)
check("altı durumun hepsi tanımlı, prefers-reduced-motion korunuyor",
      all(f'data-state="{s}"' in css for s in STATES if s != "idle") and "prefers-reduced-motion:reduce" in css)
check("tema rengi dışarıdan verilebilir (--ck-tema)", "var(--ck-tema," in css)

# pano: SVG sunulur, sayfa satır içi gömer
d = server.Dashboard(ctx, lambda t, silent=False: None, port=8996)
d.start()
c = http.client.HTTPConnection("127.0.0.1", d.port, timeout=5)
c.request("GET", "/static/cekirdek.svg", headers={"Host": f"127.0.0.1:{d.port}"})
r = c.getresponse()
body = r.read().decode("utf-8")
c.close()
d.stop()
check("pano /static/cekirdek.svg'yi assets/'ten sunar (kopya yok)", r.status == 200 and "image/svg+xml" in r.getheader("Content-Type") and body == svg_text
      and not (HERE / "dashboard" / "static" / "cekirdek.svg").exists())
js = (HERE / "dashboard" / "static" / "app.js").read_text(encoding="utf-8")
html = (HERE / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")
check("pano maskotu satır içi gömer (img değil) ve data-state'i günceller",
      'id="mascot"' in html and "DOMParser().parseFromString(t, \"image/svg+xml\")" in js and "box.replaceChildren(mascotSvg)" in js and "mascotSvg.dataset.state" in js and "setMascot(d.mascot)" in js and "<img" not in html.split('id="mascot"')[1][:80])

# ada: durağan maskot
check("ada görünümü maskotu taşır; onayda alert, bağlantı yokken error",
      island.view({"state": "thinking", "label": "Düşünüyor", "mascot": "thinking"})["mascot"] == "thinking"
      and island.view({"state": "x", "kind": "confirm", "id": "c1", "question": "q", "mascot": "idle"})["mascot"] == "alert"
      and island.view(None)["mascot"] == "error" and island.view({"state": "x", "mascot": "<script>"})["mascot"] == "idle")
ok = True
for s in STATES:
    try:
        ET.fromstring(island.mascot_svg(s))
    except ET.ParseError:
        ok = False
check("adadaki durağan maskot her durumda geçerli SVG; alert/error kendi rengiyle",
      ok and b"#f59e0b" in island.mascot_svg("alert") and b"#f43f5e" in island.mascot_svg("error") and b"#22d3ee" in island.mascot_svg("idle"))
# ada animasyonu: kareler zamanla değişir, değerler cekirdek.svg @keyframes ile aynı
F = island.mascot_svg
frames = {st: {F(st, t / 15) for t in range(0, 75)} for st in STATES}   # 5 sn, 15 kare/sn
check("adada her durum hareketli (5 sn'de birden çok farklı kare)", all(len(v) > 3 for v in frames.values()), str({k: len(v) for k, v in frames.items()}))


def num(svg: bytes, pat: str) -> list[float]:
    return [float(x) for x in re.findall(pat, svg.decode())]


eyes = lambda t: num(F("idle", t), r'<rect[^>]*scale\(1 ([\d.]+)\)')  # noqa: E731
check("göz kırpma: 5 sn döngünün %95'inde kapalı (.1), başka anda açık (1)", eyes(4.75) == [0.1, 0.1] and eyes(1.0) == [1.0, 1.0])
check("dinlerken gözler büyük (1,15), dalga ölçeği .6->1,7", eyes(0) and num(F("listening", 0.0), r'<rect[^>]*scale\(1 ([\d.]+)\)') == [1.15, 1.15]
      and num(F("listening", 0.0), r'stroke-width="4"[^>]*scale\(([\d.]+)\)')[0] == 0.6 and num(F("listening", 1.59), r'stroke-width="4"[^>]*scale\(([\d.]+)\)')[0] > 1.65)
mouth = [num(F("speaking", t / 100), r'<path[^>]*scale\(1 ([\d.]+)\)')[0] for t in range(0, 35)]
check("konuşma: ağız .35 sn'de .3 -> 1,6 -> .3", min(mouth) == 0.3 and max(mouth) > 1.55)
check("düşünürken halka hızlı döner (2,5 sn), boştayken yavaş (24 sn)",
      num(F("thinking", 1.25), r'rotate\(([\d.]+)\)')[0] == 180.0 and num(F("idle", 12.0), r'rotate\(([\d.]+)\)')[0] == 180.0)
shake = lambda t: num(F("error", t, 0.0), r'<g transform="translate\((-?[\d.]+) 0\)')[0]  # noqa: E731
check("hata: yalnızca girişte .8 sn titrer, sonra durur", abs(shake(0.1)) > 4 and shake(2.0) == 0.0)
ok = True
for st in STATES:
    for t in range(0, 30):
        try:
            ET.fromstring(F(st, t / 7, 0.0))
        except ET.ParseError:
            ok = False
check("tüm animasyon kareleri geçerli SVG", ok)
check("hareket azaltma: JARVIS_REDUCED_MOTION=1 iken kare zamanlayıcısı başlamaz",
      "if face is not None and not REDUCED:" in (HERE / "desktop" / "island.py").read_text(encoding="utf-8") and 'JARVIS_REDUCED_MOTION' in (HERE / "desktop" / "island.py").read_text(encoding="utf-8"))

try:
    from qtpy.QtSvg import QSvgRenderer
    check("Qt SVG çizicisi maskot karelerini yükler", all(QSvgRenderer(island.mascot_svg(s, t / 3, 0.0)).isValid() for s in STATES for t in range(9)))
except Exception:  # noqa: BLE001
    print("ATLA QtSvg yok")

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
