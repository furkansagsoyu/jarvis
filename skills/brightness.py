"""Ekran parlaklığı. Sırayla denenen yollar:
1) brightnessctl  2) Cinnamon güç servisi (D-Bus, yetki gerekmez)  3) /sys/class/backlight (yazma izni varsa)
Ekranın tamamen kararmaması için alt sınır yüzde 5.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

BACKLIGHT = Path("/sys/class/backlight")
MIN_PERCENT = 5
CINNAMON = [
    "gdbus", "call", "--session",
    "--dest", "org.cinnamon.SettingsDaemon.Power",
    "--object-path", "/org/cinnamon/SettingsDaemon/Power",
    "--method",
]
CIN_GET = "org.cinnamon.SettingsDaemon.Power.Screen.GetPercentage"
CIN_SET = "org.cinnamon.SettingsDaemon.Power.Screen.SetPercentage"


def _run(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} hata verdi: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def _sysfs_dir() -> Path | None:
    if BACKLIGHT.is_dir():
        for d in sorted(BACKLIGHT.iterdir()):
            if (d / "brightness").exists() and (d / "max_brightness").exists():
                return d
    return None


def _backend() -> str:
    if shutil.which("brightnessctl"):
        return "brightnessctl"
    if shutil.which("gdbus"):
        try:
            _run(CINNAMON + [CIN_GET])
            return "cinnamon"
        except Exception:  # noqa: BLE001
            pass
    d = _sysfs_dir()
    if d and os.access(d / "brightness", os.W_OK):
        return "sysfs"
    raise RuntimeError(
        "Parlaklığı değiştirecek bir yol bulunamadı. 'sudo apt install brightnessctl' ile kurabilirsin."
    )


def _read_sysfs() -> int | None:
    """Gerçek donanım değeri. Okumak için yetki gerekmez; Cinnamon'un GetPercentage'ı eski değer dönüyordu."""
    d = _sysfs_dir()
    if not d:
        return None
    try:
        cur, mx = int((d / "brightness").read_text()), int((d / "max_brightness").read_text())
    except (OSError, ValueError):
        return None
    return round(100 * cur / mx) if mx else None


def get_level() -> int:
    level = _read_sysfs()
    if level is not None:
        return level
    b = _backend()
    if b == "brightnessctl":
        m = re.search(r"(\d+)%", _run(["brightnessctl", "-m"]))
    elif b == "cinnamon":
        m = re.search(r"(\d+)", _run(CINNAMON + [CIN_GET]))
    else:
        d = _sysfs_dir()
        cur, mx = int((d / "brightness").read_text()), int((d / "max_brightness").read_text())
        return round(100 * cur / mx)
    if not m:
        raise RuntimeError("Parlaklık okunamadı")
    return int(m.group(1))


def set_level(percent: int) -> int:
    percent = max(MIN_PERCENT, min(100, int(percent)))
    b = _backend()
    if b == "brightnessctl":
        _run(["brightnessctl", "set", f"{percent}%"])
    elif b == "cinnamon":
        _run(CINNAMON + [CIN_SET, str(percent)])
    else:
        d = _sysfs_dir()
        mx = int((d / "max_brightness").read_text())
        (d / "brightness").write_text(str(round(mx * percent / 100)))
    return percent


def _to_int(value, name: str) -> int:
    try:
        return int(float(str(value).strip().rstrip("%")))
    except ValueError:
        raise ValueError(f"{name} bir sayı olmalı, gelen: {value!r}") from None


def set_brightness(percent) -> str:
    level = set_level(_to_int(percent, "percent"))
    return f"Parlaklık yüzde {level} yapıldı."


def change_brightness(delta_percent) -> str:
    delta = _to_int(delta_percent, "delta_percent")
    before = get_level()
    if delta >= 100:
        after = set_level(100)
    elif delta <= -100:
        after = set_level(MIN_PERCENT)
    else:
        after = set_level(before + max(-50, min(50, delta)))
    return f"Parlaklık yüzde {before} iken yüzde {after} yapıldı."


SKILLS = [
    {
        "name": "set_brightness",
        "description": "Ekran parlaklığını belirli bir yüzdeye ayarlar. Kullanıcı parlaklık için yüzde verdiğinde kullan.",
        "parameters": {
            "type": "object",
            "properties": {"percent": {"type": "integer", "description": "5 ile 100 arası hedef parlaklık"}},
            "required": ["percent"],
        },
        "run": set_brightness,
    },
    {
        "name": "change_brightness",
        "description": (
            "Ekran parlaklığını mevcut seviyesine göre artırır veya azaltır. "
            "Kullanıcı yüzde vermeden parlaklığı artır, azalt, ekranı karart veya aç derse bunu kullan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "delta_percent": {
                    "type": "integer",
                    "description": "Değişim miktarı. Negatif karartır, pozitif parlatır. 'Biraz' için 10 kullan.",
                }
            },
            "required": ["delta_percent"],
        },
        "run": change_brightness,
    },
]
