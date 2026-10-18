"""Donanım durumu: CPU, RAM, GPU (kullanım, bellek, sıcaklık), disk. Ek kütüphane gerekmez (/proc, /sys, nvidia-smi)."""
import shutil
import subprocess
import time
from pathlib import Path


def _cpu_times() -> tuple[int, int]:
    """(toplam, boşta) CPU jiffy; /proc/stat ilk satırı."""
    vals = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:8]]
    return sum(vals), vals[3] + vals[4]  # idle + iowait


def cpu_percent(interval: float = 0.4) -> float:
    t1, i1 = _cpu_times()
    time.sleep(interval)
    t2, i2 = _cpu_times()
    return 100.0 * (1 - (i2 - i1) / max(1, t2 - t1))


def parse_meminfo(text: str) -> tuple[float, float]:
    """(kullanılan GB, toplam GB). Kullanılan = toplam - MemAvailable."""
    kb = {ln.split(":")[0]: int(ln.split()[1]) for ln in text.splitlines() if ":" in ln and len(ln.split()) > 1}
    total = kb["MemTotal"]
    return (total - kb["MemAvailable"]) / 1048576, total / 1048576


def cpu_temp() -> float | None:
    """En sıcak CPU sensörü (°C). x86_pkg_temp / coretemp / k10temp öncelikli, yoksa en yüksek thermal_zone."""
    best, pref = None, None
    for z in Path("/sys/class/thermal").glob("thermal_zone*"):
        try:
            t = int((z / "temp").read_text()) / 1000
            kind = (z / "type").read_text().strip().lower()
        except (OSError, ValueError):
            continue
        if any(k in kind for k in ("x86_pkg", "coretemp", "k10temp", "cpu")):
            pref = max(pref or 0, t)
        best = max(best or 0, t)
    return pref if pref is not None else best


def gpu_info() -> dict | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
        name, util, used, total, temp = (x.strip() for x in out.split(","))
        return {"name": name, "util": int(util), "used": int(used), "total": int(total), "temp": int(temp)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def get_system_status(part: str = "") -> str:
    """part: 'cpu' | 'ram' | 'gpu' | 'disk' | '' (hepsi). Kısa, sesli okunacak cümleler döner."""
    part = (part or "").lower()
    want = lambda *keys: not part or any(k in part for k in keys)  # noqa: E731
    out = []
    if want("cpu", "işlemci"):
        txt = f"İşlemci yüzde {cpu_percent():.0f} dolu"
        t = cpu_temp()
        out.append(txt + (f", sıcaklığı {t:.0f} derece." if t else "."))
    if want("ram", "bellek"):
        used, total = parse_meminfo(Path("/proc/meminfo").read_text())
        out.append(f"Bellek {total:.0f} gigabaytın {used:.1f} gigabaytı dolu.".replace(".", ","))
    if want("gpu", "ekran kartı", "vram"):
        g = gpu_info()
        if g:
            out.append(f"Ekran kartında yüzde {g['util']} yük var, video belleğinin {g['used'] / 1024:.1f} gigabaytı "
                       f"({g['total'] / 1024:.0f} içinden) dolu, sıcaklık {g['temp']} derece.".replace(".", ","))
        elif part:
            out.append("Ekran kartı bilgisine ulaşamadım.")
    if want("disk", "depolama"):
        d = shutil.disk_usage(Path.home())
        out.append(f"Diskte {d.free / 1e9:.0f} gigabayt boş yer var.")
    return " ".join(out) or "Donanım bilgisi alamadım."


SKILLS = [
    {
        "name": "get_system_status",
        "description": "Bilgisayarın işlemci, bellek, ekran kartı, sıcaklık ve disk durumunu söyler. 'CPU kaç', 'RAM ne kadar dolu', 'sistem durumu' denince kullanılır.",
        "parameters": {"type": "object", "properties": {
            "part": {"type": "string", "description": "cpu, ram, gpu veya disk; hepsi için boş"}}},
        "hidden": True,
        "run": get_system_status,
    },
]
