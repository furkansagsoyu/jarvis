"""Hafıza (SQLite FTS5) testleri: Türkçe arama, sıralama, tekrar, unutma, memory.json göçü (yedek kalır), izinler,
FTS5 yokken LIKE yedeği, sorgu güvenliği, uzaktan kapalı."""
import json
import os
import stat
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
try:
    import ollama  # noqa: F401
except ImportError:
    sys.modules["ollama"] = types.ModuleType("ollama")
from skills import _store  # noqa: E402
from skills import memory as M  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


def fresh_dir() -> Path:
    d = Path(tempfile.mkdtemp())
    _store.DATA_DIR, _store._secured = d, False
    return d


for fts in (True, False):
    tag = "FTS5" if fts else "LIKE yedeği"
    d = fresh_dir()
    M._fts = None if fts else False
    check(f"[{tag}] boş hafıza", M.recall("") == "Henüz kayıtlı bir bilgi yok.")
    for f in ("Kullanıcının adı Furkan", "Kedimin adı Pamuk", "İstanbul'da doğdum", "En sevdiğim çiçek lale", "Bitirme projem Jarvis asistanı"):
        M.remember(f)
    check(f"[{tag}] Türkçe ek: 'kedimin adı neydi' -> Pamuk", "Pamuk" in M.recall("kedimin adı neydi"))
    check(f"[{tag}] İ/i ve ç/c katlanır", "İstanbul" in M.recall("istanbul") and "lale" in M.recall("cicek"))
    check(f"[{tag}] eşleşme yoksa açık cevap", M.recall("uçak bileti") == "Bununla ilgili kayıtlı bir bilgi bulamadım.")
    check(f"[{tag}] aynı bilgi (büyük/küçük harf farkıyla) iki kez kaydedilmez", M.remember("kullanıcının adı furkan") == "Bunu zaten biliyorum.")
    check(f"[{tag}] boş sorgu: son 5 kayıt, eskiden yeniye", M.recall("").startswith("Kullanıcının adı Furkan.") and M.recall("").endswith("Jarvis asistanı."))
    check(f"[{tag}] sorgu enjeksiyonu çökertmez", isinstance(M.recall('"; DROP TABLE facts; -- adı*'), str) and "Pamuk" in M.recall("kedi"))
    check(f"[{tag}] unutma: eşleşenler silinir", M.forget("kedim") == "1 kaydı sildim." and "Pamuk" not in M.recall("") and M.forget("kedim") == "Eşleşen bir kayıt bulamadım.")
    check(f"[{tag}] pano istatistiği", M.stats()["count"] == 4 and M.stats()["last"][0] == "Bitirme projem Jarvis asistanı")
    mode = stat.S_IMODE(os.stat(d / M.DB).st_mode)
    check(f"[{tag}] memory.db yalnızca sahibine açık (0600)", mode == 0o600, oct(mode))

# sıralama: daha çok terim tutan önce (bm25)
fresh_dir()
M._fts = None
for f in ("Annemin doğum günü 3 Mart", "Babamın doğum günü 12 Eylül", "Annemin telefonu yeni", "Doğum günü pastası çikolatalı olsun"):
    M.remember(f)
check("bm25: 'annemin doğum günü' en alakalı kayıt önce", M.recall("annemin doğum günü").startswith("Annemin doğum günü 3 Mart."), M.recall("annemin doğum günü"))
check("en fazla 5 sonuç", M.recall("doğum annem babam pasta telefon").count(".") <= M.MAX_RECALL + 3)

# üst sınır: en eskiler düşer
fresh_dir()
old_max, M.MAX_FACTS = M.MAX_FACTS, 3
for i in range(5):
    M.remember(f"not numara {i}")
check("üst sınır aşılınca en eskiler düşer", M.stats(10) == {"count": 3, "last": ["not numara 4", "not numara 3", "not numara 2"]})
M.MAX_FACTS = old_max

# geri uyumlu göç
d = fresh_dir()
M._fts = None
legacy = [{"text": "Kullanıcının adı Furkan", "date": "2026-01-02"}, {"text": "Tokat'ta yaşıyor", "date": "2026-02-03"},
          {"text": "kullanıcının adı furkan", "date": "2026-03-04"}, {"bozuk": 1}, "metin"]
(d / "memory.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
out = M.recall("tokat")
check("göç: eski memory.json kayıtları aranabilir", "Tokat'ta yaşıyor" in out, out)
check("göç: kaynak silinmez, memory.json.bak olarak kalır (içerik aynen)", not (d / "memory.json").exists()
      and json.loads((d / "memory.json.bak").read_text(encoding="utf-8")) == legacy)
check("göç: tekrar eden ve bozuk kayıtlar atlanır, tarih korunur", M.stats(10)["count"] == 2
      and __import__("sqlite3").connect(d / M.DB).execute("SELECT date FROM facts WHERE text LIKE 'Tokat%'").fetchone()[0] == "2026-02-03")
M.recall("")
check("göç bir kez yapılır (yinelenmez)", M.stats(10)["count"] == 2)

# gizlilik: uzaktan kapalı, model şeması değişmedi
import brain as B  # noqa: E402

check("recall uzaktan (Telegram/telefon) kapalı", "recall" in B.REMOTE_BLOCKED)
check("araç adları/parametreleri değişmedi (model uyumu)", [s["name"] for s in M.SKILLS] == ["remember", "recall", "forget"]
      and list(M.SKILLS[1]["parameters"]["properties"]) == ["query"])

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
