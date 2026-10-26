"""Zamanlanmış görevler testleri: ayrıştırma, zamanı gelme kuralı, zamanlayıcı (yeniden deneme), kurmanın onaylı olması,
kısıtlı kipte çalışma (uzaktan kapalı araçlar çalışmaz), pano listesi/silme."""
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri

import datetime as dt  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402

os.environ["JARVIS_DATA"] = tempfile.mkdtemp()
try:
    import ollama  # noqa: F401
except ImportError:
    sys.modules["ollama"] = types.ModuleType("ollama")
from core import scheduler as S  # noqa: E402
from skills import _confirm as confirm  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


# ---------------------------------------------------------------- ayrıştırma
P = S.parse
check("her gün / saat / iki nokta", P("her gün 9'da: hava nasıl") == {"days": S.EVERY, "hh": 9, "mm": 0, "cmd": "hava nasıl"}
      and P("her gün saat 9'da hava nasıl")["cmd"] == "hava nasıl")
check("hafta içi 8:30, hafta sonu, belirli gün", P("hafta içi her gün 8:30'da günün özeti")["days"] == [0, 1, 2, 3, 4]
      and P("hafta içi her gün 8:30'da günün özeti")["mm"] == 30 and P("hafta sonu 10'da hava")["days"] == [5, 6] and P("her cuma 17'de görevlerim")["days"] == [4])
check("akşam/gece/öğlen saatleri 24 saate çevrilir", P("her akşam 7'de pil kaç")["hh"] == 19 and P("her gece 11'de saat kaç")["hh"] == 23
      and P("her öğlen 1'de hava")["hh"] == 13 and P("her sabah 7'de hava")["hh"] == 7)
check("geçersiz saat ve boş komut reddedilir", P("her gün 25'te hava") == "Saat geçersiz." and "söylemedin" in P("her gün 9'da: ab"))
check("onay gerektiren ajan/ekip/kod/MCP ve iç içe zamanlama reddedilir",
      all("zamanlayamam" in P(t) for t in ("her gün 9'da araştır: haberler", "her gün 9'da ajan modu: x yap", "her gün 9'da kod: hesap makinesi",
                                          "her gün 9'da mcp: zaman get_current_time", "her gün 9'da her gün 10'da hava")))
check("'kodlarımı göster' gibi masum cümle reddedilmez", isinstance(P("her gün 9'da kodlarımı göster"), dict))
check("anlaşılmayan zamanlama açıklama verir", "anlayamadım" in P("yarın 9'da hava"))
check("açıklama", S.describe(P("hafta içi her gün 8:30'da günün özeti")) == "hafta içi her gün 08:30: günün özeti"
      and S.describe(P("her cuma 17'de görevlerim")) == "her cuma 17:00: görevlerim")

# ---------------------------------------------------------------- zamanı gelme
job = {"id": 1, "days": [0], "hh": 9, "mm": 0, "cmd": "x", "last": ""}
mon = dt.datetime(2026, 10, 26, 9, 0, 30)          # pazartesi
check("doğru gün ve saatte zamanı gelir", S.due(job, mon))
check("saatinden önce / yanlış günde gelmez", not S.due(job, mon.replace(hour=8, minute=59)) and not S.due(job, mon + dt.timedelta(days=1)))
check("10 dk içinde geç kalan çalışır, daha geç kalan (bilgisayar kapalıydı) çalışmaz",
      S.due(job, mon.replace(minute=9)) and not S.due(job, mon.replace(minute=11)))
check("bugün çalıştıysa tekrar gelmez", not S.due({**job, "last": "2026-10-26"}, mon))

# ---------------------------------------------------------------- zamanlayıcı
S.save([{"id": 1, "days": S.EVERY, "hh": 9, "mm": 0, "cmd": "saat kaç", "last": ""}])
ran = []
res = {"v": False}
sch = S.Scheduler(lambda j: ran.append(j["id"]) or res["v"], clock=lambda: dt.datetime(2026, 10, 26, 9, 1))
check("çalıştırıcı False dönerse (onay bekliyor/meşgul) işaretlenmez, sonra yeniden denenir", sch.tick() == [] and S.load()[0]["last"] == "")
res["v"] = True
check("başarılı çalışma işaretlenir, aynı gün ikinci kez çalışmaz", sch.tick() == [1] and S.load()[0]["last"] == "2026-10-26" and sch.tick() == [] and ran == [1, 1])
S.save([{"id": 2, "days": S.EVERY, "hh": 9, "mm": 0, "cmd": "x", "last": ""}])
boom = S.Scheduler(lambda j: 1 / 0, clock=lambda: dt.datetime(2026, 10, 26, 9, 1))
check("çalıştırıcı hata verirse zamanlayıcı ölmez, görev o gün tekrar denenmez", boom.tick() == [2])
S.save([])

# ---------------------------------------------------------------- Brain: kurma onaylı, liste, silme, model/uzaktan kuramaz
from core import brain as B  # noqa: E402

B.ollama.chat = lambda **kw: {"message": {"content": "?"}}
b = B.Brain(tools=None)
confirm.cancel()
q = " ".join(b.reply_stream("her gün 9'da hava nasıl"))
check("kurma onay ister; onaydan önce kaydedilmez", q.endswith("Onaylıyor musun?") and "her gün 09:00: hava nasıl" in q and S.load() == [], q)
out = " ".join(b.reply_stream("evet"))
check("evet ile kurulur", "1 numaralı görev" in out and len(S.load()) == 1, out)
" ".join(b.reply_stream("hafta içi her gün 8:30'da günün özeti"))
" ".join(b.reply_stream("evet"))
out = " ".join(b.reply_stream("zamanlanmış görevler"))
check("liste", "1: her gün 09:00: hava nasıl." in out and "2: hafta içi her gün 08:30: günün özeti." in out, out)
out = " ".join(b.reply_stream("zamanlanmış görevi sil 1"))
check("numarayla silme", "1 numaralı zamanlanmış görevi sildim" in out and [j["id"] for j in S.load()] == [2], out)
check("araçlar modelin şemasında yok (gizli) ve uzaktan kapalı",
      {"schedule_add", "schedule_list", "schedule_delete"} <= B.HIDDEN and {"schedule_add", "schedule_list", "schedule_delete"} <= B.REMOTE_BLOCKED)
b.remote = True
out = " ".join(b.reply_stream("her gün 10'da saat kaç"))
check("uzaktan (Telegram/telefon) görev kurulamaz", "uzaktan yapmıyorum" in out and len(S.load()) == 1 and not confirm.has_pending(), out)
b.remote = False

# ---------------------------------------------------------------- çalıştırma: kısıtlı kip
import main  # noqa: E402
from desktop import ui_state  # noqa: E402

said = []
ok = main.run_scheduled(b, said.append, {"id": 9, "cmd": "saat kaç"})
check("zamanı gelen görev çalışır, sonucu 'Zamanlanmış görev' diye bildirilir, konuşma kaydına etiketli düşer",
      ok and said and said[-1].startswith("Zamanlanmış görev.") and any(t["text"] == "[Zamanlanmış] saat kaç" for t in ui_state.read_status()["turns"]), str(said))
ok = main.run_scheduled(b, said.append, {"id": 9, "cmd": "rapor.txt dosyasını oku"})
check("kısıtlı kip: dosya okuma gibi uzaktan kapalı araç gözetimsiz çalışmaz", ok and "uzaktan yapmıyorum" in said[-1], said[-1])
check("çalıştıktan sonra beyin normal (yerel) kipe döner", b.remote is False)
confirm.request("deneme işlemi.", lambda: "ok")
n = len(said)
check("bilgisayarda onay bekliyorsa görev ertelenir (False), hiçbir şey söylenmez", main.run_scheduled(b, said.append, {"id": 9, "cmd": "saat kaç"}) is False and len(said) == n)
confirm.cancel()

# ---------------------------------------------------------------- pano
from dashboard import server, state  # noqa: E402

rows = state._zamanlanmis(types.SimpleNamespace(brain=b))
check("pano listesi", rows and rows[0]["text"] == "hafta içi her gün 08:30: günün özeti")
d = server.Dashboard(types.SimpleNamespace(brain=b), lambda t, silent=False: None, port=8999)
r = d.agenda_op({"op": "schedule_delete", "id": 2})
check("panodan silme (yerel)", r["ok"] and S.load() == [])
import connect.remote as remote  # noqa: E402

check("telefon sayfası zamanlanmış görev silemez", "schedule_delete" not in remote.REMOTE_AGENDA_OPS)

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
