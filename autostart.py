#!/usr/bin/env python3
"""Oturum açılınca Jarvis'i eller serbest modda otomatik başlatır (Linux Mint / freedesktop autostart).

    python autostart.py --install     # ~/.config/autostart/jarvis.desktop oluşturur
    python autostart.py --remove      # kaldırır
    python autostart.py --status

Notlar:
- Şu an çalışan Python (freya ortamı) ve bu klasör kaydedilir; ortamı değiştirirsen yeniden --install yap.
- Terminal açmaz. Çıktı data/jarvis.log dosyasına yazılır (git dışında).
- Oturumdan 20 sn sonra başlar (ses sistemi ve ağ hazır olsun).
- Kapatmak için "Jarvis, kapat kendini" de ya da: pkill -f 'main.py --wake'
"""
import argparse
import json
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESKTOP = Path.home() / ".config" / "autostart" / "jarvis.desktop"


def flags() -> str:
    """Her zaman: --wake --ui --morning. Telegram kuruluysa (data/telegram.json) --telegram de eklenir."""
    out = ["--wake", "--ui", "--morning"]
    try:
        cfg = json.loads((HERE / "data" / "telegram.json").read_text(encoding="utf-8"))
        if cfg.get("token") and cfg.get("chat_id"):
            out.append("--telegram")
    except (OSError, ValueError):
        pass
    return " ".join(out)


def desktop_text() -> str:
    log = HERE / "data" / "jarvis.log"
    cmd = f"mkdir -p {shlex.quote(str(log.parent))}; cd {shlex.quote(str(HERE))} && exec {shlex.quote(sys.executable)} main.py {flags()} >> {shlex.quote(str(log))} 2>&1"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Jarvis\n"
        "Comment=Sesli asistan (Hey Jarvis)\n"
        f"Exec=sh -c {shlex.quote(cmd)}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=20\n"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--install", action="store_true")
    g.add_argument("--remove", action="store_true")
    g.add_argument("--status", action="store_true")
    a = p.parse_args()
    if a.install:
        DESKTOP.parent.mkdir(parents=True, exist_ok=True)
        DESKTOP.write_text(desktop_text(), encoding="utf-8")
        print(f"Kuruldu: {DESKTOP}\nBayraklar: {flags()}\nBir sonraki oturum açılışında başlar. Log: {HERE / 'data' / 'jarvis.log'}")
    elif a.remove:
        if DESKTOP.exists():
            DESKTOP.unlink()
            print("Otomatik başlatma kaldırıldı.")
        else:
            print("Zaten kurulu değil.")
    else:
        print(f"Kurulu: {DESKTOP}\n" + DESKTOP.read_text(encoding="utf-8") if DESKTOP.exists() else "Kurulu değil.")


if __name__ == "__main__":
    main()
