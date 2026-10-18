"""Günün özeti: selam, tarih, hava, hatırlatıcılar, pil. Tek komutla ("günaydın", "günün özeti")."""
import datetime as dt

from . import _store, battery, clock, reminders, weather


def greeting(hour: int | None = None) -> str:
    h = dt.datetime.now().hour if hour is None else hour
    return "Günaydın" if 5 <= h < 12 else "İyi günler" if 12 <= h < 18 else "İyi akşamlar"


def morning_brief() -> str:
    parts = [f"{greeting()}.", clock.get_date()]
    w = weather.get_weather()
    if not w.startswith("Hata"):  # internet yoksa hava kısmı sessizce atlanır
        parts.append(w)
    r = reminders.list_reminders()
    if "yok" not in r:
        parts.append(r)
    b = battery.read_battery()
    if b and b[0] <= 30 and b[1] == "Discharging":
        parts.append(f"Pil yüzde {b[0]}, şarja takmayı unutma.")
    return " ".join(parts)


def due_today(now: dt.datetime | None = None) -> bool:
    """Sabah 05-12 arası ve bugün henüz özet verilmediyse True (otomatik başlatmada bir kez konuşmak için)."""
    now = now or dt.datetime.now()
    return 5 <= now.hour < 12 and _store.load("briefing.json", {}).get("last") != now.date().isoformat()


def mark_done(now: dt.datetime | None = None) -> None:
    _store.save("briefing.json", {"last": (now or dt.datetime.now()).date().isoformat()})


SKILLS = [
    {
        "name": "morning_brief",
        "description": "Günün özetini verir: tarih, hava, hatırlatıcılar. 'Günaydın', 'günün özeti', 'bugün neler var' denince kullanılır.",
        "hidden": True,
        "run": morning_brief,
    },
]
