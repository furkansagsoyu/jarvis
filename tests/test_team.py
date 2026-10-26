"""Ekip modu (çoklu ajan) testleri: plan, roller, bulut/yerel seçimi, kirlenme kuralı, onay, enjeksiyon (sahte model/araç/bulut)."""
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri

import json
import os
import sys
import tempfile
import time
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
try:
    import ollama  # noqa: E402
except ImportError:
    ollama = sys.modules["ollama"] = types.ModuleType("ollama")
os.environ["GROQ_API_KEY"] = "gsk_testtesttesttesttesttest"
WS = tempfile.mkdtemp()
os.environ["JARVIS_WORKSPACE"] = WS
os.environ["JARVIS_CODE_SANDBOX"] = "off"   # yalnızca test: gerçek kutu yok
from core import brain as B  # noqa: E402
from core import privacy  # noqa: E402
from core import router as R  # noqa: E402
from core import team as T  # noqa: E402
from skills import _confirm as confirm  # noqa: E402
from skills import _store  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


SECRET = "GIZLI-ICERIK-123"
cloud_log, local_log, tool_log, quiet_seen = [], [], [], []
from skills import web  # noqa: E402
from skills import codeagent  # noqa: E402
CODE_SKILLS = codeagent.SKILLS
cfg = {"plan": None, "research_mode": "normal", "local_down": False, "kod_script": [], "review_script": [], "arch": None}


def cloud_ok(text):
    return 200, {}, {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 50, "completion_tokens": 10}}


def respond(messages, where):
    """Hem sahte bulut hem sahte yerel model aynı davranışı verir; (metin) döndürür."""
    sysm = messages[0]["content"]
    has_obs = any(m["content"].startswith("Araç sonucu") for m in messages)
    if "görev planlayıcısısın" in sysm:
        return json.dumps(cfg["plan"]) if cfg["plan"] is not None else "bu bir plan değil"
    if "Araştırma Ajanısın" in sysm:
        mode = cfg["research_mode"]
        if mode == "inject":
            return json.dumps({"tool": "read_file", "args": {"name": "x"}})
        if mode == "garbage":
            return "ben JSON yazmam"
        if not has_obs:
            return json.dumps({"tool": "web_search", "args": {"query": "rtx 3070 ti fiyat", "uydurma": 1, "open_browser": True}})
        return json.dumps({"final": f"Bulgu ({where}): 35 bin TL civarı."})
    if "Dosya Ajanısın" in sysm:
        if not has_obs:
            return "```json\n" + json.dumps({"tool": "read_file", "args": {"name": "notlar.txt"}}) + "\n```"
        return json.dumps({"final": f"Dosyada not var ({where})."})
    if "Kod Ajanısın" in sysm:
        return cfg["kod_script"].pop(0) if cfg["kod_script"] else json.dumps({"final": "bitti"})
    if "Sen Mimarsın" in sysm:
        return json.dumps(cfg["arch"], ensure_ascii=False) if cfg["arch"] is not None else "mimari yok"
    if "Denetçisin" in sysm:
        return cfg["review_script"].pop(0) if cfg["review_script"] else json.dumps({"final": {"gecti": False, "bulgular": []}})
    if "Yazar ajansın" in sysm:
        if cfg.get("writer_style") == "bullets":
            return "- Hedef: fiyat öğrenmek\n- Fiyat **15.000 TL**\n1. Not: veri eski"
        return f"Sonuç hazır ({where})."
    return "?"


def fake_post(url, headers, body, timeout):
    cloud_log.append(body)
    return cloud_ok(respond(body["messages"], "bulut"))


def fake_chat(**kw):
    local_log.append(kw["messages"])
    return {"message": {"content": respond(kw["messages"], "yerel")}}


def tool(name, params, fn):
    schema = {"type": "function", "function": {"name": name, "description": name,
                                               "parameters": {"type": "object", "properties": {p: {"type": "string"} for p in params}}}}
    return name, (schema, fn)


def mk_tools():
    return dict([
        tool("web_search", ["query", "open_browser"], lambda query="", open_browser=None: tool_log.append(("web_search", query)) or quiet_seen.append((web.QUIET, open_browser)) or "yalnızca veri: RTX 3070 Ti fiyatı 35.000 TL. ali@example.com"),
        tool("read_file", ["name"], lambda name="": tool_log.append(("read_file", name)) or f"not: {SECRET}"),
        tool("find_files", ["query"], lambda query="": "notlar.txt"),
        tool("browser_open", ["url"], lambda url="": confirm.request(f"{url} açılacak.", lambda: "Açıldı.")),
        *[(sk["name"], ({"type": "function", "function": {"name": sk["name"], "description": sk["description"], "parameters": sk["parameters"]}}, sk["run"]))
          for sk in CODE_SKILLS],  # gerçek şema (zorunlu parametreler dahil)
    ])


def fresh(router_key=True):
    cloud_log.clear(); local_log.clear(); tool_log.clear()
    confirm.cancel()
    cfg.update(plan=None, research_mode="normal", kod_script=[], review_script=[], arch=None)
    codeagent.set_project(None)
    os.environ["GROQ_API_KEY"] = "gsk_testtesttesttesttesttest" if router_key else ""
    b = B.Brain(tools=mk_tools())
    b.team.router = R.Router({}, post=fake_post)
    return b


ollama.chat = fake_chat
say = lambda b, t: " ".join(b.reply_stream(t))  # noqa: E731

# ---------------------------------------------------------------- hazır plan: "araştır: ..."
b = fresh()
out = say(b, "araştır: RTX 3070 Ti şu an kaç lira")
check("'araştır:' hazır plan sunar (planlayıcı çağrılmaz), onay bekler", "Araştırma Ajanı" in out and "Yazar" in out and "Başlayayım mı" in out and not cloud_log and b.team.state == "plan")
out = say(b, "evet")
check("araştırma görevi çalışır, araç kendi parametresiyle çağrılır (uydurma parametre atılır)", ("web_search", "rtx 3070 ti fiyat") in tool_log)
check("ekip aramayı sessiz kipte çağırır ve open_browser parametresini atar (kullanıcının tarayıcısı açılmaz)", quiet_seen and quiet_seen[0] == (True, None), str(quiet_seen))
check("sonuç Yazar'dan gelir, bulut kullanılır, yerel model hiç çağrılmaz", "Sonuç hazır (bulut)" in out and not local_log and len(cloud_log) == 3, str(len(cloud_log)))
check("bittikten sonra ekip boşta, kayıt yazıldı", b.team.state == "idle" and (_store.path("team_runs.jsonl")).read_text().count("\n") == 1)
log = json.loads(_store.path("team_runs.jsonl").read_text().splitlines()[-1])
check("kayıt yalnızca özet (görev durumları, model), sonuç metni yok", [t["status"] for t in log["tasks"]] == ["done", "done"] and "35 bin" not in json.dumps(log) and log["tasks"][0]["model"].startswith("groq/"))
check("web sonucundaki e-posta bulut çağrısını ENGELLEMEZ (herkese açık kaynak)", any("ali@example.com" in json.dumps(c) for c in cloud_log))

# ---------------------------------------------------------------- planlayıcı + kirlenme (dosya -> yalnızca yerel)
b = fresh()
cfg["plan"] = {"tasks": [
    {"id": "t1", "role": "dosya", "do": "notlar.txt dosyasını oku", "after": []},
    {"id": "t2", "role": "arastirma", "do": "RTX fiyatını internette ara", "after": []},
    {"id": "t3", "role": "yazar", "do": "hepsini derle", "after": ["t1", "t2"]}]}
out = say(b, "ekip: notlarımı oku ve RTX fiyatına bak")
check("planlayıcı (bulut) planı çıkarır ve sesli okunur", "Dosya Ajanı" in out and "Araştırma Ajanı" in out and "Yazar" in out and len(cloud_log) == 1 and b.team.state == "plan")
check("planlayıcıya yalnızca kullanıcının cümlesi ve rol listesi gider", "ekip:" not in json.dumps(cloud_log[0]) and "notlarımı oku" in json.dumps(cloud_log[0], ensure_ascii=False))
out = say(b, "evet")
check("dosya ajanı YEREL çalışır ve dosyayı okur", ("read_file", "notlar.txt") in tool_log and any("Dosya Ajanısın" in m[0]["content"] for m in local_log))
check("dosya okunduktan sonra internete giden adım onay ister (kirlenme)", b.team.state == "confirm" and "internete" in out and ("web_search", "rtx 3070 ti fiyat") not in tool_log)
out = say(b, "evet")
check("onaydan sonra araştırma sürer ve ekip bitirir", ("web_search", "rtx 3070 ti fiyat") in tool_log and b.team.state == "idle" and "Sonuç hazır" in out, out[:200])
check("GİZLİ dosya içeriği hiçbir bulut isteğinde YOK", SECRET not in json.dumps(cloud_log))
check("yazar (kişisel veriye bağlı) YEREL çalıştı", any("Yazar ajansın" in m[0]["content"] for m in local_log) and "Sonuç hazır (yerel)" in out)
check("araştırma ajanı (temiz) bulutta çalıştı", any("Araştırma Ajanısın" in c["messages"][0]["content"] for c in cloud_log))

# ---------------------------------------------------------------- yazar çıktısı sesli okunacak düz metin olur
b = fresh()
cfg["writer_style"] = "bullets"
say(b, "araştır: RTX 3070 Ti şu an kaç lira")
out = say(b, "başla")
cfg.pop("writer_style")
check("yazar madde işareti/markdown yazsa bile cümleye çevrilir", out.endswith("Hedef: fiyat öğrenmek. Fiyat 15.000 TL. Not: veri eski.") and "*" not in out and "- " not in out, out[-120:])
check("ajanlara bugünün tarihi verilir (eski veriyi güncel sanmasın)", time.strftime("%Y-%m-%d") in cloud_log[0]["messages"][0]["content"])
check("speakable: boş ve tek satır", T.speakable("") == "" and T.speakable("Tamam") == "Tamam.")

# ---------------------------------------------------------------- plan onayı doğal cevaplarla
for word in ("başla", "başlayabilirsin", "devam et", "hadi", "tamam"):
    b = fresh()
    say(b, "araştır: RTX 3070 Ti şu an kaç lira")
    out = say(b, word)
    check(f"plan onayı: '{word}' ekibi başlatır", "Sonuç hazır" in out and b.team.state == "idle", out[:80])
for word in ("başlama", "vazgeç", "hayır başla"):
    b = fresh()
    say(b, "araştır: RTX 3070 Ti şu an kaç lira")
    say(b, word)
    check(f"plan onayı: '{word}' başlatmaz", b.team.state == "idle" and not tool_log)
confirm.request("Test işlemi.", lambda: "yapıldı")
check("tehlikeli işlem onayı 'başla' ile VERİLMEZ (yalnızca plan onayı genişledi)", confirm.classify("başla") == "other" and confirm.classify_plan("başla") == "yes")
confirm.cancel()

# ---------------------------------------------------------------- bulut yoksa yerel
b = fresh(router_key=False)
say(b, "araştır: RTX 3070 Ti şu an kaç lira")
out = say(b, "evet")
check("bulut anahtarı yoksa tüm ekip yerelde çalışır", not cloud_log and "Sonuç hazır (yerel)" in out and ("web_search", "rtx 3070 ti fiyat") in tool_log)

# ---------------------------------------------------------------- gizlilik: kullanıcı cümlesinde kişisel veri
b = fresh()
say(b, "araştır: benim telefonum 0532 123 45 67 bunu bul")
out = say(b, "evet")
check("hedefte telefon numarası varsa bulut atlanır, yerelde çalışır", not any("0532" in json.dumps(c) for c in cloud_log) and "Sonuç hazır (yerel)" in out)

# ---------------------------------------------------------------- enjeksiyon / rol dışı araç
b = fresh()
cfg["research_mode"] = "inject"
say(b, "araştır: herhangi bir konu")
out = say(b, "evet")
check("araştırma ajanı rol dışı araç (read_file) çağıramaz", ("read_file", "x") not in tool_log and not any(t[0] == "read_file" for t in tool_log))
last = json.loads(_store.path("team_runs.jsonl").read_text().splitlines()[-1])
check("rol dışı istek 3 kez olunca görev başarısız sayılır, yazar yine de dürüstçe söyler", last["tasks"][0]["status"] == "failed" and "Sonuç hazır" in out)

b = fresh()
cfg["research_mode"] = "garbage"
say(b, "araştır: herhangi bir konu")
out = say(b, "evet")
last = json.loads(_store.path("team_runs.jsonl").read_text().splitlines()[-1])
check("model geçerli JSON vermezse görev 3 ardışık denemede başarısız olur (sonsuz döngü yok)", last["tasks"][0]["status"] == "failed" and b.team.state == "idle")

# ---------------------------------------------------------------- plan doğrulama
have = ["arastirma", "dosya", "yazar"]
V = T.Team.validate_plan
check("plan: bilinmeyen rol atılır, yazar sona eklenir", [t.role for t in V({"tasks": [{"role": "hacker", "do": "x"}, {"role": "arastirma", "do": "ara"}]}, have)] == ["arastirma", "yazar"])
p = V({"tasks": [{"id": "a", "role": "arastirma", "do": "bir", "after": ["yok", "ileri"]}, {"id": "ileri", "role": "arastirma", "do": "iki", "after": ["a"]}, {"role": "yazar", "do": "yaz"}]}, have)
check("plan: olmayan/ileri bağımlılık atılır, yazar hepsine bağlanır", p[0].after == [] and p[1].after == ["a"] and p[-1].after == ["a", "ileri"])
check("plan: en fazla 5 görev", len(V({"tasks": [{"role": "arastirma", "do": f"g{i}"} for i in range(12)]}, have)) == T.MAX_TASKS)
check("plan: boş/bozuk plan reddedilir", V(None, have) == [] and V({"tasks": "x"}, have) == [] and V({"tasks": [{"role": "yazar", "do": "y"}]}, have) == [])
check("plan: rol yüklü araç yoksa kullanılmaz", V({"tasks": [{"role": "dosya", "do": "oku"}]}, ["arastirma", "yazar"]) == [])
check("JSON ayrıştırma: kod çiti, think, fazlalık", T.parse_json("<think>x</think>```json\n{\"final\": \"a\"}\n```") == {"final": "a"} and T.parse_json("yok") is None and T.parse_json("[1]") is None)
check("JSON ayrıştırma: ham satır sonu, sondaki açıklama, fazla virgül",
      T.parse_json('{"final": "satır bir\nsatır iki"}') == {"final": "satır bir\nsatır iki"}
      and T.parse_json('{"tool": "code_run", "args": {"path": "main.py"}} Umarım yardımcı olur }') == {"tool": "code_run", "args": {"path": "main.py"}}
      and T.parse_json('{"tool": "code_read", "args": {"path": "a.py",},}') == {"tool": "code_read", "args": {"path": "a.py"}}
      and T.parse_json('Tamam: {"final": "bitti"}') == {"final": "bitti"} and T.parse_json("{bozuk") is None)
check("speakable: dosya adındaki alt çizgi kalır, vurgu işaretleri gider",
      T.speakable("Çalıştır: `pytest tests/test_main.py` ve __kalın__ _eğik_ **yıldız**") == "Çalıştır: pytest tests/test_main.py ve kalın eğik yıldız.")
raw_re = r'{"tool": "code_write", "args": {"path": "m.py", "content": "x = re.compile(r\"\d+\\s\")\nprint(1)"}}'
# gerçek yerel model (gemma4:e4b) cevaplarından ölçülen bozuk JSON kalıpları (2026-10-25, done_reason=stop: kesilme DEĞİL)
P = T.parse_json
check("onarım: değer sınırlayıcısı kaçışlı (\\\"...\\\")",
      P('{"tool": "code_run", "args": {"command": "python main.py", "stdin": \\"add Alışveriş yap\\nlist\\nquit\\n\\"}}')
      == {"tool": "code_run", "args": {"command": "python main.py", "stdin": "add Alışveriş yap\nlist\nquit\n"}})
check("onarım: fazladan kapanış köşeli parantezi (\"]]}})",
      P('{"final": {"gecti": false, "bulgular": ["todo_manager.py: ID artışı garanti değil."]]}}') == {"final": {"gecti": False, "bulgular": ["todo_manager.py: ID artışı garanti değil."]}})
check("onarım: dizge içinde kaçışsız tırnak",
      P('{"final": {"gecti": false, "bulgular": ["test çıktısı ile gelen "Hata: ID 99 bulunamadı." mesajı, beklenmedik."]}}')
      == {"final": {"gecti": False, "bulgular": ['test çıktısı ile gelen "Hata: ID 99 bulunamadı." mesajı, beklenmedik.']}})
check("onarım: koddaki kaçışsız tırnak ve virgül dizgeyi kapatmaz",
      P('{"tool": "code_write", "args": {"path": "a.py", "content": "print("a", b)\\n"}}') == {"tool": "code_write", "args": {"path": "a.py", "content": 'print("a", b)\n'}})
check("onarım: kesilmiş cevap kapatılır", P('{"final": {"gecti": false, "bulgular": ["eksik test') == {"final": {"gecti": False, "bulgular": ["eksik test"]}})
check("onarım: kapanış tırnağı da kaçışlı + ardından ikinci nesne -> ilk nesne alınır",
      P('{"tool": "code_write", "args": {"path": "a.py", "content": "print(\\"x\\")\\n\\"}}\n{"tool": "code_run", "args": {"command": "python a.py"}}')
      == {"tool": "code_write", "args": {"path": "a.py", "content": 'print("x")\n'}})
check("onarım: nesneden sonra başıboş karakterler ('\"})}', '\"}\")}')",
      P('{"tool": "code_write", "args": {"path": "a.py", "content": "x = 1\\n"})}') == {"tool": "code_write", "args": {"path": "a.py", "content": "x = 1\n"}}
      and P('{"tool": "code_write", "args": {"path": "a.py", "content": "x = 1\\n"}")}') == {"tool": "code_write", "args": {"path": "a.py", "content": "x = 1\n"}})
check("onarım: '\"})' ile biten nesneden sonra ikinci çağrı -> ilk nesne kapatılır",
      P('{"tool": "code_write", "args": {"path": "a.py", "content": "main()"})\n{"tool": "code_run", "args": {"command": "python a.py"}}')
      == {"tool": "code_write", "args": {"path": "a.py", "content": "main()"}})
check("onarım: son '}' unutulmuşsa eklenir", P('{"tool": "code_write", "args": {"path": "a.py", "content": "x = 1\\n"}') == {"tool": "code_write", "args": {"path": "a.py", "content": "x = 1\n"}})
check("dizge ortasında kesilmiş code_write REDDEDİLİR (yarım dosya yazılmaz; done=length)",
      P('{"tool": "code_write", "args": {"path": "t.py", "content": "import unittest\\n\\t\\t\\t\\t') is None)
check("onarım: geçerli JSON'a dokunulmaz (iç tırnak kaçışlı kalır)", P('{"final": "a \\"b\\" c", "x": [1, {"y": "}"}]}') == {"final": 'a "b" c', "x": [1, {"y": "}"}]})
check("JSON ayrıştırma: koddaki geçersiz kaçış (\\d) onarılır, geçerli \\\\s ve \\n bozulmaz",
      T.parse_json(raw_re) == {"tool": "code_write", "args": {"path": "m.py", "content": 'x = re.compile(r"\\d+\\s")\nprint(1)'}})

# ---------------------------------------------------------------- konuşma akışı
b = fresh()
cfg["plan"] = "bozuk"
out = say(b, "ekip: şunu yap bakalım")
check("planlayıcı saçmalarsa dürüstçe söyler, plan kurulmaz", "çıkaramadım" in out and b.team.state == "idle")
b = fresh()
say(b, "araştır: bir konu araştırılacak")
check("'hayır' ekibi iptal eder", "iptal" in say(b, "hayır") and b.team.state == "idle" and not tool_log)
b = fresh()
say(b, "araştır: bir konu araştırılacak")
b.team.plan_expires = time.time() - 1
say(b, "saat kaç")
check("plan süresi dolunca düşer", b.team.state == "idle")
b = fresh()
b.remote = True
out = say(b, "araştır: bir konu araştırılacak")
check("uzaktan (Telegram) ekip başlatılamaz", b.team.state == "idle" and "Başlayayım" not in out)
b = fresh()
b.agent.state = "plan"
check("ajan modu doluyken ekip başlamaz", b.team.handle("araştır: bir konu araştırılacak") is None)
b.agent.abort()
check("'ekip' kelimesi sıradan cümlede tetiklemez", all(b.team.handle(t) is None for t in ("ekip arkadaşlarım geldi", "araştırma yapıyorum bugün", "takım nasıl oynadı")))
b = fresh()
say(b, "araştır: bir konu araştırılacak")
gen = b.team.handle("evet")
first = next(gen)
snap = b.team.snapshot()
check("canlı durum: çalışıyor, aktif rol ve görev listesi (pano için)", snap["state"] == "running" and snap["active_role"] == "arastirma" and snap["total"] == 2 and snap["tasks"][0]["status"] == "running")
for _ in gen:
    pass

from dashboard import state  # noqa: E402
from pathlib import Path  # noqa: E402

# ---------------------------------------------------------------- Kod Ajanı
J = json.dumps
def kod_run(goal, script, say_word="başla"):
    b = fresh()
    cfg["kod_script"] = list(script)
    plan = say(b, f"kod: {goal}")
    out = say(b, say_word)
    return b, plan, out


b, plan, out = kod_run("hesap makinesi yaz", [
    J({"tool": "code_write", "args": {"path": "main.py", "content": "print(2 + 3)\n"}}),
    J({"tool": "code_run", "args": {"command": "python main.py"}}),
    J({"final": "main.py yazdım; python main.py çalıştırınca 5 verdi."})])
proj = Path(WS) / "hesap-makinesi-yaz"
check("'kod:' hazır plan: Kod Ajanı + Yazar, onay bekler (planlayıcı çağrılmaz)", "Kod Ajanı" in plan and "Yazar" in plan and "Başlayayım mı" in plan and not any("planlayıcısısın" in c["messages"][0]["content"] for c in cloud_log))
check("kod yazıldı ve çalıştırıldı: dosya workspace/<proje>/ altında", (proj / "main.py").read_text() == "print(2 + 3)\n")
check("sesli ilerleme: 'Kod yazıyorum.' ve 'Çalıştırıp deniyorum.' bir kez", out.count("Kod yazıyorum.") == 1 and out.count("Çalıştırıp deniyorum.") == 1, out[:200])
check("sonuçta proje klasörü söylenir, kod ajanı bulutta çalıştı", "workspace/hesap-makinesi-yaz klasöründe" in out and any("Kod Ajanısın" in c["messages"][0]["content"] for c in cloud_log))
kod_req = json.dumps([c["messages"] for c in cloud_log if "Kod Ajanısın" in c["messages"][0]["content"]][0], ensure_ascii=False)
check("kod ajanına 'workspace/...' yolu GÖSTERİLMEZ (yollara önek eklemesin), kökten yazması söylenir", "workspace/" not in kod_req and "kökten itibaren" in kod_req)
check("yazara proje klasörü bildirilir", any("Proje klasörü: workspace/hesap-makinesi-yaz" in json.dumps(c["messages"], ensure_ascii=False) for c in cloud_log if "Yazar ajansın" in c["messages"][0]["content"]))
check("kod ajanı isteklerinde max_tokens yüksek (dosya yazabilsin)", any(c["max_tokens"] == 1800 for c in cloud_log))

b, plan, out = kod_run("toplama programı yaz", [
    J({"tool": "code_write", "args": {"path": "main.py", "content": "raise ValueError('bozuk')\n"}}),
    J({"tool": "code_run", "args": {"command": "python main.py"}}),
    J({"tool": "code_write", "args": {"path": "main.py", "content": "print('düzeldi')\n"}}),
    J({"tool": "code_run", "args": {"command": "python main.py"}}),
    J({"final": "Hatayı düzelttim; artık çalışıyor."})])
reqs = [json.dumps(c["messages"], ensure_ascii=False) for c in cloud_log if "Kod Ajanısın" in c["messages"][0]["content"]]
check("hata döngüsü: traceback bir sonraki istekte ajana görünür, düzeltip tekrar çalıştırır", "ValueError: bozuk" in reqs[2] and (Path(WS) / "toplama-programi-yaz" / "main.py").read_text() == "print('düzeldi')\n")

# bağlam sıkıştırma: uzun döngüde istek boyutu sınırda kalır, eski adımlar özetlenir
big = "x = 1\n" * 900
script = [J({"tool": "code_write", "args": {"path": "big.py", "content": big}})] + [J({"tool": "code_read", "args": {"path": "big.py", "start_line": i}}) for i in range(1, 11)] + [J({"final": "okudum"})]
b, plan, out = kod_run("büyük dosya okuma denemesi", script)
sizes = [sum(len(m["content"]) for m in c["messages"]) for c in cloud_log if "Kod Ajanısın" in c["messages"][0]["content"]]
check("uzun kod döngüsünde her istek ücretsiz bulut sınırına sığar (sıkıştırma)", max(sizes) <= T.VIEW_BUDGET * 1.3 + 3500, str(max(sizes)))
check("eski adımlar kısa özet olarak taşınır", any("Önceki adımların kısa özeti" in json.dumps(c["messages"], ensure_ascii=False) for c in cloud_log))
check("hiçbir istek bulut girdi sınırını aşmadı (yerel modele düşülmedi)", not local_log)

# rol sınırı: kod ajanı web/dosya aracı çağıramaz; araştırma ajanı kod aracı çağıramaz
b, plan, out = kod_run("deneme programı yaz", [J({"tool": "web_search", "args": {"query": "x"}}), J({"tool": "read_file", "args": {"name": "gizli.txt"}}), J({"tool": "web_search", "args": {"query": "x"}})])
check("kod ajanı rol dışı araç (web_search/read_file) çağıramaz", not tool_log)
b = fresh()
cfg["research_mode"] = "inject"
check("araştırma rolünün araç listesinde kod aracı yok", not set(T.ROLES["arastirma"].tools) & {"code_write", "code_run"} and "read_file" not in T.ROLES["kod"].tools)

# kişisel veri içeren hedef: bulut atlanır, yerelde çalışır
b, plan, out = kod_run("0532 123 45 67 numaralı rehber programı yaz", [J({"tool": "code_write", "args": {"path": "r.py", "content": "print(1)"}}), J({"final": "yazdım"})])
check("hedefte telefon varsa kod ajanı YEREL çalışır, bulut isteğinde numara yok", not any("0532" in json.dumps(c) for c in cloud_log) and any("Kod Ajanısın" in m[0]["content"] for m in local_log))

# güvenli kutu yoksa: çalıştırma onay ister, onaydan sonra sürer
os.environ.pop("JARVIS_CODE_SANDBOX")
codeagent.reset_sandbox_cache()
_w = codeagent.shutil.which
codeagent.shutil.which = lambda n: None if n == "bwrap" else _w(n)
b = fresh()
cfg["kod_script"] = [J({"tool": "code_write", "args": {"path": "main.py", "content": "print('merhaba')\n"}}), J({"tool": "code_run", "args": {"command": "python main.py"}}), J({"final": "çalıştı"})]
say(b, "kod: selamlama programı yaz")
out = say(b, "başla")
check("güvenli kutu yokken çalıştırma onay ister, ekip 'onay bekliyor' durumuna geçer", b.team.state == "confirm" and "Güvenli kutu yok" in out, out[-200:])
out = say(b, "evet")
check("onaydan sonra kod çalışır ve görev biter", b.team.state == "idle" and "Sonuç hazır" in out and "selamlama-programi-yaz" in out, out[-200:])
codeagent.shutil.which = _w
os.environ["JARVIS_CODE_SANDBOX"] = "off"

# bulut kısa süre limitteyse kod ajanı yerel modele düşmez, bekler ve bulutta sürer
b = fresh()
tclock = [5000.0]
b.team.router = R.Router({}, post=None, now=lambda: tclock[0])
rate = {"n": 0}


def limited_post(url, headers, body, timeout):
    if rate["n"] < 5:
        rate["n"] += 1
        return 429, {"retry-after": "20"}, {"error": {"message": "rate limit"}}
    return fake_post(url, headers, body, timeout)


b.team.router.post = limited_post
slept = []
b.team.sleep = lambda sec: (slept.append(sec), tclock.__setitem__(0, tclock[0] + sec))
cfg["kod_script"] = [J({"tool": "code_write", "args": {"path": "main.py", "content": "print(7)\n"}}), J({"final": "yazdım"})]
say(b, "kod: bekleme denemesi programı yaz")
out = say(b, "başla")
check("kod ajanı bulut limitteyken yerel modele düşmez: bekler (≈21 sn) ve bulutta sürer", slept and 20 <= slept[0] <= 22 and not any("Kod Ajanısın" in m[0]["content"] for m in local_log) and (Path(WS) / "bekleme-denemesi-programi-yaz" / "main.py").exists(), str(slept))
b = fresh()
b.team.router = R.Router({}, post=lambda *a: (429, {"retry-after": "300"}, {}), now=lambda: tclock[0])
slept.clear()
b.team.sleep = lambda sec: slept.append(sec)
cfg["kod_script"] = [J({"final": "yerelde yazdım"})]
say(b, "kod: uzun bekleme denemesi yaz")
say(b, "başla")
check("limit çok uzunsa (300 sn) beklemeden yerele düşer", not slept and any("Kod Ajanısın" in m[0]["content"] for m in local_log))

# gerçek model denemesinde görülen: gemma4 code_write'a "path" yerine "file" verdi -> ad düzeltilir; eksik zorunlu ad aracı çağırmaz
b, plan, out = kod_run("takma ad denemesi yaz", [
    J({"tool": "code_write", "args": {"content": "print(1)\n"}}),
    J({"tool": "code_write", "args": {"file": "main.py", "code": "print(9)\n"}}),
    J({"final": "yazdım"})])
reqs = [json.dumps(c["messages"], ensure_ascii=False) for c in cloud_log if "Kod Ajanısın" in c["messages"][0]["content"]]
check("yanlış parametre adı (file/code) şemadaki ada çevrilir, dosya yazılır", (Path(WS) / "takma-ad-denemesi-yaz" / "main.py").read_text() == "print(9)\n")
check("eksik zorunlu parametre: araç çağrılmaz, ajana doğru adlar söylenir", "code_write için eksik parametre: path" in reqs[1])
check("araç kılavuzunda gerçek parametre adları yazar", "code_write: " in reqs[0] and "(parametreler: path, content)" in reqs[0])
check("takma ad, şemadaki gerçek adı ezmez", T.Team._fit_args({"path": "a.py", "file": "b.py", "content": "x"}, {"properties": {"path": {}, "content": {}}, "required": ["path"]})
      == ({"path": "a.py", "content": "x"}, []))

b, plan, out = kod_run("tekrar denemesi yaz", [
    J({"tool": "code_write", "args": {"path": "main.py", "content": "print(1)\n"}}),
    J({"tool": "code_read", "args": {"path": "main.py"}}), J({"tool": "code_read", "args": {"path": "main.py"}}),
    J({"tool": "code_write", "args": {"path": "main.py", "content": "print(2)\n"}}),
    J({"tool": "code_read", "args": {"path": "main.py"}}), J({"final": "tamam"})])
reqs = [json.dumps(c["messages"], ensure_ascii=False) for c in cloud_log if "Kod Ajanısın" in c["messages"][0]["content"]]
check("aynı çağrı tekrarlanmaz (ajana söylenir); code_write'tan sonra yeniden okumak serbest",
      "code_read çağrısını aynı argümanlarla zaten yaptın" in reqs[3] and reqs[-1].count("aynı argümanlarla zaten yaptın") == 1 and "print(2)" in reqs[-1])

b, plan, out = kod_run("yeniden yazma denemesi", [J({"tool": "code_write", "args": {"path": "main.py", "content": f"print({i})\n"}}) for i in range(4)]
                       + [J({"tool": "code_run", "args": {"command": "python main.py"}}), J({"tool": "code_write", "args": {"path": "main.py", "content": "print(9)\n"}}),
                          J({"final": "tamam"})])
reqs = [json.dumps(c["messages"], ensure_ascii=False) for c in cloud_log if "Kod Ajanısın" in c["messages"][0]["content"]]
check("aynı dosya çalıştırılmadan 2'den fazla yazılmaz; code_run'dan sonra yine yazılabilir",
      "çalıştırmadan 2 kez yazdın" in reqs[3] and (Path(WS) / "yeniden-yazma-denemesi" / "main.py").read_text() == "print(9)\n")

# ---------------------------------------------------------------- Denetçi
V = T.review_verdict
check("hüküm: bulgu yok + çalıştırdı -> geçti", V({"gecti": True, "bulgular": []}, True)[0] == "geçti")
check("hüküm: çalıştırmadan 'geçti' kabul edilmez", V({"gecti": True}, False)[0] == "doğrulanamadı")
check("hüküm: bulgu varsa 'geçti' dese de kaldı, bulgular numaralı okunur",
      V({"gecti": True, "bulgular": ["main.py: boş girdide çöküyor"]}, True) == ("kaldı", "Denetim kaldı. Düzeltilmesi gerekenler: 1) main.py: boş girdide çöküyor."))
check("hüküm: düz metin 'GEÇTİ' / 'KALDI: ...' anlaşılır, belirsiz metin doğrulanamadı",
      V("GEÇTİ", True)[0] == "geçti" and V("KALDI: toplama yanlış", False)[0] == "kaldı" and "toplama yanlış" in V("kaldı - toplama yanlış", True)[1]
      and V("bilmiyorum", True)[0] == "doğrulanamadı")
check("hüküm: mimar planındaki eksik dosya kendiliğinden bulgu (denetçi geçti dese de kaldı)",
      V({"gecti": True, "bulgular": []}, True, ["tests/test_b.py"]) == ("kaldı", "Denetim kaldı. Düzeltilmesi gerekenler: 1) tests/test_b.py: mimarın planında var ama yazılmamış."))
check("hüküm: en fazla 5 bulgu", V({"gecti": False, "bulgular": [f"b{i}" for i in range(9)]}, True)[1].count(")") == T.MAX_FINDINGS)

b, plan, out = kod_run("çarpım programı yaz", [
    J({"tool": "code_write", "args": {"path": "main.py", "content": "print(2 * 3)\n"}}),
    J({"tool": "code_run", "args": {"command": "python main.py"}}),
    J({"final": "main.py yazdım, kusursuz çalışıyor, denetime gerek yok."})])
check("'kod:' planında Denetçi var (Kod Ajanı -> Denetçi -> Yazar)", "Denetçi" in plan and plan.index("Kod Ajanı") < plan.index("Denetçi") < plan.index("Yazar"), plan)
den_req = [c["messages"] for c in cloud_log if "Denetçisin" in c["messages"][0]["content"]]
den_txt = json.dumps(den_req, ensure_ascii=False)
check("denetçi ayrı bağlamda: kod ajanının konuşması/araç adımları gitmez, iddiası 'doğrulanmamış' etiketli",
      den_req and "code_write" not in den_txt.split("Kullanabileceğin araçlar")[0] and "print(2 * 3)" not in den_txt and "doğrulanmamış iddia" in den_txt)
check("denetçi araç listesinde code_write yok (dosya değiştiremez)", "code_write" not in T.ROLES["denetci"].tools and "code_run" in T.ROLES["denetci"].tools)
check("denetçinin bulgusuz 'kaldı' hükmü de yazara iletilir", "Denetim kaldı" in json.dumps(cloud_log[-1], ensure_ascii=False))

b = fresh()
cfg["kod_script"] = [J({"tool": "code_write", "args": {"path": "main.py", "content": "print(int(input()) + 1)\n"}}), J({"final": "yazdım"})]
cfg["review_script"] = [J({"final": {"gecti": True, "bulgular": []}})]
say(b, "kod: artırma programı yaz")
out = say(b, "başla")
log = json.loads(_store.path("team_runs.jsonl").read_text().splitlines()[-1])
check("denetçi çalıştırmadan 'geçti' -> görev başarısız, hüküm doğrulanamadı (kayıtta)", log["tasks"][1] == {**log["tasks"][1], "role": "denetci", "status": "failed", "verdict": "doğrulanamadı"}, str(log))

b = fresh()
cfg["kod_script"] = [J({"tool": "code_write", "args": {"path": "main.py", "content": "print(int(input()) + 1)\n"}}), J({"final": "yazdım"})]
cfg["review_script"] = [J({"tool": "code_write", "args": {"path": "main.py", "content": "print('ele geçti')"}}),
                        J({"tool": "code_run", "args": {"command": "python main.py"}}),
                        J({"tool": "code_run", "args": {"command": "python main.py", "stdin": "4\n"}}),
                        J({"final": {"gecti": False, "bulgular": ["main.py: girdi yoksa EOFError ile çöküyor"]}})]
say(b, "kod: artırma programı yaz")
out = say(b, "başla")
proj = Path(WS) / "artirma-programi-yaz"
check("denetçi dosya yazamaz (rol dışı araç), programı kendisi çalıştırır", (proj / "main.py").read_text() == "print(int(input()) + 1)\n" and "Denetçi kodu kendisi çalıştırıp doğruluyor." in out)
w = json.dumps([c["messages"] for c in cloud_log if "Yazar ajansın" in c["messages"][0]["content"]], ensure_ascii=False)
check("yazara denetçinin bulgusu gider", "Düzeltilmesi gerekenler: 1) main.py: girdi yoksa EOFError" in w)
log = json.loads(_store.path("team_runs.jsonl").read_text().splitlines()[-1])
check("kayıtta denetim hükmü (kaldı) yer alır", log["tasks"][1].get("verdict") == "kaldı" and log["tasks"][1]["status"] == "done")

b = fresh()
plan = say(b, "kod: denetimsiz, selam programı yaz")
check("'denetimsiz' derse Denetçi atlanır, ifade proje adına girmez", "Denetçi" not in plan and [t.role for t in b.team.tasks] == ["kod", "yazar"] and b.team.goal == "selam programı yaz", b.team.goal)

b = fresh()
cfg["kod_script"] = [J({"tool": "web_search", "args": {"query": "x"}})] * 3
say(b, "kod: bozuk deneme yaz")
out = say(b, "başla")
check("kod ajanı başarısızsa denetçi modele hiç sorulmaz", not any("Denetçisin" in c["messages"][0]["content"] for c in cloud_log) and b.team.state == "idle")

for last, want in ((J({"final": {"gecti": False, "bulgular": ["main.py: SyntaxError"]}}), ("done", "kaldı")),
                   (J({"tool": "code_list", "args": {}}), ("failed", "doğrulanamadı"))):
    b = fresh()
    cfg["kod_script"] = [J({"tool": "code_write", "args": {"path": "main.py", "content": "print(1)\n"}}), J({"final": "yazdım"})]
    cfg["review_script"] = [J({"tool": "code_run", "args": {"command": f"python main.py {i}"}}) for i in range(T.ROLES["denetci"].max_rounds)] + [last]
    say(b, "kod: sınır denemesi yaz")
    say(b, "başla")
    log = json.loads(_store.path("team_runs.jsonl").read_text().splitlines()[-1])
    dreq = json.dumps([c["messages"] for c in cloud_log if "Denetçisin" in c["messages"][0]["content"]][-1], ensure_ascii=False)
    check(f"denetçi tur sınırında son kez yalnızca hüküm istenir -> {want[0]}/{want[1]}",
          "Araç hakkın bitti" in dreq and log["tasks"][1]["status"] == want[0] and log["tasks"][1].get("verdict", "") == want[1], str(log["tasks"][1]))

check("planlayıcı: kodsuz plandaki denetçi atılır, kodlu planda kod görevine bağlanır",
      [t.role for t in T.Team.validate_plan({"tasks": [{"id": "a", "role": "denetci", "do": "denetle"}, {"id": "y", "role": "yazar", "do": "söyle"}]}, ["arastirma", "kod", "denetci", "yazar"])] == []
      and [(t.role, t.after) for t in T.Team.validate_plan({"tasks": [{"id": "k", "role": "kod", "do": "yaz"}, {"id": "d", "role": "denetci", "do": "denetle"},
                                                                       {"id": "y", "role": "yazar", "do": "söyle"}]}, ["kod", "denetci", "yazar"])]
      == [("kod", []), ("denetci", ["k"]), ("yazar", ["k", "d"])])

# ---------------------------------------------------------------- Mimar ("proje:")
VD = T.validate_design
d = VD({"ozet": "x", "parcalar": [{"dosyalar": ["../kacis.py", "/etc/a.py", "./depo.py", "a.py", "b.py"], "is": "depo"},
                                   {"dosyalar": ["depo.py"], "is": "aynı dosya tekrar"}, {"dosyalar": "main.py", "is": "giriş"},
                                   {"dosyalar": ["c.py"], "is": ""}, *[{"dosyalar": [f"p{i}.py"], "is": "ek"} for i in range(6)]]})
check("mimari doğrulama: kaçış/mutlak yol atılır, './' temizlenir, parça başı 2 dosya, aynı dosya iki parçada yok, boş iş atılır, en fazla 4 parça",
      d and [p["dosyalar"] for p in d[1]] == [["depo.py", "a.py"], ["main.py"], ["p0.py"], ["p1.py"]], str(d))
check("mimari doğrulama: parçasız / bozuk çıktı reddedilir", VD(None) is None and VD({"parcalar": []}) is None and VD({"parcalar": [{"dosyalar": ["../x.py"], "is": "y"}]}) is None)

ARCH = {"ozet": "Komut satırı harcama takipçisi.", "parcalar": [
    {"dosyalar": ["depo.py", "tests/test_depo.py"], "is": "harcamaları JSON dosyasında tut", "arayuz": "def ekle(ad, tutar) -> None; def liste() -> list"},
    {"dosyalar": ["main.py"], "is": "komut satırı menüsü", "arayuz": "def main() -> None"}]}
b = fresh()
cfg["arch"] = ARCH
plan = say(b, "proje: harcamalarımı takip eden komut satırı uygulaması yaz")
check("'proje:' mimarı onaydan önce çağırır, plan okunur: parçalar + Denetçi + Yazar, onay bekler",
      "Mimar planı" in plan and "Proje 2 parçada" in plan and "depo.py, tests/test_depo.py yaz" in plan and "Denetçi" in plan and "Başlayayım mı" in plan
      and b.team.state == "plan" and [t.role for t in b.team.tasks] == ["kod", "kod", "denetci", "yazar"] and not tool_log, plan)
check("mimar bulutta çalıştı (temiz bağlam), henüz kod ajanı çağrılmadı",
      any("Sen Mimarsın" in c["messages"][0]["content"] for c in cloud_log) and not any("Kod Ajanısın" in c["messages"][0]["content"] for c in cloud_log))
check("proje kipinde araç çağrısı sınırı yükseltilir; denetçi tüm kod parçalarına bağlı",
      b.team.max_calls == T.MAX_CALLS_PROJECT and b.team.tasks[2].after == ["t1", "t2"] and b.team.tasks[1].after == ["t1"])
cfg["kod_script"] = [J({"tool": "code_write", "args": {"path": "depo.py", "content": "V = []\n"}}), J({"final": "depo.py yazıldı"}),
                     J({"tool": "code_write", "args": {"path": "main.py", "content": "import depo\nprint(len(depo.V))\n"}}),
                     J({"tool": "code_run", "args": {"command": "python main.py"}}), J({"final": "main.py yazıldı, 0 yazdırdı"})]
out = say(b, "evet")
kreqs = [json.dumps(c["messages"], ensure_ascii=False) for c in cloud_log if "Kod Ajanısın" in c["messages"][0]["content"]]
proj = Path(WS) / "harcamalarimi-takip-eden-komut"
check("tek 'evet' ile parçalar sırayla aynı proje klasöründe yazılır", (proj / "depo.py").exists() and (proj / "main.py").exists() and b.team.state == "idle", str(list(Path(WS).iterdir())))
check("her kod ajanı mimarın tasarımını ve arayüzleri görür", kreqs and all("Mimarın tasarımı" in r and "def ekle(ad, tutar)" in r for r in kreqs))
check("ikinci parça birinci parçanın sonucunu görür", any("depo.py yazıldı" in r and "main.py yaz:" in r for r in kreqs))
check("sonda denetçi ve yazar çalışır", any("Denetçisin" in c["messages"][0]["content"] for c in cloud_log) and "Sonuç hazır" in out)

b = fresh()
cfg["arch"] = ARCH
cfg["kod_script"] = [J({"tool": "code_write", "args": {"path": "depo.py", "content": "V = []\n"}}), J({"final": "depo.py yazıldı"}),
                     J({"tool": "code_write", "args": {"path": "main.py", "content": "print(1)\n"}}), J({"tool": "code_run", "args": {"command": "python main.py"}}), J({"final": "bitti"})]
cfg["review_script"] = [J({"tool": "code_run", "args": {"command": "python main.py"}}), J({"final": {"gecti": True, "bulgular": []}})]
say(b, "proje: harcama takipçisi yaz")
say(b, "evet")
log = json.loads(_store.path("team_runs.jsonl").read_text().splitlines()[-1])
w = json.dumps([c["messages"] for c in cloud_log if "Yazar ajansın" in c["messages"][0]["content"]], ensure_ascii=False)
check("proje: tests/test_depo.py yazılmadı -> denetçi 'geçti' dese de hüküm kaldı, yazara eksik dosya gider",
      log["tasks"][2].get("verdict") == "kaldı" and "tests/test_depo.py: mimarın planında var ama yazılmamış" in w, str(log["tasks"]))

b = fresh()
cfg["arch"] = None
out = say(b, "proje: bir şey yaz bakalım")
check("mimar plan çıkaramazsa kibarca söyler, ekip boşta kalır", "mimari plan çıkaramadım" in out and b.team.state == "idle")
b = fresh()
cfg["arch"] = ARCH
say(b, "mimar: harcama uygulaması yaz")
out = say(b, "hayır")
check("'mimar:' de başlatır; 'hayır' iptal eder, hiçbir kod yazılmaz", "iptal" in out and b.team.state == "idle" and not any("Kod Ajanısın" in c["messages"][0]["content"] for c in cloud_log))
b = fresh()
cfg["arch"] = ARCH
plan = say(b, "proje: denetimsiz, harcama uygulaması yaz")
check("proje kipinde de 'denetimsiz' Denetçiyi atlar", [t.role for t in b.team.tasks] == ["kod", "kod", "yazar"] and "Denetçi" not in plan)
b = fresh()
cfg["plan"] = {"tasks": [{"id": "m", "role": "mimar", "do": "böl"}, {"id": "k", "role": "kod", "do": "yaz"}, {"id": "y", "role": "yazar", "do": "söyle"}]}
say(b, "ekip: bir program yaz")
preq = json.dumps([c["messages"] for c in cloud_log if "planlayıcısısın" in c["messages"][0]["content"]], ensure_ascii=False)
check("mimar planlayıcıya rol olarak sunulmaz ve plana görev olarak giremez", preq and "- mimar:" not in preq and [t.role for t in b.team.tasks] == ["kod", "yazar"], str([t.role for t in b.team.tasks]))

# planlayıcı kod ajanını da kullanabilir
b = fresh()
cfg["plan"] = {"tasks": [{"id": "t1", "role": "arastirma", "do": "API belgesini ara", "after": []}, {"id": "t2", "role": "kod", "do": "örnek istemci yaz", "after": ["t1"]},
                         {"id": "t3", "role": "yazar", "do": "özetle", "after": ["t1", "t2"]}]}
plan = say(b, "ekip: bir API için örnek istemci yaz")
check("planlayıcı planında Kod Ajanı yer alabilir; kod görevi araştırma sonucuna bağlanır", "Kod Ajanı" in plan and b.team.tasks[1].after == ["t1"] and [t.role for t in b.team.tasks] == ["arastirma", "kod", "yazar"])
check("panel: kod ajanı satırı", {r["name"]: r for r in state._ajanlar(types.SimpleNamespace(brain=b))}["Kod Ajanı"]["status"] == "Hazır")

# ---------------------------------------------------------------- pano satırları
b = fresh()
rows = {r["name"]: r for r in state._ajanlar(types.SimpleNamespace(brain=b))}
check("pano: ekip modu ve uzman ajanlar listelenir", rows["Ekip Modu"]["status"] == "Hazır" and rows["Araştırma Ajanı"]["status"] == "Hazır" and rows["Dosya Ajanı"]["status"] == "Hazır" and "yalnızca yerel" in rows["Dosya Ajanı"]["detail"])
say(b, "araştır: bir konu araştırılacak")
rows = {r["name"]: r for r in state._ajanlar(types.SimpleNamespace(brain=b))}
check("pano: plan onayı bekliyor görünür", rows["Ekip Modu"]["status"] == "Plan onayı bekliyor")

# ---------------------------------------------------------------- gizlilik kapısı: public/private bayrakları
check("gizlilik: public mesajdaki e-posta geçer, kullanıcı mesajındaki geçmez, private her zaman engellenir",
      privacy.gate([{"role": "user", "content": "iletişim: a@b.com", "public": True}])[0]["content"] == "iletişim: a@b.com")
for msgs in ([{"role": "user", "content": "mail a@b.com"}], [{"role": "user", "content": "x", "public": True, "private": True}]):
    try:
        privacy.gate(msgs)
        ok = False
    except privacy.Blocked:
        ok = True
    check("gizlilik: engel " + msgs[0]["content"][:12], ok)

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
