"""Model yönlendirici + gizlilik kapısı testleri (gerçek ağa çıkmadan, sahte HTTP ile)."""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
for k in ("GROQ_API_KEY", "MISTRAL_API_KEY"):
    os.environ.pop(k, None)
import privacy  # noqa: E402
import router as R  # noqa: E402
import ui_state  # noqa: E402
from skills import _store  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


# ---------------------------------------------------------------- gizlilik kapısı
I = privacy.inspect
check("gizlilik: sıradan soru temiz", I("python'da liste nasıl tersine çevrilir") == [] and I("şifre nedir") == [])
check("gizlilik: API anahtarı", bool(I("gsk_" + "a" * 30)) and bool(I("key sk-" + "b" * 24)) and bool(I("-----BEGIN RSA PRIVATE KEY-----")))
check("gizlilik: parola atamaları (kod ve sesli)", bool(I("password = 'abc12345'")) and bool(I("şifrem 4821 olsun")) and bool(I("parola: kedi123")))
check("gizlilik: e-posta, telefon, IBAN", bool(I("ali@example.com")) and bool(I("0532 123 45 67")) and bool(I("TR330006100519786457841326")))
check("gizlilik: kart (Luhn) ve T.C. kimlik (sağlama)", bool(I("kart 4111 1111 1111 1111")) and bool(I("10000000146")) and I("12345678901") == [])
check("gizlilik: adres", bool(I("Atatürk mahallesi 12. sokak")))
check("gizlilik: ev yolu maskelenir, engellenmez", privacy.gate([{"role": "user", "content": "File /home/furkan/jarvis/x.py satır 3"}])[0]["content"] == "File /home/kullanici/jarvis/x.py satır 3")
try:
    privacy.gate([{"role": "user", "content": "merhaba"}, {"role": "user", "content": "hafıza", "private": True}])
    ok = False
except privacy.Blocked as b:
    ok = "özel" in b.text
check("gizlilik: 'private' işaretli içerik asla gitmez", ok)
check("gizlilik: sebep içeriği göstermez", "4111" not in privacy.Blocked(I("kart 4111 1111 1111 1111")).text)

# ---------------------------------------------------------------- sahte HTTP + sahte saat
clock = [1_000_000.0]
calls = []
script = []  # her çağrı için (durum, başlıklar, veri) ya da istisna


def fake_post(url, headers, body, timeout):
    calls.append((url, headers, body))
    r = script.pop(0) if script else (200, {}, ok_body("tamam"))
    if isinstance(r, Exception):
        raise r
    return r


def ok_body(text, tin=11, tout=5):
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": tin, "completion_tokens": tout}}


MSG = [{"role": "user", "content": "Python'da liste nasıl tersine çevrilir?"}]


def new(cfg=None, key="gsk_testtesttesttesttesttest"):
    os.environ.pop("GROQ_API_KEY", None)
    if key:
        os.environ["GROQ_API_KEY"] = key
    calls.clear()
    script.clear()
    _store.save("router_stats.json", {})
    _store.save("settings.json", {})
    return R.Router(cfg or {}, post=fake_post, now=lambda: clock[0])


r = new(key="")
try:
    r.chat(MSG)
    ok = False
except R.Unavailable as e:
    ok = "anahtar" in str(e)
check("anahtar yoksa Unavailable (yerel modele dönülür), ağa çıkılmaz", ok and not calls)
check("durum: anahtar yok", r.status()["providers"][0]["state"] == "anahtar yok" and not r.ready())

r = new()
script.append((200, {}, ok_body("<think>düşünüyorum</think>Ters çevirmek için liste[::-1] kullan.", 20, 9)))
rep = r.chat(MSG, effort="low")
url, hdr, body = calls[0]
check("başarılı çağrı: metin, sağlayıcı, jeton", rep.text == "Ters çevirmek için liste[::-1] kullan." and rep.provider == "groq" and rep.tokens_in == 20 and rep.tokens_out == 9)
check("istek: doğru adres, Bearer anahtar, User-Agent, ilk model, akıl yürütme düzeyi", url == "https://api.groq.com/openai/v1/chat/completions" and hdr["Authorization"].startswith("Bearer gsk_")
      and "python" not in hdr["User-Agent"].lower() and body["model"] == "openai/gpt-oss-120b" and body["reasoning_effort"] == "low")
st = r.status()
check("sayaç: çağrı ve jeton günlük kayda geçer", st["calls"] == 1 and st["tokens"] == 29)
check("durum çıktısı anahtarı içermez", "gsk_" not in json.dumps(st) and "gsk_" not in Path(_store.DATA_DIR / "router_stats.json").read_text())

# 429 -> sıradaki model; bekleme süresi dolunca birincil tekrar denenir
r = new()
script.extend([(429, {"retry-after": "30"}, {"error": {"message": "rate limit"}}), (200, {}, ok_body("ikinci model"))])
rep = r.chat(MSG)
check("429: sıradaki modele düşer", rep.text == "ikinci model" and rep.model == "qwen/qwen3.8-27b" and len(calls) == 2)
st = r.status()["providers"][0]["models"][0]
check("429: model Retry-After kadar bekletilir (pano 'bekliyor')", st["state"] == "bekliyor" and st["wait"] == 30)
script.append((200, {}, ok_body("yine ikinci")))
r.chat(MSG)
check("beklerken birincil atlanır", calls[-1][2]["model"] == "qwen/qwen3.8-27b")
clock[0] += 31
script.append((200, {}, ok_body("birinci")))
check("bekleme bitince birincil geri döner", r.chat(MSG).model == "openai/gpt-oss-120b")

# 401 -> sağlayıcı kapanır
r = new()
script.append((401, {}, {"error": {"message": "invalid api key"}}))
try:
    r.chat(MSG)
    ok = False
except R.Unavailable:
    ok = True
n = len(calls)
try:
    r.chat(MSG)
except R.Unavailable:
    pass
check("401: anahtar reddedilince sağlayıcı kapanır, tekrar denenmez", ok and len(calls) == n and r.status()["providers"][0]["state"] == "anahtar reddedildi")

# 404 model yok -> o model kapanır
r = new()
script.extend([(404, {}, {"error": {"message": "model_not_found"}}), (200, {}, ok_body("diğer"))])
rep = r.chat(MSG)
r.chat(MSG)
check("404: model kapatılır, sonraki çağrıda denenmez", rep.model == "qwen/qwen3.8-27b" and all(c[2]["model"] != "openai/gpt-oss-120b" for c in calls[2:]))

# 400 isteğe bağlı parametre -> onsuz tekrar
r = new()
script.extend([(400, {}, {"error": {"message": "reasoning_effort is not supported"}}), (200, {}, ok_body("onsuz oldu"))])
rep = r.chat(MSG, json_mode=True)
check("400: desteklenmeyen isteğe bağlı parametre atılıp aynı modelle tekrar denenir", rep.text == "onsuz oldu" and "reasoning_effort" not in calls[1][2] and "response_format" not in calls[1][2] and calls[1][2]["model"] == calls[0][2]["model"])

# ağ hatası / boş cevap -> sıradaki
r = new()
script.extend([TimeoutError("zaman aşımı"), (200, {}, ok_body("   ")), (200, {}, ok_body("üçüncü"))])
rep = r.chat(MSG)
check("ağ hatası ve boş cevap: sıradaki modeller denenir", rep.text == "üçüncü" and len(calls) == 3)

# hepsi tükenirse
r = new()
script.extend([(429, {"retry-after": "10"}, {})] * 5)
try:
    r.chat(MSG)
    ok = False
except R.Unavailable as e:
    ok = "429" in str(e)
check("hepsi limitte: Unavailable (yerel modele dönülür)", ok and len(calls) == 5)

# engeller
r = new()
for msgs, why in (([{"role": "user", "content": "şifrem: kedi1234 bunu çöz"}], "parola"), ([{"role": "user", "content": "x", "private": True}], "özel")):
    try:
        r.chat(msgs)
        ok = False
    except privacy.Blocked as b:
        ok = why in b.text
    check(f"engel: {why} içeren mesaj buluta HİÇ gitmez", ok and not calls)
check("engel sayacı ve son neden panoya yansır", r.status()["blocked"] == 2)
try:
    r.chat(MSG, task="chat")
    ok = False
except privacy.Blocked:
    ok = not calls
check("engel: bulut yalnızca zor görevlerde (task=chat reddedilir)", ok)
ui_state.set_cloud_enabled(False)
try:
    r.chat(MSG)
    ok = False
except privacy.Blocked as b:
    ok = "kapalı" in b.text and not calls
check("ayar: bulut kapalıyken hiçbir şey gitmez", ok and not r.status()["enabled"])
ui_state.set_cloud_enabled(True)
try:
    r.chat([{"role": "user", "content": "kod: " + "x = 1\n" * 3000}])
    ok = False
except R.TooLarge:
    ok = not calls
check("büyük girdi ücretsiz sınıra sığmaz: TooLarge, ağa çıkılmaz", ok)
r.chat([{"role": "user", "content": "hata: File /home/furkan/a.py satır 2"}])
check("ev yolu bulutta kullanıcı adı olmadan gider", "furkan" not in json.dumps(calls[-1][2]) and "/home/kullanici/a.py" in json.dumps(calls[-1][2]))

# ek sağlayıcı (data/models.json): groq tükenince devreye girer
os.environ["MISTRAL_API_KEY"] = "mk_testtesttesttest"
r = new(cfg={"providers": {"mistral": {"label": "Mistral", "base_url": "https://api.mistral.ai/v1/", "key_env": "MISTRAL_API_KEY", "models": ["mistral-small-latest"]}}})
script.extend([(429, {"retry-after": "5"}, {})] * 5 + [(200, {}, ok_body("mistral cevabı"))])
rep = r.chat(MSG)
check("models.json: ek sağlayıcı zincire eklenir, yedek olarak kullanılır", rep.provider == "mistral" and calls[-1][0] == "https://api.mistral.ai/v1/chat/completions")
os.environ.pop("MISTRAL_API_KEY")

# .env dosyası
envf = Path(_store.DATA_DIR) / "keys.env"
envf.write_text("# yorum\nTEST_A_KEY=\"abc123\"\nexport TEST_B_KEY=xyz\nBOS=\nTEST_C_KEY=eski\n", encoding="utf-8")
os.environ["TEST_C_KEY"] = "ortam"
used = R.load_env()
check("keys.env okunur (tırnak/export), ortamdaki değeri ezmez, boşları atlar", os.environ.get("TEST_A_KEY") == "abc123" and os.environ.get("TEST_B_KEY") == "xyz"
      and os.environ.get("TEST_C_KEY") == "ortam" and "BOS" not in os.environ and used)
envf.unlink()
p = R.init_env_file()
check("şablon oluşturulur ve yalnızca sahibi okuyabilir", "GROQ_API_KEY=" in p.read_text() and (p.stat().st_mode & 0o077) == 0)
p.unlink()

# ---------------------------------------------------------------- Brain: "bulut: ..." komutu
import brain as B  # noqa: E402

check("'bulut:' kalıbı: eşleşenler", all(B.WORD_CLOUD.match(t) for t in ("bulut: python'da sözlük nasıl sıralanır", "Bulutta sor, kuantum nedir ve nasıl çalışır", "bulut çöz: 17 çarpı 23 kaç eder")))
check("'bulut:' kalıbı: sıradan cümleler eşleşmez", not any(B.WORD_CLOUD.match(t) for t in ("bulutlar neden oluşur", "bulut nedir", "bulut hesaplama nedir anlat", "bugün hava bulutlu mu")))

br = B.Brain(model="x", tools={})
r = new()
br.router = r
script.append((200, {}, ok_body("Sözlüğü sorted ile sırala.")))
out = "".join(br.reply_stream("bulut: python'da sözlük nasıl sıralanır"))
sent = calls[-1][2]["messages"]
check("Brain: bulut cevabı döner, yalnızca sistem+soru gönderilir (geçmiş/hafıza yok)", out == "Sözlüğü sorted ile sırala." and [m["role"] for m in sent] == ["system", "user"] and sent[1]["content"] == "python'da sözlük nasıl sıralanır")
check("Brain: aktif model bulut olarak görünür, geçmişe işlenir", br.active_model == "groq/openai/gpt-oss-120b" and br.history[-1]["content"] == out)
n = len(calls)
out = "".join(br.reply_stream("bulut: şifrem: kedi1234 bunu hatırla"))
check("Brain: kişisel veri varsa buluta gitmez, kullanıcıya söylenir", len(calls) == n and "göndermedim" in out and "parola" in out)
script.extend([(429, {"retry-after": "9"}, {})] * 5)
out = "".join(br.reply_stream("bulut: kuantum bilgisayar nedir kısaca"))
check("Brain: bulut yoksa yerel modele dönmeyi önerir (çökmez)", "ulaşamadım" in out)

# ---------------------------------------------------------------- pano: komut + durum
from dashboard import server, state  # noqa: E402

d = server.Dashboard(types.SimpleNamespace(brain=br), lambda *a, **k: None, port=18711)
before = ui_state.cloud_enabled()
d.run_command("cloudtoggle")
check("pano komutu 'cloudtoggle' bulutu açar/kapar", ui_state.cloud_enabled() is (not before))
d.run_command("cloudtoggle")
d.httpd.server_close()
br.model = "gemma4:e4b"
br.tool_count = 0
ms = state.build_state(types.SimpleNamespace(brain=br, fallbacks=[]))
check("pano durumu: model.cloud sağlayıcı/engel bilgisi taşır, anahtar yok", ms["model"]["cloud"]["providers"][0]["label"] == "Groq" and "gsk_" not in json.dumps(ms))
check("pano durumu: durum.cloud alanı", ms["durum"]["cloud"] is True)

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
