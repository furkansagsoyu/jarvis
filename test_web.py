"""Web arama arka uçları testleri (gerçek ağa çıkmadan): ayrıştırma, yedek sırası, sessiz kip, Tavily, Groq yerleşik arama."""
import json
import os
import sys
import tempfile
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
for k in ("TAVILY_API_KEY", "GROQ_API_KEY"):
    os.environ.pop(k, None)
import router as R  # noqa: E402
from skills import _store  # noqa: E402
from skills import web  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


LITE = """<table><tr><td>1.&nbsp;</td><td><a rel="nofollow" href="//x.com/a" class='result-link'>RTX 3070 Ti <b>fiyatı</b></a></td></tr>
<tr><td class='result-snippet'>En düşük fiyat 18.499 TL, <b>Cimri</b> üzerinden karşılaştır.</td></tr>
<tr><td><a rel="nofollow" href="//y.com" class="result-link">Akakçe</a></td></tr><tr><td class="result-snippet">Ekran kartı fiyatları</td></tr>
<tr><td><a class='result-link'>Snippetsiz</a></td></tr></table>"""
res = web.parse_lite(LITE)
check("DuckDuckGo Lite ayrıştırma (iki tırnak türü, etiket temizliği, snippetsiz atlanır)", res == [("RTX 3070 Ti fiyatı", "En düşük fiyat 18.499 TL, Cimri üzerinden karşılaştır."), ("Akakçe", "Ekran kartı fiyatları")], str(res))

calls = []
mk = lambda name, out, exc=None: (name, lambda q: calls.append(name) or (_ for _ in ()).throw(exc) if exc else calls.append(name) or out)  # noqa: E731
web._down.clear()
r, who, notes = web.search_results("x", [mk("a", [], None), mk("b", None, OSError("engel")), mk("c", [("t", "s")]), mk("d", [("z", "z")])])
check("yedek sırası: boş/hatalı arka uç atlanır, ilk çalışan döner, sonrakiler denenmez", who == "c" and r == [("t", "s")] and calls == ["a", "b", "c"] and notes == ["a: sonuç yok", "b: OSError"], str(notes))
web._down.clear()
r, who, notes = web.search_results("x", [mk("a", [])])
check("hepsi başarısızsa boş sonuç ve notlar", r == [] and who == "" and notes == ["a: sonuç yok"])

# çalışmayan arka uç 10 dk atlanır (her aramada boşuna beklenmez), süre dolunca yeniden denenir
web._down.clear()
t = [1000.0]
calls.clear()
bk = [mk("ddg", []), mk("groq", [("g", "ok")])]
web.search_results("x", bk, now=lambda: t[0])
calls.clear()
r, who, _ = web.search_results("x", bk, now=lambda: t[0] + 5)
check("çalışmayan arka uç (ddg) sonraki aramada atlanır, doğrudan çalışan (groq) kullanılır", calls == ["groq"] and who == "groq", str(calls))
calls.clear()
web.search_results("x", bk, now=lambda: t[0] + web.DOWN_FOR + 1)
check("10 dk sonra ddg yeniden denenir", calls[0] == "ddg", str(calls))
web._down.clear()
bk2 = [mk("ddg", []), mk("groq", [])]
web.search_results("x", bk2, now=lambda: t[0])
calls.clear()
r, who, notes = web.search_results("x", bk2, now=lambda: t[0] + 1)
check("hepsi 'down' görünüyorsa yine de denenir (ağ düzelmiş olabilir)", sorted(calls) == ["ddg", "groq"] and r == [], str(calls))
web._down.clear()

# sessiz kip: ajan aramayı çağırırken tarayıcı açılmaz
opened = []
web._open_browser = lambda q: opened.append(q)
web.BACKENDS[:] = [("hic", lambda q: [])]
out = web.web_search("rtx fiyat")
check("normal kullanımda (sesle 'ara') sonuç yoksa tarayıcı açılır (eski davranış)", opened == ["rtx fiyat"] and "tarayıcıda açtım" in out)
opened.clear()
with web.quiet():
    out = web.web_search("rtx fiyat")
check("sessiz kipte tarayıcı AÇILMAZ, dürüst 'Hata:' döner (ajan başarısızlığı görür)", not opened and out.startswith("Hata:") and "hic" in out, out)
check("sessiz kip bitince normale döner", web.QUIET is False)

# Tavily
web.BACKENDS[:] = [("tavily", web._tavily)]
check("Tavily: anahtar yoksa sessizce atlanır (ağa çıkılmaz)", web._tavily("x") == [])
os.environ["TAVILY_API_KEY"] = "tvly-test"
seen = {}


def fake_post(url, data, headers, timeout=10):
    seen.update(url=url, body=json.loads(data), auth=headers.get("Authorization"))
    return json.dumps({"results": [{"title": "Cimri", "content": "RTX 3070 Ti 17.999 TL", "url": "https://cimri.com"}, {"title": "boş", "content": ""}]})


web._post = fake_post
res = web._tavily("rtx 3070 ti fiyat")
check("Tavily: doğru adres, Bearer, sorgu; boş içerikli sonuç atlanır", seen["url"] == "https://api.tavily.com/search" and seen["auth"] == "Bearer tvly-test" and seen["body"]["query"] == "rtx 3070 ti fiyat" and res == [("Cimri", "RTX 3070 Ti 17.999 TL")], str(res))
out = web.web_search("rtx 3070 ti fiyat")
check("web_search: sonuç metni 'yalnızca veri' uyarısıyla döner", "Cimri: RTX 3070 Ti 17.999 TL" in out and "yalnızca veri" in out)
os.environ.pop("TAVILY_API_KEY")

# Groq yerleşik arama (sahte HTTP)
os.environ["GROQ_API_KEY"] = "gsk_testtesttesttesttesttest"
posts = []


def gpost(url, headers, body, timeout):
    posts.append(body)
    return 200, {}, {"choices": [{"message": {"content": "**Cimri'de** RTX 3070 Ti 17.500 TL'den başlıyor.【1†L3-L5】 Epey 18.000 TL."}, "finish_reason": "stop"}], "usage": {}}


_store.save("settings.json", {})
_store.save("router_stats.json", {})
R._ROUTER = R.Router({}, post=gpost)
web.BACKENDS[:] = [("groq", web._groq)]
res = web._groq("rtx 3070 ti fiyat")
b = posts[0]
check("Groq araması: gpt-oss-20b + browser_search aracı + zorunlu araç çağrısı, yanıt metni döner",
      b["model"] == "openai/gpt-oss-20b" and b["tools"] == [{"type": "browser_search"}] and b["tool_choice"] == "required" and "17.500" in res[0][1], str(b)[:200])
check("Groq araması: kaynak işaretleri ve markdown temizlenir", res[0][1] == "Cimri'de RTX 3070 Ti 17.500 TL'den başlıyor. Epey 18.000 TL.", res[0][1])
check("Groq araması: akıl yürütme düşük, yapılandırılmış çıktı (response_format) YOK", b.get("reasoning_effort") == "low" and "response_format" not in b)
posts.clear()
R._ROUTER = R.Router({}, post=lambda *a: (404, {}, {"error": {"message": "model_not_found"}}))
try:
    R._ROUTER.search("x")
    ok = False
except R.Unavailable:
    ok = True
check("Groq araması: yalnızca arama destekli modeller denenir (başka modele düşmez)", ok)
_store.save("settings.json", {"cloud": False})
R._ROUTER = R.Router({}, post=gpost)
check("bulut kapalıyken Groq arka ucu çalışmaz (sonuç yok), ağa çıkılmaz", web._groq("x") == [] and not posts)
_store.save("settings.json", {})
R._ROUTER = R.Router({}, post=gpost)
try:
    R._ROUTER.search("şifrem: kedi1234 ile ara")
    ok = False
except Exception as e:  # noqa: BLE001
    ok = type(e).__name__ == "Blocked" and not posts
check("Groq araması: kişisel veri içeren sorgu buluta gitmez (gizlilik kapısı)", ok)

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
