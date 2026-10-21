"""Pil durumu ve düşük pil uyarısı (Linux: /sys/class/power_supply)."""
import os
import threading
from pathlib import Path

SYS = Path(os.environ.get("JARVIS_POWER_DIR", "/sys/class/power_supply"))


def read_battery() -> tuple[int, str] | None:
    """(yüzde, durum) ya da pil yoksa None. Durum: Charging / Discharging / Full / Not charging ..."""
    for d in sorted(SYS.glob("BAT*")):
        try:
            pct = int((d / "capacity").read_text().strip())
            status = (d / "status").read_text().strip()
            return pct, status
        except (OSError, ValueError):
            continue
    return None


def _state_text(status: str) -> str:
    return {"Charging": "şarj oluyor", "Full": "şarj dolu", "Discharging": "şarja takılı değil",
            "Not charging": "şarja takılı, şarj olmuyor"}.get(status, "durumu belirsiz")


def get_battery() -> str:
    b = read_battery()
    if not b:
        return "Bu bilgisayarda pil bilgisi bulamadım."
    pct, status = b
    return f"Pil yüzde {pct}, {_state_text(status)}."


class Monitor:
    """Pil düşünce bir kez uyarır (yüzde 20 ve 10). Şarja takılınca uyarılar sıfırlanır."""

    def __init__(self, say, levels=(20, 10), interval: float = 60.0):
        self.say, self.levels, self.interval = say, sorted(levels, reverse=True), interval
        self._warned: set[int] = set()
        self._stop = threading.Event()

    def check(self) -> None:
        b = read_battery()
        if not b:
            return
        pct, status = b
        if status != "Discharging":
            self._warned.clear()
            return
        crossed = [lv for lv in self.levels if pct <= lv and lv not in self._warned]
        if crossed:
            self._warned.update(crossed)
            self.say(f"Pil seviyesi düşük, yüzde {pct}. Şarj aletini takar mısın?")

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


SKILLS = [
    {
        "name": "get_battery",
        "description": "Pil yüzdesini ve şarj durumunu söyler. 'Pil kaç', 'şarjım ne kadar kaldı' denince kullanılır.",
        "hidden": True,
        "run": get_battery,
    },
]
