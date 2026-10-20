"""Hava durumu (Open-Meteo: ücretsiz, anahtarsız)."""
import json
import os
import urllib.parse
import urllib.request

DEFAULT_CITY = os.environ.get("JARVIS_CITY", "Tokat")  # şehir söylenmezse; başka şehir için JARVIS_CITY ayarla

CODES = {
    0: "açık", 1: "çoğunlukla açık", 2: "parçalı bulutlu", 3: "kapalı", 45: "sisli", 48: "sisli",
    51: "hafif çiseleme", 53: "çiseleme", 55: "yoğun çiseleme", 61: "hafif yağmurlu", 63: "yağmurlu",
    65: "şiddetli yağmurlu", 71: "hafif karlı", 73: "karlı", 75: "yoğun karlı", 80: "sağanak yağışlı",
    81: "sağanak yağışlı", 82: "şiddetli sağanak", 95: "gök gürültülü fırtınalı", 96: "dolulu fırtınalı", 99: "dolulu fırtınalı",
}


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


def get_weather(city: str = "", day: str = "bugün") -> str:
    city = (city or DEFAULT_CITY).strip()
    try:
        geo = _get("https://geocoding-api.open-meteo.com/v1/search?" +
                   urllib.parse.urlencode({"name": city, "count": 1, "language": "tr"}))
        if not geo.get("results"):
            return f"{city} adında bir yer bulamadım."
        place = geo["results"][0]
        data = _get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"}))
    except Exception:  # noqa: BLE001  (ağ yok, zaman aşımı, bozuk cevap)
        return "Hata: hava durumuna ulaşamadım."
    name = place.get("name", city)
    d = data["daily"]
    if "yarın" in (day or "").lower():
        i, label = 1, "yarın"
    else:
        i, label = 0, "bugün"
    desc = CODES.get(d["weather_code"][i], "değişken")
    rain = d["precipitation_probability_max"][i] or 0
    day_part = (f"en düşük {round(d['temperature_2m_min'][i])}, en yüksek {round(d['temperature_2m_max'][i])} derece, "
                f"yağış ihtimali yüzde {rain}.")
    if i == 0:
        c = data["current"]
        return (f"{name} için şu an hava {CODES.get(c['weather_code'], 'değişken')}, {round(c['temperature_2m'])} derece, "
                f"hissedilen {round(c['apparent_temperature'])}. Gün boyu {day_part}")
    return f"{name} için {label} hava {desc}, {day_part}"


def current_temp(city: str = "") -> int | None:
    """Pano için yalnızca anlık sıcaklık (°C, tam sayı); ulaşılamazsa None."""
    city = (city or DEFAULT_CITY).strip()
    try:
        geo = _get("https://geocoding-api.open-meteo.com/v1/search?" +
                   urllib.parse.urlencode({"name": city, "count": 1, "language": "tr"}))
        place = geo["results"][0]
        data = _get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": place["latitude"], "longitude": place["longitude"], "current": "temperature_2m"}))
        return round(data["current"]["temperature_2m"])
    except Exception:  # noqa: BLE001
        return None


SKILLS = [
    {
        "name": "get_weather",
        "description": "Hava durumunu söyler. 'Hava nasıl', 'yarın yağmur var mı', 'İstanbul'da kaç derece' denince kullanılır.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "Şehir adı; söylenmediyse boş bırak"},
            "day": {"type": "string", "description": "'bugün' veya 'yarın'"}}},
        "run": get_weather,
    },
]
