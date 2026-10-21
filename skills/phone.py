"""Telefon araması (Android, ADB ile): ara, kapat, gelen aramayı aç, rehber.

Güvenlik:
- Arama HER ZAMAN sesli onay ister (skills/_confirm.py); model onaylayamaz. Araçlar "hidden": yalnızca kural tabanlı hızlı yoldan çağrılır.
- Numara sıkı doğrulanır (yalnızca rakam ve baştaki +). `adb shell` komutu telefonda bir kabuktan geçtiği için bu şarttır;
  '#', '*', ';' gibi karakterler (USSD/MMI kodları, komut ekleme) asla gönderilmez.
- Rehber yalnızca data/contacts.json'da (yerel, git dışı) durur; buluta ve Telegram'a gitmez.
"""
import difflib
import os
import re
import shutil
import subprocess
import time

from . import _confirm, _store

CONTACTS_FILE = "contacts.json"
ADB_TIMEOUT = 12
NUMBER = re.compile(r"\+?\d{3,15}")
NOISE_WORDS = {"internet", "internette", "web", "google", "youtube", "site", "sitede", "sitesinde", "wikipedia", "vikipedi", "tarayıcı", "dosya", "dosyada", "kelime", "bunu", "şunu", "onu"}
# Akrabalık sözcükleri: kullanıcı "Annemi ara" der, rehberde "Annem" yazar.
KIN = ("anne", "baba", "abla", "abi", "ağabey", "kardeş", "eş", "dayı", "teyze", "hala", "amca", "kuzen", "babaanne", "anneanne", "dede")


def _norm(s: str) -> str:
    s = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"\s+", " ", s).strip()


def _fold(s: str) -> str:
    """Aksan farkını yok sayan karşılaştırma anahtarı (STT 'Ayşe'yi 'Ayse' yazabilir)."""
    return _norm(s).translate(str.maketrans("çğıöşüâî", "cgiosuai"))


# ------------------------------------------------------------------ numara
def clean_number(raw: str) -> str | None:
    """'0555 123 45 67', '+90 (555) 123-45-67' -> '05551234567' / '+905551234567'. Geçersizse None."""
    s = re.sub(r"[\s\-().]", "", str(raw or ""))
    return s if NUMBER.fullmatch(s) else None


def _speak_tail(num: str) -> str:
    d = re.sub(r"\D", "", num)
    return " ".join(d[-4:]) if len(d) >= 4 else d


# ------------------------------------------------------------------ rehber
def contacts() -> dict:
    data = _store.load(CONTACTS_FILE, {})
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}


def add_contact(name: str, number: str) -> str:
    name = re.sub(r"\s+", " ", str(name or "")).strip(" '\"“”")
    num = clean_number(number)
    if not name or len(name) > 60:
        return "Hata: kişi adı anlaşılmadı."
    if not num:
        return "Hata: numara geçersiz. Yalnızca rakam ve baştaki artı kabul ederim."
    book = contacts()
    old = next((k for k in book if _fold(k) == _fold(name)), None)
    book[old or name] = num
    _store.save(CONTACTS_FILE, book)
    return f"{old or name} rehbere {'güncellendi' if old else 'eklendi'}."


def _stem_variants(q: str) -> list[str]:
    """'annemi' -> ['annemi','annem','anne'...]: yalın hâl bulunana kadar ek soyar (i, ı, u, ü, yi, yı, ni, nı, ye, ya, e, a, in, ın)."""
    out, seen = [q], {q}
    for suf in ("yi", "yı", "yu", "yü", "ni", "nı", "nu", "nü", "i", "ı", "u", "ü", "ye", "ya", "e", "a", "in", "ın", "un", "ün", "nin", "nın"):
        if q.endswith(suf) and len(q) - len(suf) >= 2:
            v = q[: -len(suf)]
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def find_contact(query: str) -> tuple[list[tuple[str, str]], str]:
    """Rehberde ara. (eşleşmeler, not). Not: '' | 'belirsiz' | 'yok'."""
    q = _norm(query)
    q = re.split(r"['’]", q)[0] if re.search(r"['’]", q) else q  # "Ahmet'i" -> "ahmet"; "Ahmet Yılmaz'ı" -> "ahmet yılmaz"
    q = re.sub(r"\b(lütfen|bana|şu|bir)\b", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    book = contacts()
    if not q or not book:
        return [], "yok"
    variants = [_fold(v) for v in _stem_variants(q)]
    names = {n: _fold(n) for n in book}
    # 1) tam eşleşme (ek soyulmuş hâliyle)
    for v in variants:
        exact = [n for n, f in names.items() if f == v]
        if exact:
            return [(exact[0], book[exact[0]])], ""
    # 2) ilk ad / sözcük eşleşmesi
    hits = []
    for v in variants:
        hits = [n for n, f in names.items() if v in f.split() or f.startswith(v + " ")]
        if hits:
            break
    # 3) bulanık eşleşme (STT yazım farkı)
    if not hits:
        for v in variants:
            close = difflib.get_close_matches(v, list(names.values()), n=3, cutoff=0.82)
            hits = [n for n, f in names.items() if f in close]
            if hits:
                break
    if not hits:
        return [], "yok"
    if len(hits) > 1:
        return [(n, book[n]) for n in hits], "belirsiz"
    return [(hits[0], book[hits[0]])], ""


def resolve(target: str) -> tuple[str, str, str]:
    """Hedef bir numara ya da kişi adı. (görünen ad, numara, hata). Hata boşsa başarılı."""
    t = str(target or "").strip()
    t = re.sub(r"(?<=\d)['’]\w+$", "", t)                       # "0555 123 45 67'yi" -> numara
    t = re.sub(r"\s+numara\w*$", "", t, flags=re.I).strip()      # "0555... numarasını"
    num = clean_number(t)
    if num:
        return ("bu numara", num, "")
    digits = re.sub(r"[\s\-().+]", "", t)
    if digits.isdigit():  # rakam gibi ama geçersiz (çok kısa/uzun)
        return ("", "", "Numara geçersiz görünüyor (3 ile 15 hane olmalı).")
    if re.search(r"[#*;&|$`<>]", t):
        return ("", "", "Bu arama isteğini güvenlik için reddettim.")
    if _fold(t).split()[:1] and set(_fold(t).split()) & NOISE_WORDS:
        return ("", "", "Kimi aramamı istediğini anlayamadım.")
    hits, note = find_contact(t)
    if note == "belirsiz":
        return ("", "", "Rehberde birden fazla eşleşme var: " + ", ".join(n for n, _ in hits[:4]) + ". Hangisi?")
    if note == "yok":
        if not contacts():
            return ("", "", "Rehberim boş. “rehbere ekle: Annem 0555 123 45 67” diyerek kişi ekleyebilir ya da “rehberi telefondan al” diyebilirsin.")
        return ("", "", f"Rehberde {re.split(chr(39) + '|’', t)[0]} diye biri yok. Numarasını söylersen “rehbere ekle” ile kaydederim.")
    name, number = hits[0]
    return (name, number, "")


def callable_target(name: str) -> bool:
    """Hızlı yol "X'i ara" cümlesini telefona mı yoksa aramaya (arama motoru) mı yönlendirsin?
    Numara ya da rehberde bulunan ad -> telefon. Bilinmeyen ad -> yalnızca kısa ve yer eki (-da/-de/-dan) taşımayan kişi adı gibiyse."""
    t = str(name or "").strip()
    if resolve(t)[1] or find_contact(t)[1] == "belirsiz":
        return True
    words = _fold(re.sub(r"['’]\w*", "", t)).split()
    if not words or len(words) > 2 or set(words) & NOISE_WORDS:
        return False
    last = _fold(t).split()[-1]
    return not re.search(r"(?:['’]?(?:n?da|n?de|ta|te|dan|den|tan|ten)|ile|için)$", last)


# ------------------------------------------------------------------ ADB
def adb_path() -> str | None:
    return shutil.which("adb")


def _run(args: list[str], timeout: int = ADB_TIMEOUT) -> tuple[int, str]:
    """adb'yi çalıştırır; (çıkış kodu, çıktı). Testlerde değiştirilir."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "zaman aşımı"
    except OSError as exc:
        return 127, str(exc)


def devices() -> list[tuple[str, str]]:
    adb = adb_path()
    if not adb:
        return []
    _, out = _run([adb, "devices"])
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and not line.startswith("*"):
            rows.append((parts[0], parts[1]))
    return rows


def pick_device() -> tuple[str | None, str]:
    """(seri no, hata). Hata boşsa hazır."""
    if not adb_path():
        return None, "ADB kurulu değil. Terminalde sudo apt install adb yaz."
    rows = devices()
    if not rows:
        return None, "Telefon bağlı görünmüyor. USB kablosunu tak ve USB hata ayıklamayı aç."
    want = os.environ.get("JARVIS_ADB_SERIAL", "")
    ready = [s for s, st in rows if st == "device" and (not want or s == want)]
    if ready:
        return ready[0], ""
    if any(st == "unauthorized" for _, st in rows):
        return None, "Telefon izin bekliyor. Ekrandaki “USB hata ayıklamaya izin ver” penceresini onayla."
    return None, "Telefon bağlı ama hazır değil (" + rows[0][1] + "). Kabloyu çıkarıp tak."


def _sh(serial: str, *cmd: str, timeout: int = ADB_TIMEOUT) -> tuple[int, str]:
    return _run([adb_path() or "adb", "-s", serial, "shell", *cmd], timeout)


def call_state(serial: str) -> int | None:
    """0 boşta, 1 çalıyor (gelen), 2 görüşmede/arıyor. Okunamazsa None."""
    code, out = _sh(serial, "dumpsys", "telephony.registry")
    if code != 0:
        return None
    states = [int(m) for m in re.findall(r"mCallState=(\d)", out)]
    return max(states) if states else None


def _wait_state(serial: str, want: set[int], seconds: float = 5.0) -> int | None:
    end, st = time.time() + seconds, None
    while True:
        st = call_state(serial)
        if st in want or time.time() >= end:
            return st
        time.sleep(0.8)


def _denied(out: str) -> bool:
    return bool(re.search(r"permission denial|securityexception|not allowed|izin|exception", out, re.I))


def _do_call(name: str, number: str) -> str:
    serial, err = pick_device()
    if not serial:
        return f"Hata: {err}"
    code, out = _sh(serial, "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{number}")
    if code != 0 or "Error" in out or _denied(out):
        # Xiaomi gibi telefonlar doğrudan aramayı engelleyebilir: arama ekranını numarayla açıp kullanıcıdan yeşil tuşa basmasını iste.
        code2, out2 = _sh(serial, "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{number}")
        if code2 == 0 and "Error" not in out2:
            return f"Telefon doğrudan aramaya izin vermedi. {name} için arama ekranını açtım, yeşil tuşa sen bas."
        return "Hata: telefonda arama başlatılamadı."
    state = _wait_state(serial, {2}, 5.0)
    if state == 2:
        return f"{name} aranıyor." if name != "bu numara" else "Arıyorum."
    if state is None:
        return f"{name} için arama komutunu gönderdim ama durumunu okuyamadım. Telefon ekranına bak." if name != "bu numara" else "Arama komutunu gönderdim ama durumunu okuyamadım. Telefon ekranına bak."
    return "Arama komutunu gönderdim ama telefonda görüşme başlamadı. Ekranda bir izin penceresi çıkmış olabilir, telefona bak."


def phone_call(target: str) -> str:
    name, number, err = resolve(target)
    if err:
        return err
    serial, derr = pick_device()
    if not serial:
        return derr
    who = f"{name} kişisini" if name != "bu numara" else "bu numarayı"
    return _confirm.request(f"{who}, numarası sonu {_speak_tail(number)} ile biten telefonu arayacağım.", lambda: _do_call(name, number))


def _key(serial: str, keycode: str) -> tuple[int, str]:
    return _sh(serial, "input", "keyevent", keycode)


def phone_hangup() -> str:
    serial, err = pick_device()
    if not serial:
        return err
    before = call_state(serial)
    if before == 0:
        return "Şu an açık bir arama yok."
    code, out = _key(serial, "KEYCODE_ENDCALL")
    if code != 0 or re.search(r"inject_events|securityexception|permission", out, re.I):
        return ("Aramayı kapatamadım: telefon tuş göndermeye izin vermiyor. Xiaomi'de Geliştirici seçenekleri içinde "
                "“USB hata ayıklama (Güvenlik ayarları)” da açık olmalı.")
    after = _wait_state(serial, {0}, 3.0)
    if after == 0:
        return "Aramayı kapattım."
    if after is None:
        return "Kapatma komutunu gönderdim ama durumunu okuyamadım."
    return "Kapatma komutunu gönderdim ama arama hâlâ açık görünüyor. Telefondan kapat."


def phone_answer() -> str:
    serial, err = pick_device()
    if not serial:
        return err
    if call_state(serial) != 1:
        return "Şu an çalan bir arama yok."
    code, out = _key(serial, "KEYCODE_CALL")
    if code != 0 or re.search(r"inject_events|securityexception|permission", out, re.I):
        return "Aramayı açamadım: telefon tuş göndermeye izin vermiyor (Güvenlik ayarları için USB hata ayıklama kapalı olabilir)."
    return "Aramayı açtım." if _wait_state(serial, {2}, 3.0) == 2 else "Aç komutunu gönderdim ama görüşme başlamadı gibi görünüyor."


def phone_status() -> str:
    serial, err = pick_device()
    if not serial:
        return err
    st = call_state(serial)
    txt = {0: "Telefon bağlı, şu an arama yok.", 1: "Telefon bağlı ve çalıyor.", 2: "Telefon bağlı, bir görüşme var."}
    return txt.get(st, "Telefon bağlı ama arama durumunu okuyamadım.")


# ------------------------------------------------------------------ rehberi telefondan alma
ROW = re.compile(r"display_name=(?P<n>.*?), data1=(?P<p>[^,]*)$")


def parse_contacts_output(out: str) -> dict[str, str]:
    book: dict[str, str] = {}
    for line in out.splitlines():
        m = ROW.search(line.strip())
        if not m:
            continue
        name, num = m.group("n").strip(), clean_number(m.group("p"))
        if name and num and name != "NULL":
            book.setdefault(name, num)
    return book


def sync_contacts() -> str:
    serial, err = pick_device()
    if not serial:
        return err
    code, out = _sh(serial, "content", "query", "--uri", "content://com.android.contacts/data/phones",
                    "--projection", "display_name:data1", timeout=30)
    book = parse_contacts_output(out) if code == 0 else {}
    if not book:
        why = "izin verilmedi" if re.search(r"permission|securityexception|denied", out, re.I) else "okunamadı"
        return (f"Telefonun rehberi {why}. Elle ekleyebilirsin: “rehbere ekle: Annem 0555 123 45 67”.")
    mine = contacts()
    added = 0
    for n, num in book.items():
        if not any(_fold(k) == _fold(n) for k in mine):
            mine[n] = num
            added += 1
    _store.save(CONTACTS_FILE, mine)
    return f"Telefondan {len(book)} kişi okudum, {added} yenisini rehbere ekledim. Rehber yalnızca bu bilgisayarda kalır."


SKILLS = [
    {"name": "phone_call", "description": "Telefondan bir kişiyi ya da numarayı arar (onay ister).", "hidden": True,
     "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}, "run": phone_call},
    {"name": "phone_hangup", "description": "Açık aramayı kapatır.", "hidden": True, "run": phone_hangup},
    {"name": "phone_answer", "description": "Çalan aramayı açar.", "hidden": True, "run": phone_answer},
    {"name": "phone_status", "description": "Telefon bağlı mı, arama var mı.", "hidden": True, "run": phone_status},
    {"name": "contact_add", "description": "Yerel rehbere kişi ekler.", "hidden": True,
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "number": {"type": "string"}}, "required": ["name", "number"]},
     "run": add_contact},
    {"name": "contacts_sync", "description": "Telefonun rehberini yerel rehbere alır.", "hidden": True, "run": sync_contacts},
]
