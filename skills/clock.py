"""Saat ve tarih."""
import datetime as dt

GUNLER = ["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"]
AYLAR = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"]


def get_time() -> str:
    now = dt.datetime.now()
    return f"Şu an saat {now.hour:02d}:{now.minute:02d}."


def get_date() -> str:
    now = dt.datetime.now()
    return f"Bugün {now.day} {AYLAR[now.month - 1]} {now.year}, {GUNLER[now.weekday()]}."


SKILLS = [
    {
        "name": "get_time",
        "description": (
            "Şu anki saati söyler. "
            "Kullanıcı saati sorarsa MUTLAKA bu aracı çağır, saati kendin tahmin etme."
        ),
        "run": get_time,
    },
    {
        "name": "get_date",
        "description": (
            "Bugünün tarihini ve gününü söyler. "
            "Kullanıcı tarihi veya günü sorarsa MUTLAKA bu aracı çağır, kendin tahmin etme."
        ),
        "run": get_date,
    },
]
