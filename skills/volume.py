"""Sistem ses seviyesi (PulseAudio/PipeWire: pactl, yoksa wpctl, yoksa amixer)."""
import re
import shutil
import subprocess


def _run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} hata verdi: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def _backend() -> str:
    for name in ("pactl", "wpctl", "amixer"):
        if shutil.which(name):
            return name
    raise RuntimeError("Ses denetimi için pactl, wpctl veya amixer bulunamadı")


def get_level() -> int:
    b = _backend()
    if b == "pactl":
        m = re.search(r"(\d+)%", _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]))
    elif b == "wpctl":
        m = re.search(r"([\d.]+)", _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]))
        if m:
            return round(float(m.group(1)) * 100)
    else:
        m = re.search(r"\[(\d+)%\]", _run(["amixer", "sget", "Master"]))
    if not m:
        raise RuntimeError("Ses seviyesi okunamadı")
    return int(m.group(1))


def set_level(percent: int) -> int:
    percent = max(0, min(100, int(percent)))
    b = _backend()
    if b == "pactl":
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
    elif b == "wpctl":
        _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{percent / 100:.2f}"])
    else:
        _run(["amixer", "sset", "Master", f"{percent}%"])
    return percent


def _to_int(value, name: str) -> int:
    try:
        return int(float(str(value).strip().rstrip("%")))
    except ValueError:
        raise ValueError(f"{name} bir sayı olmalı, gelen: {value!r}") from None


def set_volume(percent) -> str:
    level = set_level(_to_int(percent, "percent"))
    return f"Ses seviyesi yüzde {level} yapıldı."


def change_volume(delta_percent) -> str:
    delta = max(-50, min(50, _to_int(delta_percent, "delta_percent")))  # tek seferde en fazla 50 puan
    before = get_level()
    after = set_level(before + delta)
    return f"Ses seviyesi yüzde {before} iken yüzde {after} yapıldı."


def get_volume() -> str:
    return f"Ses seviyesi şu an yüzde {get_level()}."


SKILLS = [
    {
        "name": "set_volume",
        "description": "Sesi belirli bir yüzdeye ayarlar. Kullanıcı yüzde verdiğinde kullan, örneğin 'sesi yüzde otuz yap'.",
        "parameters": {
            "type": "object",
            "properties": {"percent": {"type": "integer", "description": "0 ile 100 arası hedef ses seviyesi"}},
            "required": ["percent"],
        },
        "run": set_volume,
    },
    {
        "name": "change_volume",
        "description": (
            "Sesi mevcut seviyesine göre artırır veya azaltır. "
            "Kullanıcı yüzde vermeden 'biraz kıs' veya 'biraz aç' derse bunu kullan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "delta_percent": {
                    "type": "integer",
                    "description": "Değişim miktarı. Negatif kısar, pozitif açar. 'Biraz' için 10 kullan.",
                }
            },
            "required": ["delta_percent"],
        },
        "run": change_volume,
    },
    {
        "name": "get_volume",
        "description": "Şu anki ses seviyesini söyler. Kullanıcı ses seviyesini sorarsa MUTLAKA bu aracı çağır.",
        "run": get_volume,
    },
]
