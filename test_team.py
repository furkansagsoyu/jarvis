"""Ekip modu (çoklu ajan) testleri: plan, roller, bulut/yerel seçimi, kirlenme kuralı, onay, enjeksiyon (sahte model/araç/bulut)."""
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
import brain as B  # noqa: E402
import privacy  # noqa: E402
import router as R  # noqa: E402
import team as T  # noqa: E402
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
cfg = {"plan": None, "research_mode": "normal", "local_down": False}


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
    ])


def fresh(router_key=True):
    cloud_log.clear(); local_log.clear(); tool_log.clear()
    confirm.cancel()
    cfg.update(plan=None, research_mode="normal")
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
check("model geçerli JSON vermezse görev 2 denemede başarısız olur (sonsuz döngü yok)", last["tasks"][0]["status"] == "failed" and b.team.state == "idle")

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

# ---------------------------------------------------------------- pano satırları
from dashboard import state  # noqa: E402

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
