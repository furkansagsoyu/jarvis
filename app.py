#!/usr/bin/env python3
"""JARVIS masaüstü uygulaması başlatıcısı (terminalsiz).

Uygulama menüsündeki "JARVIS" simgesi bunu çalıştırır (kurulum: python install_app.py).
- Jarvis kapalıysa: arka planda başlatır (çıktı data/jarvis.log), model yüklenince pano penceresi kendiliğinden açılır.
- Jarvis zaten çalışıyorsa: pano penceresini öne getirir ya da yeniden açar (tek pencere kuralı dashboard/window.py'de).
  Pencereyi kapatmak Jarvis'i kapatmaz: pencere sağ alttaki sistem tepsisine iner, simgeye tıklayınca geri gelir.
  Tamamen kapatmak için tepsi menüsü > "Jarvis'i kapat", panoda Ayarlar > "Jarvis'i kapat" ya da "Jarvis, kapat kendini" de.
- Bayrakları değiştirmek için data/launch_args.txt dosyasına tek satır yaz (örn. --wake --dash --telegram).
- Terminalde hata ayıklamak için: python main.py --wake --dash
"""
from __future__ import annotations

import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LOCK = "/tmp/jarvis.lock"
LOG_MAX = 5 * 1024 * 1024


def data_dir() -> Path:
    from skills import _store  # noqa: PLC0415
    return _store.DATA_DIR


def is_running() -> bool:
    """main.py tek-örnek kilidini (aynı dosya) tutuyor mu?"""
    try:
        f = open(LOCK, "a+")  # noqa: SIM115
    except OSError:
        return False
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return True
    fcntl.flock(f, fcntl.LOCK_UN)
    f.close()
    return False


def default_args() -> list[str]:
    """data/launch_args.txt varsa o; yoksa --wake --dash --morning (+ Telegram kuruluysa --telegram)."""
    try:
        txt = (data_dir() / "launch_args.txt").read_text(encoding="utf-8").strip()
        if txt:
            return txt.split()
    except OSError:
        pass
    out = ["--wake", "--dash", "--morning"]
    try:
        cfg = json.loads((data_dir() / "telegram.json").read_text(encoding="utf-8"))
        if cfg.get("token") and cfg.get("chat_id"):
            out.append("--telegram")
    except (OSError, ValueError):
        pass
    return out


def notify(text: str) -> None:
    if shutil.which("notify-send"):
        icon = HERE / "assets" / "jarvis-256.png"
        subprocess.run(["notify-send", "-i", str(icon), "JARVIS", text], check=False, timeout=5)


def open_window() -> bool:
    url = None
    try:
        url = json.loads((data_dir() / "dashboard.json").read_text(encoding="utf-8")).get("url")
    except (OSError, ValueError):
        pass
    if not url:
        notify("Pano adresi bulunamadı; Jarvis --dash ile başlamamış olabilir.")
        return False
    subprocess.Popen([sys.executable, "-m", "dashboard.window", url], cwd=str(HERE), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def start_jarvis(args: list[str]) -> subprocess.Popen:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    log = d / "jarvis.log"
    if log.exists() and log.stat().st_size > LOG_MAX:
        log.replace(d / "jarvis.log.old")
    out = open(log, "a", encoding="utf-8")  # noqa: SIM115
    out.write(f"\n===== başlatıldı: {' '.join(args)} =====\n")
    out.flush()
    return subprocess.Popen([sys.executable, str(HERE / "main.py"), *args], cwd=str(HERE), stdout=out, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)


def debug_in_terminal() -> int:
    """Hata ayıklama: Jarvis'i terminal penceresinde başlatır (çıktıyı canlı görürsün)."""
    if is_running():
        notify("Jarvis zaten çalışıyor; önce kapat (panoda Ayarlar > Jarvis'i kapat).")
        return 1
    inner = f"cd {shlex.quote(str(HERE))} && {shlex.quote(sys.executable)} main.py {' '.join(default_args())}; echo; read -p 'Kapatmak için Enter'"
    for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["xfce4-terminal", "-x"], ["xterm", "-e"]):
        if shutil.which(term[0]):
            subprocess.Popen([*term, "bash", "-c", inner], start_new_session=True)
            return 0
    notify("Terminal bulunamadı; elle çalıştır: python main.py --wake --dash")
    return 1


def main() -> int:
    if "--debug" in sys.argv:
        return debug_in_terminal()
    if is_running():
        return 0 if open_window() else 1
    notify("Başlıyor… modeller yükleniyor, pano birazdan açılır.")
    start_jarvis(default_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
