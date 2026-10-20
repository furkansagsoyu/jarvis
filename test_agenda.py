"""Takvim ve görevler testleri: Türkçe tarih ayrıştırma, depo, hızlı yol, uyarı, sabah özeti."""
import datetime as dt
import os
import sys
import tempfile
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
from skills import _confirm as confirm  # noqa: E402
from skills import agenda as a  # noqa: E402
from skills._trdate import parse_when  # noqa: E402


def check(name, cond):
    print(("OK   " if cond else "HATA ") + name)
    return bool(cond)


NOW = dt.datetime(2026, 10, 20, 10, 0)  # Salı

DATE_CASES = [  # metin, tarih, saat, süre(dk), kalan metin
    ("yarın saat 14'te toplantı", "2026-10-21", "14:00", None, "toplantı"),
    ("cuma akşam 8'de yemek", "2026-10-23", "20:00", None, "yemek"),
    ("haftaya salı saat 9.30 diş randevusu", "2026-10-27", "09:30", None, "diş randevusu"),
    ("15 Kasım'da sınav", "2026-11-15", None, None, "sınav"),
    ("25.12 saat 18:00 parti", "2026-12-25", "18:00", None, "parti"),
    ("bugün saat 3'te ders", "2026-10-20", "15:00", None, "ders"),
    ("2 saat sonra mola", "2026-10-20", "12:00", None, "mola"),
    ("yarın öğlen toplantı", "2026-10-21", "12:00", None, "toplantı"),
    ("cumartesi sabah 10'da ders 2 saatlik", "2026-10-24", "10:00", 120, "ders"),
    ("salı toplantı", "2026-10-27", None, None, "toplantı"),
    ("yarım saat sonra çay", "2026-10-20", "10:30", None, "çay"),
    ("öbür gün akşam 7'de sinema", "2026-10-22", "19:00", None, "sinema"),
    ("saat 3 buçukta kahve yarın", "2026-10-21", "15:30", None, "kahve"),
    ("1 Ocak yılbaşı", "2027-01-01", None, None, "yılbaşı"),
]


def run() -> bool:
    ok = True
    for text, d, t, dur, rest in DATE_CASES:
        w = parse_when(text, NOW)
        got = (str(w.date), w.time.strftime("%H:%M") if w.time else None, w.duration, w.rest)
        ok &= check(f"tarih: {text!r}", got == (d, t, dur, rest)) or print("     ", got) or False

    # --- hızlı yol
    ROUTES = [
        ("yarın saat 14'te toplantı ekle", "agenda_add"), ("takvime cuma akşam 8'de yemek koy", "agenda_add"),
        ("bu hafta takvimimde ne var", "agenda_list"), ("yarın ne var", "agenda_list"), ("toplantılarım neler", "agenda_list"),
        ("cumartesi ne yapıyorum", "agenda_list"), ("toplantı etkinliğini sil", "agenda_cancel"),
        ("görev ekle: raporu bitir, cuma, yüksek öncelik", "task_add"), ("yeni görev: matematik ödevi", "task_add"),
        ("matematik ödevini göreve ekle", "task_add"), ("görevlerim neler", "task_list"), ("geciken görevler", "task_list"),
        ("raporu bitir görevi bitti", "task_done"), ("raporu bitir görevini sil", "task_delete"),
        ("bir toplantı ekle", "agenda_add"),
        ("yarın saat 9'a hatırlatıcı ekle", None), ("ekranda ne var", None), ("dosya ekle", None), ("hava yarın nasıl", None),
        ("saat kaç", None), ("20 dakika sonra beni uyar", None),
    ]
    for text, want in ROUTES:
        r = a.route(text)
        ok &= check(f"rota: {text!r} -> {want}", (r[0][0] if r else None) == want)
    r = a.route("görev ekle: raporu bitir, cuma, yüksek öncelik")[0][1]
    ok &= check("görev: başlık/öncelik/tarih ayrıştı", r["title"] == "raporu bitir" and r["priority"] == "yüksek" and r["due"])

    # --- depo (saat sahte)
    clock = {"now": NOW}
    real_now = a._now
    a._now = lambda: clock["now"]
    try:
        out = a.add_event("toplantı", "2026-10-21", "14:00")
        ok &= check("etkinlik eklenir", "yarın saat 14.00 Toplantı takvime eklendi" in out)
        ok &= check("yakın saatte çakışma uyarısı", "Dikkat" in a.add_event("diş", "2026-10-21", "14:15"))
        ok &= check("geçmiş saat reddedilir", "geçmiş" in a.add_event("x", "2026-10-20", "09:00"))
        ok &= check("zamansız etkinlik yardım verir", "Örnek" in a.add_event("x"))
        a.add_event("sınav", "2026-10-23")
        out = a.list_events("tomorrow")
        ok &= check("yarını okur", "2 etkinlik" in out and "Toplantı" in out)
        ok &= check("hafta listesi gün adlarıyla", "Cuma" in a.list_events("week"))
        ok &= check("boş gün", "etkinlik yok" in a.list_events("2026-11-30"))

        out = a.cancel_event("toplantı")
        ok &= check("silme onay ister, silmez", confirm.has_pending() and "Toplantı" in out and "Toplantı" in a.list_events("tomorrow"))
        confirm.approve()
        ok &= check("onayla silinir", "Toplantı" not in a.list_events("tomorrow"))
        ok &= check("belirsiz silme listeler", "eşleşti" in a.cancel_event("") or "anlamadım" in a.cancel_event(""))

        # görevler
        ok &= check("görev eklenir", "Görev eklendi: Rapor yaz, bitiş yarın, öncelik yüksek" in a.add_task("rapor yaz", "2026-10-21", "yüksek"))
        a.add_task("ödev", "2026-10-19", "orta")
        a.add_task("market", "", "düşük")
        out = a.list_tasks("open")
        ok &= check("3 açık görev, geciken önce", "3 açık görev" in out and out.index("Ödev") < out.index("Rapor"))
        ok &= check("geciken filtre", "Ödev" in a.list_tasks("overdue") and "Market" not in a.list_tasks("overdue"))
        ok &= check("görev bitti (ek yutan eşleşme)", "Ödev görevi bitti" in a.done_task("ödevi"))
        ok &= check("bitenler listede yok", "Ödev" not in a.list_tasks("open"))
        ok &= check("yok olan görev", "bulamadım" in a.done_task("uçak"))
        a.add_task("rapor oku", "", "orta")
        ok &= check("belirsiz görev sorar", "eşleşti" in a.done_task("rapor"))
        out = a.delete_task("market")
        ok &= check("görev silme onay ister", confirm.has_pending())
        confirm.approve()
        ok &= check("görev silindi", "Market" not in a.list_tasks("open"))

        # sabah özeti ve sayaçlar
        clock["now"] = dt.datetime(2026, 10, 21, 8, 0)
        a.add_task("bugünkü iş", "2026-10-21", "orta")
        br = a.brief_text()
        ok &= check("sabah özeti: etkinlik yok ama görev ve gecikme", "bugün bitmesi gereken" in br.lower() and "Bugünkü iş" in br)
        c = a.counts()
        ok &= check("pano sayaçları", c["open_tasks"] >= 3 and "overdue" in c and "events_today" in c)

        # uyarı iş parçacığı
        said = []
        a.add_event("ders", "2026-10-21", "09:00")
        mon = a.Monitor(said.append)
        clock["now"] = dt.datetime(2026, 10, 21, 8, 40)
        ok &= check("10 dk'dan önce uyarmaz", mon.check(clock["now"]) == [])
        clock["now"] = dt.datetime(2026, 10, 21, 8, 52)
        got = mon.check(clock["now"])
        ok &= check("10 dk kala bir kez uyarır", len(got) == 1 and "8 dakika sonra Ders" in got[0] and said == got)
        ok &= check("ikinci kez uyarmaz", mon.check(clock["now"]) == [])
    finally:
        a._now = real_now
        confirm.cancel()
    return bool(ok)


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
