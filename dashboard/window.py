"""Pano penceresi: kendi penceresinde açar (pywebview). Ayrı süreç olarak çalışır; ana süreç ölünce kapanır.

    python -m dashboard.window                 # data/dashboard.json'daki adresi açar
    python -m dashboard.window URL --parent PID

pywebview yoksa Chromium/Chrome --app moduna, o da yoksa varsayılan tarayıcıya düşer.
Kurulum: pip install pywebview   (Linux Mint: sudo apt install python3-gi gir1.2-webkit2-4.1 da gerekebilir)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def alive(pid: int | None) -> bool:
    if not pid:
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def open_fallback(url: str, parent: int | None) -> None:
    for exe in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser"):
        if shutil.which(exe):
            prof = Path.home() / ".cache" / "jarvis-dash-profile"
            p = subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={prof}", "--window-size=1500,860"])
            while p.poll() is None and alive(parent):
                time.sleep(1)
            if p.poll() is None:
                p.terminate()
            return
    webbrowser.open(url)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--parent", type=int, default=None)
    ap.add_argument("--browser", action="store_true", help="pywebview yerine Chromium/Chrome --app")
    a = ap.parse_args()
    url = a.url
    if not url:
        from skills import _store  # noqa: PLC0415
        url = _store.load("dashboard.json", {}).get("url")
    if not url:
        raise SystemExit("Pano adresi yok: önce Jarvis'i 'python main.py --dash' ile başlat.")
    if a.browser:
        return open_fallback(url, a.parent)
    try:
        import webview  # noqa: PLC0415
    except ImportError:
        print("[pano] pywebview yok (pip install pywebview); tarayıcı penceresi açılıyor.", flush=True)
        return open_fallback(url, a.parent)

    win = webview.create_window("JARVIS Komut Merkezi", url, width=1500, height=860, min_size=(1000, 620), background_color="#030b18")

    def watch():  # ana Jarvis kapanınca pencere de kapansın
        while alive(a.parent):
            time.sleep(1)
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            os._exit(0)

    threading.Thread(target=watch, daemon=True).start()
    try:
        webview.start()
    except Exception as exc:  # noqa: BLE001  (conda ortamında GTK/Qt yoksa vb.)
        print(f"[pano] pywebview penceresi açılamadı ({type(exc).__name__}); tarayıcı penceresine geçiliyor.", flush=True)
        open_fallback(url, a.parent)


if __name__ == "__main__":
    main()
