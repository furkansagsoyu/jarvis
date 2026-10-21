"""Telefon becerisi testleri (gerçek telefon/adb olmadan, sahte ADB ile): numara güvenliği, rehber eşleşmesi, onay kapısı,
arama doğrulaması, Xiaomi yedek yolu, kapatma/açma, rehber alma."""
import os
import sys
import tempfile
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
from skills import _confirm as confirm  # noqa: E402
from skills import phone as P  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


class FakePhone:
    def __init__(self):
        self.log, self.state, self.devs = [], 0, "List of devices attached\nABC123\tdevice\n"
        self.call_ok, self.dial_ok, self.key_ok, self.contacts_out, self.call_starts = True, True, True, "", True

    def run(self, args, timeout=0):
        self.log.append(args)
        if args[1:2] == ["devices"]:
            return 0, self.devs
        cmd = args[4:] if args[1:2] == ["-s"] else args[1:]
        if cmd[:3] == ["dumpsys", "telephony.registry"]:
            return 0, f"  mCallState={self.state}\n  mCallState={self.state}"
        if cmd[:2] == ["am", "start"]:
            if "android.intent.action.CALL" in cmd:
                if not self.call_ok:
                    return 0, "java.lang.SecurityException: Permission Denial"
                if self.call_starts:
                    self.state = 2
                return 0, "Starting: Intent { act=android.intent.action.CALL }"
            return (0, "Starting: Intent { act=DIAL }") if self.dial_ok else (1, "Error")
        if cmd[:2] == ["input", "keyevent"]:
            if not self.key_ok:
                return 1, "java.lang.SecurityException: Injecting to another application requires INJECT_EVENTS permission"
            self.state = 0
            return 0, ""
        if cmd[:2] == ["content", "query"]:
            return 0, self.contacts_out
        return 1, "?"


fake = FakePhone()
P.adb_path = lambda: "/usr/bin/adb"
P._run = fake.run
P.time.sleep = lambda s: None

# --- numara doğrulama (adb shell bir kabuktan geçer: enjeksiyon olmamalı)
check("numara temizlenir", P.clean_number("0555 123 45 67") == "05551234567" and P.clean_number("+90 (555) 123-45-67") == "+905551234567")
for bad_num in ("0555;reboot", "*#06#", "0555$(id)", "05 55 `ls`", "12", "", "abc", "1234567890123456", "0555\nreboot"):
    check(f"geçersiz numara reddedilir: {bad_num!r}", P.clean_number(bad_num) is None)
check("USSD/enjeksiyon hedefi aramaya dönüşmez", all(P.phone_call(t).startswith(("Numara", "Bu arama", "Rehber")) for t in ("*#06#", "0555;reboot", "#21#")) and not confirm.has_pending())

# --- rehber
check("rehber boşken yardımcı mesaj", "Rehberim boş" in P.phone_call("Annem"))
P.add_contact("Annem", "0555 111 22 33")
P.add_contact("Ahmet Yılmaz", "0532 000 00 01")
P.add_contact("Ahmet Kaya", "0532 000 00 02")
P.add_contact("Ayşe", "+90 533 000 00 03")
check("kayıt temiz numara olarak durur", P.contacts()["Annem"] == "05551112233" and P.contacts()["Ayşe"] == "+905330000003")
check("geçersiz numara kaydedilmez", P.add_contact("Kötü", "0555;rm").startswith("Hata") and "Kötü" not in P.contacts())
check("aynı ad güncellenir, çoğalmaz", "güncellendi" in P.add_contact("annem", "0555 111 22 34") and len([k for k in P.contacts() if k.lower() == "annem"]) == 1)
P.add_contact("Annem", "0555 111 22 33")
def who(q): return P.resolve(q)[:2]
check("'Annemi' -> Annem (ek soyma)", who("Annemi") == ("Annem", "05551112233"))
check("'Ayşe'yi' ve STT yazım farkı 'Ayse'", who("Ayşe'yi")[0] == "Ayşe" and who("Ayse")[0] == "Ayşe")
check("tam ad + ek: 'Ahmet Yılmaz'ı'", who("Ahmet Yılmaz'ı")[0] == "Ahmet Yılmaz")
check("yalnız ilk ad iki kişiye uyuyorsa sorar", "birden fazla" in P.resolve("Ahmet'i")[2] and "Ahmet Kaya" in P.resolve("Ahmet'i")[2])
check("rehberde yoksa söyler, numara uydurmaz", "Rehberde" in P.resolve("Mehmet")[2] and not P.resolve("Mehmet")[1])
check("rakam doğrudan numara; ek atılır", P.resolve("0555 123 45 67'yi")[1] == "05551234567" and P.resolve("0555 123 45 67 numarasını")[1] == "05551234567")
check("'bunu/google' gibi sözcükler aramaya dönüşmez", all(P.resolve(t)[2] for t in ("bunu", "google'da")))

check("hızlı yol: tanıdık ad/numara telefona, arama motoru cümlesi değil",
      P.callable_target("Annemi") and P.callable_target("0555 123 45 67'yi") and P.callable_target("Mehmet'i")
      and not P.callable_target("bu kelimeyi sözlükte") and not P.callable_target("python'da") and not P.callable_target("google"))

# --- onay kapısı + arama
q = P.phone_call("Annemi")
check("arama önce onay ister, henüz aramaz", "Onaylıyor musun" in q and "Annem" in q and "2 2 3 3" in q, q)
check("onay gelmeden adb am start çağrılmadı", not any("am" in a and "start" in a for a in fake.log))
res = confirm.approve()
cmd = [a for a in fake.log if "android.intent.action.CALL" in a][-1]
check("onaydan sonra CALL intent'i doğru numarayla gider", cmd[:5] == ["/usr/bin/adb", "-s", "ABC123", "shell", "am"] and cmd[-1] == "tel:05551112233", str(cmd))
check("durum okunup doğrulanınca 'aranıyor' denir", res == "Annem aranıyor.", res)

# iptal
P.phone_call("Annemi"); confirm.cancel()
n = len(fake.log)
check("iptalde arama yapılmaz", not confirm.has_pending() and confirm.approve().startswith("Onay süresi"))

# Xiaomi: doğrudan arama engelli -> arama ekranı
fake.state, fake.call_ok = 0, False
P.phone_call("Annemi")
res = confirm.approve()
check("CALL engellenirse DIAL'a düşer ve dürüstçe söyler", "yeşil tuşa sen bas" in res and "aranıyor" not in res, res)
fake.call_ok = True
# komut gitti ama görüşme başlamadı
fake.state, fake.call_starts = 0, False
P.phone_call("Annemi")
res = confirm.approve()
check("görüşme başlamadıysa 'aranıyor' DENMEZ", "aranıyor" not in res and "başlamadı" in res, res)
fake.call_starts = True

# telefon yok / izinsiz
fake.devs = "List of devices attached\n"
check("telefon bağlı değilse onay bile istenmez", "bağlı görünmüyor" in P.phone_call("Annemi") and not confirm.has_pending())
fake.devs = "List of devices attached\nABC123\tunauthorized\n"
check("yetkisiz telefon: izin penceresini söyler", "izin" in P.phone_call("Annemi") and not confirm.has_pending())
fake.devs = "List of devices attached\nABC123\tdevice\n"

# --- kapat / aç
fake.state = 0
check("arama yokken kapat", P.phone_hangup() == "Şu an açık bir arama yok.")
fake.state = 2
check("kapat: ENDCALL gönderilir ve doğrulanır", P.phone_hangup() == "Aramayı kapattım." and fake.state == 0)
fake.state, fake.key_ok = 2, False
r = P.phone_hangup()
check("tuş izni yoksa Xiaomi güvenlik ayarını söyler", "Güvenlik ayarları" in r and "kapattım" not in r, r)
fake.key_ok = True
fake.state = 0
check("çalan arama yokken aç", P.phone_answer() == "Şu an çalan bir arama yok.")
fake.state = 1
orig = fake.run
def run_answer(args, timeout=0):
    if "KEYCODE_CALL" in args: fake.state = 2; return 0, ""
    return orig(args, timeout)
P._run = run_answer
check("çalan aramayı açar", P.phone_answer() == "Aramayı açtım.")
P._run = orig
fake.state = 2
check("durum", "görüşme var" in P.phone_status())

# --- rehberi telefondan alma
fake.contacts_out = ("Row: 0 display_name=Baba, data1=0 532 111 11 11\nRow: 1 display_name=Doe, John, data1=+90 533 222 22 22\n"
                     "Row: 2 display_name=Annem, data1=0555 999 99 99\nRow: 3 display_name=NULL, data1=123\nRow: 4 display_name=Bozuk, data1=x;y\n")
r = P.sync_contacts()
book = P.contacts()
check("rehber alınır: yeni kişiler eklenir, var olan ezilmez, bozuk numara atılır",
      "Baba" in book and book["Baba"] == "05321111111" and book["Annem"] == "05551112233" and "Bozuk" not in book and "NULL" not in book and "2 yenisini" in r, r + str(book))
check("virgüllü ad ayrıştırılır", book.get("Doe, John") == "+905332222222")
fake.contacts_out = "Permission Denial: opening provider"
check("rehber izni yoksa elle ekleme yolunu gösterir", "izin verilmedi" in P.sync_contacts())

# --- gizlilik: telefon araçları uzaktan (Telegram) çalışmaz ve model şemasında görünmez
import brain  # noqa: E402
from skills import HIDDEN, load_skills  # noqa: E402
tools = load_skills()
check("telefon araçları gizli (modelin şemasında yok)", all(n in HIDDEN for n in ("phone_call", "phone_hangup", "phone_answer", "contact_add", "contacts_sync")))
check("telefon araçları Telegram'dan engelli", all(n in brain.REMOTE_BLOCKED for n in ("phone_call", "phone_hangup", "phone_answer", "contact_add", "contacts_sync", "phone_status")))
import team  # noqa: E402
check("ekip rollerinde telefon aracı yok", not any(t.startswith(("phone", "contact")) for r in team.ROLES.values() for t in r.tools))
import agent  # noqa: E402
check("ajan modunda telefon aracı yok", not any(t.startswith(("phone", "contact")) for t in agent.ALLOWED))

sys.exit(1 if bad else 0)
