"""Telefon uygulaması bağlantısı (FCM) testleri: imza biçimi (Kotlin ile birebir), gönderim, hata eşleme, eşleştirme, ADB/uygulama seçimi."""
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import tempfile
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
import phonelink as L  # noqa: E402
from skills import _confirm as confirm  # noqa: E402
from skills import _store  # noqa: E402
from skills import phone as P  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


# --- imza: uygulamadaki Verifier.sign ile aynı kanonik metin
d = {"cmd": "call", "name": "Anılinho", "ts": "1760000000", "nonce": "ab12"}
want = hmac.new(b"gizli", "call|Anılinho|||||1760000000|ab12".encode("utf-8"), hashlib.sha256).hexdigest()
check("imza: alan sırası cmd|name|title|body|at|id|ts|nonce, boş alanlar boş, UTF-8", L.sign("gizli", d) == want)
check("alan sırası Kotlin'dekiyle aynı (Verifier.FIELDS)", L.FIELDS == tuple(
    __import__("re").search(r'FIELDS = listOf\((.*?)\)', open("phone_app/android/app/src/main/kotlin/com/furkan/jarvisphone/Verifier.kt").read()).group(1).replace('"', "").replace(" ", "").split(",")))
b1, b2 = L.build_data("call", "k", name="Ahmet"), L.build_data("call", "k", name="Ahmet")
check("veri alanları string, imza içerir, her mesajın nonce'u farklı", all(isinstance(v, str) for v in b1.values()) and b1["nonce"] != b2["nonce"] and L.sign("k", b1) == b1["sig"])
check("bilinmeyen/boş alan eklenmez (numara alanı yok)", "number" not in L.build_data("call", "k", number="0555", name="")
      and "name" not in L.build_data("call", "k", name=""))

# --- yapılandırma yokken
check("yapılandırma yokken gönderilmez", not L.configured() and L.send("ping")[0] is False and "kurulu değil" in L.send("ping")[1])

# --- gönderim (sahte erişim belirteci ve HTTP)
_store.save(L.CFG_FILE, {"project_id": "jarvis-x", "token": "TOK123", "secret": "ab" * 32})
(_store.path(L.SA_FILE)).write_text(json.dumps({"project_id": "jarvis-x", "type": "service_account"}))
check("yapılandırma tamamsa hazır", L.configured())
calls = []
L._access_token = lambda: "ACCESS"
reply = {"v": (200, "{}")}
def fake_post(url, headers, body, timeout=10):
    calls.append((url, headers, body))
    return reply["v"]
L._post = fake_post
ok, msg = L.send("call", ttl=60, name="Anılinho")
url, headers, body = calls[-1]
m = body["message"]
check("istek: doğru proje URL'i, Bearer, yüksek öncelik, ttl, belirteç", ok and url == "https://fcm.googleapis.com/v1/projects/jarvis-x/messages:send"
      and headers["Authorization"] == "Bearer ACCESS" and m["android"] == {"priority": "HIGH", "ttl": "60s"} and m["token"] == "TOK123")
check("mesajda numara/gizli anahtar YOK, imza doğrulanır", "secret" not in json.dumps(body) and ("ab" * 32) not in json.dumps(body)
      and L.sign("ab" * 32, {k: v for k, v in m["data"].items() if k != "sig"}) == m["data"]["sig"] and m["data"]["name"] == "Anılinho")
for code, text, frag in ((404, '{"error":{"status":"NOT_FOUND"}}', "kaydı geçersiz"), (400, "UNREGISTERED", "kaydı geçersiz"), (403, "x", "izin vermedi"),
                         (401, "x", "izin vermedi"), (429, "x", "sınırı"), (0, "timeout", "ulaşılamadı"), (500, "x", "hata verdi (500)")):
    reply["v"] = (code, text)
    ok, msg = L.send("ping")
    check(f"HTTP {code} -> anlaşılır mesaj", not ok and frag in msg, msg)
reply["v"] = (200, "{}")

# --- eşleştirme
log = []
state = {"token_line": "10-24 20:50:00.1  1  1 I JarvisPhone: TOKEN=eK3x:APA91b-Gizli_Token", "paired": True}
def fake_run(args, timeout=10):
    log.append(args)
    if "logcat" in args and "-d" in args:
        return 0, state["token_line"] + ("\n10-24 20:50:02.1  1  1 I JarvisPhone: PAIRED_OK" if state["paired"] else "")
    return 0, ""
L.time.sleep = lambda s: None
_store.path(L.CFG_FILE).unlink()
r = L.pair("/usr/bin/adb", "ABC123", fake_run)
cfg = L.config()
bro = [a for a in log if "broadcast" in a and f"{L.PACKAGE}.PAIR" in a][-1]
check("eşleştirme: belirteç logcat'ten, gizli anahtar telefona yazılır ve kaydedilir", r.startswith("Eşleşti") and cfg["token"] == "eK3x:APA91b-Gizli_Token"
      and cfg["project_id"] == "jarvis-x" and len(cfg["secret"]) == 64 and bro[-1] == cfg["secret"] and bro[-2] == "secret", r + str(cfg))
check("gizli anahtar yalnızca hex (ADB kabuğuna güvenle gider)", __import__("re").fullmatch(r"[0-9a-f]{64}", cfg["secret"]) is not None)
state["paired"] = False; _store.path(L.CFG_FILE).unlink()
check("telefon anahtarı kabul etmezse kaydedilmez", "kabul etmedi" in L.pair("/usr/bin/adb", "ABC123", fake_run) and not L.config())
state["token_line"] = "hiçbir şey"
check("belirteç yoksa anlaşılır hata", "belirteç alınamadı" in L.pair("/usr/bin/adb", "ABC123", fake_run))
_store.path(L.SA_FILE).unlink()
check("servis hesabı dosyası yoksa nereye koyulacağını söyler", "fcm_service_account.json" in L.pair("/usr/bin/adb", "ABC123", fake_run))
(_store.path(L.SA_FILE)).write_text(json.dumps({"project_id": "jarvis-x"}))
_store.save(L.CFG_FILE, {"project_id": "jarvis-x", "token": "TOK123", "secret": "cd" * 32})

# --- phone.py: ADB mi uygulama mı
P.adb_path = lambda: "/usr/bin/adb"
devs = {"v": "List of devices attached\n"}
P._run = lambda args, timeout=0: (0, devs["v"]) if args[1:2] == ["devices"] else (1, "?")
P._last_try = 1e12   # kablosuz yeniden bağlanma denemesi bu testte kapalı
P.add_contact("Anılinho", "0555 000 11 22")
calls.clear()
q = P.phone_call("Anılinho")
check("ADB yok + uygulama hazır: onay sorulur (henüz gönderilmez)", "Onaylıyor musun" in q and not calls, q)
res = confirm.approve()
check("onaydan sonra komut telefona gider; 'aranıyor' DENMEZ (doğrulayamayız)", calls and calls[-1][2]["message"]["data"]["cmd"] == "call"
      and calls[-1][2]["message"]["data"]["name"] == "Anılinho" and "gönderdim" in res and "aranıyor" not in res, res)
check("numara FCM'e HİÇ girmedi", "0555" not in json.dumps(calls[-1][2]) and "05550001122" not in json.dumps(calls[-1][2]))
n = len(calls)
r = P.phone_call("0555 123 45 67")
check("ham numara + ADB yok: internetten aranmaz, nedenini söyler", "ADB bağlıyken" in r and not confirm.has_pending() and len(calls) == n, r)
reply["v"] = (404, "UNREGISTERED")
P.phone_call("Anılinho"); res = confirm.approve()
check("Firebase reddederse dürüst hata", res.startswith("Hata") and "kaydı geçersiz" in res, res)
reply["v"] = (200, "{}")
devs["v"] = "List of devices attached\nABC123\tdevice\n"
n = len(calls)
P.phone_call("Anılinho")
check("ADB hazırsa uygulama kullanılmaz (ADB önceliklidir)", confirm.has_pending() and len(calls) == n)
confirm.cancel()
devs["v"] = "List of devices attached\n"
n = len(calls)
check("kapatma: ADB yokken uygulamaya gider", P.phone_hangup() == "Kapatma komutunu telefona gönderdim." and calls[-1][2]["message"]["data"]["cmd"] == "hangup" and len(calls) == n + 1)

# --- alarm çaldırma
got, err = P._ring_when("telefonu yarın saat 14'te çaldır toplantı")
tomorrow = dt.date.today() + dt.timedelta(days=1)
check("alarm: 'yarın saat 14' ve başlık ayrıştırılır", not err and got[0] == dt.datetime.combine(tomorrow, dt.time(14, 0)) and got[1] == "Toplantı", str(got) + err)
check("alarm: saat yoksa reddedilir", "Saati anlayamadım" in P._ring_when("telefonu çaldır toplantı")[1])
calls.clear()
r = P.phone_ring("telefonu yarın saat 14'te çaldır, toplantı")
d = calls[-1][2]["message"]["data"]
check("alarm uygulamaya zamanlı gider: at (ms), başlık, kimlik; imzalı", "kurdum" in r and d["cmd"] == "ring" and int(d["at"]) == int(dt.datetime.combine(tomorrow, dt.time(14, 0)).timestamp() * 1000)
      and d["title"] == "Toplantı" and d["id"].startswith("r") and L.sign("cd" * 32, {k: v for k, v in d.items() if k != "sig"}) == d["sig"], r + str(d))

# --- yönlendirme
from brain import Brain  # noqa: E402
b = Brain(tools=None)
check("hızlı yol: 'telefonu yarın saat 14'te çaldır' -> phone_ring", b._fast_route("telefonu yarın saat 14'te çaldır toplantı")[0][0] == "phone_ring"
      and b._fast_route("toplantı için telefonuma alarm kur yarın 9")[0][0] == "phone_ring")
check("hızlı yol: telefonsuz alarm cümlesi telefona gitmez", not b._fast_route("yarın saat 9'a alarm kur") or b._fast_route("yarın saat 9'a alarm kur")[0][0] != "phone_ring")

# --- ayarlar: via, hatırlatıcı/takvim telefona gider (genel metin), iptal
from skills import _phonenotify as N  # noqa: E402
from skills import agenda, reminders  # noqa: E402
L.set_setting("via", "app")
devs["v"] = "List of devices attached\nABC123\tdevice\n"     # ADB hazır olsa bile
n = len(calls)
P.phone_call("Anılinho")
check("via=app: ADB hazır olsa da uygulama yolu kullanılır", confirm.has_pending()); res = confirm.approve()
check("via=app: komut Firebase'e gitti", len(calls) == n + 1 and calls[-1][2]["message"]["data"]["cmd"] == "call", res)
L.set_setting("via", "adb")
n = len(calls); devs["v"] = "List of devices attached\n"
check("via=adb: ADB yokken uygulamaya düşmez", "Telefon bağlı görünmüyor" in P.phone_call("Anılinho") and len(calls) == n and not confirm.has_pending())
L.set_setting("via", "auto")
P.save_wireless("192.168.1.9:5555", "ABC123"); L.set_setting("via", "auto")
check("ayarlar ve kablosuz kayıt aynı dosyada birbirini bozmaz", P.wireless_config().get("addr") == "192.168.1.9:5555" and L.setting("via") == "auto")

calls.clear(); sent_at = {}
text = reminders.set_reminder(minutes=5, message="ilacı al")
d = calls[-1][2]["message"]["data"]
check("hatırlatıcı telefona alarm olarak gider, metin gitmez (generic)", d["cmd"] == "ring" and d["id"].startswith("rem") and "ilac" not in json.dumps(d, ensure_ascii=False).lower()
      and "ilacı" not in json.dumps(d, ensure_ascii=False) and "Telefonuna da alarm kurdum" in text, text + str(d))
L.set_setting("detail", "full"); calls.clear()
reminders.set_reminder(minutes=6, message="ilacı al")
check("detail=full: başlık da gider", calls[-1][2]["message"]["data"]["title"] == "ilacı al")
L.set_setting("detail", "generic")
calls.clear(); reminders.cancel_reminders()
check("hatırlatıcılar iptal edilince telefondaki alarmlar da iptal edilir", sum(1 for c in calls if c[2]["message"]["data"]["cmd"] == "cancel") == 2)
reply["v"] = (500, "x"); calls.clear()
text = reminders.set_reminder(minutes=5, message="x")
check("telefona gidemezse hatırlatıcı yine kurulur, dürüstçe söyler", "sonra hatırlatacağım" in text and "gönderemedim" in text, text)
reply["v"] = (200, "{}")
reminders.cancel_reminders()
calls.clear()
tm = (dt.datetime.now() + dt.timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
agenda.add_event(title="Toplantı", date=tm.date().isoformat(), time_="14:00")
d = calls[-1][2]["message"]["data"]
check("takvim etkinliği: telefona hatırlatma süresinden önce (13:50) alarm olarak gider", d["cmd"] == "ring"
      and int(d["at"]) == int((tm - dt.timedelta(minutes=10)).timestamp() * 1000) and d["id"].startswith("ev") and "Toplantı" not in json.dumps(d, ensure_ascii=False), str(d))
calls.clear()
agenda.cancel_event_id(int(d["id"][2:]))
check("etkinlik silinince telefondaki alarm da iptal edilir", calls and calls[-1][2]["message"]["data"]["cmd"] == "cancel" and calls[-1][2]["message"]["data"]["id"] == d["id"])
L.set_setting("alerts", False); calls.clear()
reminders.set_reminder(minutes=5, message="x"); reminders.cancel_reminders()
check("alerts=off: telefona hiçbir şey gitmez", not calls and not N.enabled())
L.set_setting("alerts", True)
import time as _t  # noqa: E402
import threading as _th  # noqa: E402
L.DEADLINE = 0.3; L._send = lambda *a, **k: (_th.Event().wait(2), (True, "x"))[1]
t0 = _t.time(); r = L.send("ping")
check("gönderim zaman aşımına uğrar", r == (False, "Firebase zamanında yanıt vermedi.") and _t.time() - t0 < 1.5, str(r))

# --- uygulama kaynak dosyaları tutarlı
import re  # noqa: E402
root = "phone_app/android/app/src/main"
man = open(f"{root}/AndroidManifest.xml").read()
kt = "".join(open(os.path.join(dp, f)).read() for dp, _, fs in os.walk(f"{root}/kotlin") for f in fs if f.endswith(".kt"))
for cls in ("JarvisMessagingService", "AlarmReceiver", "AlarmService", "BootReceiver", "PairReceiver", "MainActivity"):
    check(f"manifest sınıfı var: {cls}", f".{cls}" in man and re.search(rf"class {cls}\b", kt) is not None)
check("PairReceiver yalnızca ADB kabuğuna açık (DUMP izni)", re.search(r'PairReceiver"[^>]*android:permission="android.permission.DUMP"', man.replace("\n", " ")) is not None)
check("PC'nin gönderdiği eylem adları uygulamada tanımlı", all(f'"{c}" ->' in kt for c in ("call", "hangup", "ring", "cancel", "ping")) and f"{L.PACKAGE}.PAIR" in kt and f"{L.PACKAGE}.TOKEN" in kt)
check("alarm servisi medya oynatma türünde ve izinli (Android 14)", 'foregroundServiceType="mediaPlayback"' in man and "FOREGROUND_SERVICE_MEDIA_PLAYBACK" in man
      and "FOREGROUND_SERVICE\"" in man)
check("alarm sesi bildirimle değil servisle çalınır; yedek yol var", "startForegroundService" in kt and "USAGE_ALARM" in kt and "showAlarmNotification" in kt and "isLooping = true" in kt)
check("paket adı her yerde aynı", all(f"package {L.PACKAGE}" in open(os.path.join(dp, f)).read() for dp, _, fs in os.walk(f"{root}/kotlin") for f in fs if f.endswith(".kt")))

sys.exit(1 if bad else 0)
