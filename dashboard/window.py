"""Pano penceresi: kendi penceresinde açar (pywebview). Ayrı süreç olarak çalışır; ana süreç ölünce kapanır.

    python -m dashboard.window                 # data/dashboard.json'daki adresi açar
    python -m dashboard.window URL --parent PID

Sıra: (1) Qt penceresi + sistem tepsisi simgesi (pywebview[qt] ile gelen qtpy/QtWebEngine), (2) pywebview, (3) Chromium/Chrome --app,
(4) varsayılan tarayıcı. Tek pencere kuralı: ikinci kez açılırsa var olan pencere öne gelir (SIGUSR1), yenisi açılmaz.
Tepsi: pencereyi kapatmak Jarvis'i kapatmaz, pencere tepsiye iner; simgeye tıklayınca geri gelir (Ayarlar'dan kapatılabilir).
Kurulum: pip install "pywebview[qt]"   (Linux Mint: sudo apt install libxcb-cursor0)
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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

WIN_LOCK = os.environ.get("JARVIS_WINDOW_LOCK", "/tmp/jarvis-window.lock")
JARVIS_LOCK = "/tmp/jarvis.lock"
ICON = Path(__file__).resolve().parent.parent / "assets" / "jarvis-256.png"
_pending_show = False  # SIGUSR1 geldi: pencere öne getirilsin


def claim_single_window(lock_path: str = WIN_LOCK):
    """Pano penceresi zaten açıksa onu öne getirir ve None döner; değilse kilidi (süreç boyunca tutulacak) döndürür."""
    f = open(lock_path, "a+")  # noqa: SIM115
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.seek(0)
        try:
            pid = int(f.read().strip() or 0)
        except ValueError:
            pid = 0
        f.close()
        if pid and pid != os.getpid():
            try:
                os.kill(pid, signal.SIGUSR1)
            except OSError:
                pass
        return None
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


def install_show_signal() -> None:
    """SIGUSR1 = "pencereyi göster". İşleyici yokken varsayılan eylem süreci öldürür; o yüzden her kipte kurulur."""
    def handler(_sig, _frm):
        global _pending_show
        _pending_show = True
    signal.signal(signal.SIGUSR1, handler)


def take_show_request() -> bool:
    global _pending_show
    was, _pending_show = _pending_show, False
    return was


def jarvis_alive(parent: int | None) -> bool:
    """Jarvis (main.py) çalışıyor mu? --parent verildiyse o süreç; yoksa tek-örnek kilidi tutuluyor mu."""
    if parent:
        return alive(parent)
    try:
        f = open(JARVIS_LOCK, "a+")  # noqa: SIM115
    except OSError:
        return True
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return True
    fcntl.flock(f, fcntl.LOCK_UN)
    f.close()
    return False


def request_quit(url: str) -> bool:
    """Panonun kendi 'Jarvis'i kapat' komutunu çağırır (aynı anahtar, aynı yol)."""
    try:
        u = urlparse(url)
        token = (parse_qs(u.query).get("t") or [""])[0]
        req = urllib.request.Request(f"{u.scheme}://{u.netloc}/api/cmd", data=json.dumps({"id": "quit"}).encode(),
                                     headers={"X-Token": token, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3) as r:  # noqa: S310  (yalnızca 127.0.0.1)
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def close_to_tray_enabled() -> bool:
    try:
        from skills import _store  # noqa: PLC0415
        return bool(_store.load("settings.json", {}).get("close_to_tray", True))
    except Exception:  # noqa: BLE001
        return True


def run_qt(url: str, parent: int | None, hidden: bool = False) -> bool:
    """Qt penceresi + tepsi simgesi. Qt/QtWebEngine yoksa False döner (çağıran pywebview'e düşer)."""
    try:
        from qtpy import QtCore, QtGui, QtWidgets  # noqa: PLC0415
        from qtpy.QtWebEngineWidgets import QWebEngineView  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[pano] Qt/QtWebEngine yok ({type(exc).__name__}); pywebview deneniyor.", flush=True)
        return False

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("JARVIS")
    app.setQuitOnLastWindowClosed(False)
    try:
        app.setDesktopFileName("jarvis")
    except Exception:  # noqa: BLE001
        pass
    icon = QtGui.QIcon(str(ICON))
    app.setWindowIcon(icon)
    state = {"quitting": False, "told": False}

    tray = QtWidgets.QSystemTrayIcon(icon, app)
    tray.setToolTip("JARVIS — tıkla: panoyu aç")

    class Window(QtWidgets.QMainWindow):
        def closeEvent(self, ev):  # noqa: N802
            if not state["quitting"] and close_to_tray_enabled() and QtWidgets.QSystemTrayIcon.isSystemTrayAvailable() and tray.isVisible():
                ev.ignore()
                self.hide()
                if not state["told"]:
                    state["told"] = True
                    tray.showMessage("JARVIS", "Arka planda çalışıyor. Panoyu açmak için tepsideki simgeye tıkla.", icon, 4000)
            else:
                ev.accept()
                quit_window()

    win = Window()
    win.setWindowTitle("JARVIS Komut Merkezi")
    win.setWindowIcon(icon)
    win.resize(1500, 860)
    win.setMinimumSize(1000, 620)
    view = QWebEngineView(win)
    try:
        view.page().setBackgroundColor(QtGui.QColor("#030b18"))
    except Exception:  # noqa: BLE001
        pass
    view.setUrl(QtCore.QUrl(url))
    win.setCentralWidget(view)

    def show():
        if win.isMinimized():
            win.showNormal()
        win.show()
        win.raise_()
        win.activateWindow()

    def quit_window():
        state["quitting"] = True
        tray.hide()
        app.quit()

    def quit_jarvis():
        # Ana süreci panonun kendi komutuyla kapat; ulaşılamazsa yalnızca pencereyi kapat
        threading.Thread(target=lambda: request_quit(url), daemon=True).start()
        QtCore.QTimer.singleShot(5000, quit_window)  # Jarvis kapanınca zaten bekçi kapatır; takılırsa bu

    menu = QtWidgets.QMenu()
    menu.addAction("Panoyu aç", show)
    menu.addSeparator()
    menu.addAction("Jarvis'i kapat", quit_jarvis)
    tray.setContextMenu(menu)
    try:
        trigger = QtWidgets.QSystemTrayIcon.ActivationReason.Trigger
    except AttributeError:
        trigger = QtWidgets.QSystemTrayIcon.Trigger
    tray.activated.connect(lambda reason: show() if reason == trigger else None)
    tray.show()

    ticks = {"dead": 0}

    def tick():  # Python sinyalleri Qt döngüsünde ancak böyle çalışır; ayrıca "göster" isteği ve ana süreç bekçisi
        if take_show_request():
            show()
        if jarvis_alive(parent):
            ticks["dead"] = 0
        else:
            ticks["dead"] += 1
            if ticks["dead"] >= 3:  # art arda 3 kez: başlangıçtaki kısa boşlukta yanlışlıkla kapanma
                quit_window()

    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(400)
    if not hidden:
        show()
    (app.exec if hasattr(app, "exec") else app.exec_)()
    del timer, view
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--parent", type=int, default=None)
    ap.add_argument("--browser", action="store_true", help="pywebview yerine Chromium/Chrome --app")
    ap.add_argument("--hidden", action="store_true", help="açılışta pencereyi gösterme, yalnızca tepsiye otur")
    ap.add_argument("--no-qt", action="store_true", help="Qt penceresini/tepsiyi atla (pywebview'e geç)")
    a = ap.parse_args()
    lock = claim_single_window()
    if lock is None:  # pano zaten açık: öne getirildi
        return
    install_show_signal()
    url = a.url
    if not url:
        from skills import _store  # noqa: PLC0415
        url = _store.load("dashboard.json", {}).get("url")
    if not url:
        raise SystemExit("Pano adresi yok: önce Jarvis'i 'python main.py --dash' ile başlat.")
    if a.browser:
        return open_fallback(url, a.parent)
    if not a.no_qt and run_qt(url, a.parent, a.hidden):
        return
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

    def show_watch():  # ikinci kez açılma isteği: pencereyi geri getir
        while True:
            time.sleep(0.4)
            if take_show_request():
                try:
                    win.show()
                    win.restore()
                except Exception:  # noqa: BLE001
                    pass

    threading.Thread(target=show_watch, daemon=True).start()
    try:
        icon = Path(__file__).resolve().parent.parent / "assets" / "jarvis-256.png"
        try:
            webview.start(icon=str(icon))
        except TypeError:  # eski pywebview sürümü icon bilmez
            webview.start()
    except Exception as exc:  # noqa: BLE001  (conda ortamında GTK/Qt yoksa vb.)
        print(f"[pano] pywebview penceresi açılamadı ({type(exc).__name__}); tarayıcı penceresine geçiliyor.", flush=True)
        open_fallback(url, a.parent)


if __name__ == "__main__":
    main()
