"""Bellek koruması. 15 GB RAM, swap yok: bellek biterse çekirdeğin OOM-killer'ı rastgele bir süreci (çoğu zaman Ollama'yı ya da
masaüstünü) öldürür ve bilgisayar dakikalarca donabilir. Bu modül:

  * kullanılabilir belleği (MemAvailable) ve baskıyı (PSI) okur: düzey ok / low / critical
  * ağır bir işe (tarayıcı, kod çalıştırma) başlamadan önce yeterli bellek var mı bakar (need)
  * Monitor: bellek azalınca bir kez, en çok kullananları sayarak uyarır (spam yok: histerezis + bekleme süresi)

Eşikler ortam değişkeniyle ayarlanır: JARVIS_MEM_LOW (GB, varsayılan 1.5), JARVIS_MEM_CRIT (GB, varsayılan 0.8).
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

LOW_GB = float(os.environ.get("JARVIS_MEM_LOW", "1.5"))
CRIT_GB = float(os.environ.get("JARVIS_MEM_CRIT", "0.8"))
PSI_LOW = 15.0    # son 10 sn'nin yüzde kaçında en az bir süreç bellek yüzünden bekledi
PSI_CRIT = 40.0
GB = 1048576.0    # kB -> GB


def read_meminfo(text: str | None = None) -> dict:
    """GB cinsinden: total, available, swap_total, swap_free."""
    text = text if text is not None else Path("/proc/meminfo").read_text()
    kb = {}
    for ln in text.splitlines():
        parts = ln.replace(":", " ").split()
        if len(parts) >= 2 and parts[1].isdigit():
            kb[parts[0]] = int(parts[1])
    return {"total": kb.get("MemTotal", 0) / GB, "available": kb.get("MemAvailable", 0) / GB,
            "swap_total": kb.get("SwapTotal", 0) / GB, "swap_free": kb.get("SwapFree", 0) / GB}


def read_psi(text: str | None = None) -> float | None:
    """/proc/pressure/memory 'some avg10' (yüzde). Çekirdek PSI vermiyorsa None."""
    try:
        text = text if text is not None else Path("/proc/pressure/memory").read_text()
    except OSError:
        return None
    for ln in text.splitlines():
        if ln.startswith("some"):
            for tok in ln.split():
                if tok.startswith("avg10="):
                    try:
                        return float(tok[6:])
                    except ValueError:
                        return None
    return None


def level(mi: dict, psi: float | None = None, low: float | None = None, crit: float | None = None) -> str:
    low = LOW_GB if low is None else low
    crit = CRIT_GB if crit is None else crit
    avail = mi["available"]
    if avail < crit or (psi is not None and psi >= PSI_CRIT):
        return "critical"
    if avail < low or (psi is not None and psi >= PSI_LOW):
        return "low"
    return "ok"


def top_consumers(n: int = 3, proc: Path = Path("/proc")) -> list[tuple[str, float]]:
    """En çok RSS kullanan programlar (aynı adlılar toplanır): [(ad, GB)]."""
    groups: dict[str, float] = {}
    try:
        entries = list(proc.iterdir())
    except OSError:
        return []
    for d in entries:
        if not d.name.isdigit():
            continue
        try:
            txt = (d / "status").read_text()
        except OSError:
            continue
        name, rss = "", 0
        for ln in txt.splitlines():
            if ln.startswith("Name:"):
                name = ln.split(None, 1)[1].strip()
            elif ln.startswith("VmRSS:"):
                parts = ln.split()
                rss = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        if name and rss:
            groups[name] = groups.get(name, 0.0) + rss / GB
    return sorted(groups.items(), key=lambda kv: -kv[1])[:n]


def snapshot() -> dict:
    mi = read_meminfo()
    psi = read_psi()
    return {**mi, "psi": psi, "level": level(mi, psi)}


def _fmt(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def need(what: str, gb: float, mi: dict | None = None) -> str:
    """Boş döner = yeterli. Değilse kullanıcıya söylenecek cümle (iş BAŞLATILMAZ). Okunamazsa engellemez."""
    try:
        mi = mi or read_meminfo()
    except OSError:
        return ""
    if mi["available"] >= gb + CRIT_GB:
        return ""
    return (f"Bellek yetersiz: {what} için en az {_fmt(gb)} gigabayt gerekir, şu an {_fmt(mi['available'])} gigabayt boş. "
            "Önce başka bir işi kapat ya da bellek kullanımını sor.")


class Monitor:
    """Bellek azalınca bir kez uyarır; düzey kötüleşirse (low -> critical) yeniden uyarır; düzeldikten sonra sıfırlanır."""

    def __init__(self, say, interval: float = 15.0, cooldown: float = 600.0, clock=time.monotonic, sample=snapshot, top=top_consumers):
        self.say, self.interval, self.cooldown, self.clock, self.sample, self.top = say, interval, cooldown, clock, sample, top
        self._level = "ok"
        self._last = -1e9
        self._stop = threading.Event()

    def check(self) -> str:
        s = self.sample()
        lv = s["level"]
        if lv == "ok":
            # histerezis: eşiğin %50 üstüne çıkmadan "düzeldi" sayılmaz (gidip gelen değer sürekli uyarmasın)
            if s["available"] >= LOW_GB * 1.5:
                self._level = "ok"
            return ""
        escalated = self._level == "ok" or (lv == "critical" and self._level != "critical")
        if not escalated:
            return ""  # bu düzey için zaten uyarıldı; düzelmeden tekrar söylenmez
        if lv != "critical" and self.clock() - self._last < self.cooldown:
            return ""  # gidip gelen değer (titreşim) kısa sürede yeniden uyarmasın
        self._level = lv
        self._last = self.clock()
        who = ", ".join(f"{n} {_fmt(g)}" for n, g in self.top(3))
        head = "Bellek kritik seviyede" if lv == "critical" else "Bellek azaldı"
        msg = f"{head}: {_fmt(s['available'])} gigabayt boş." + (f" En çok kullananlar: {who}." if who else "")
        if lv == "critical":
            msg += " Büyük işleri başlatmayacağım; takılma olursa bir uygulamayı kapat."
        self.say(msg)
        return msg

    def start(self) -> None:
        def loop():
            while not self._stop.wait(self.interval):
                try:
                    self.check()
                except Exception:  # noqa: BLE001  (izleyici hiçbir zaman programı düşürmesin)
                    pass
        threading.Thread(target=loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
