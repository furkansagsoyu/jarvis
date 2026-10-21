"""Pano penceresi testleri: tek pencere (SIGUSR1), tepsiye inme mantığı (sahte Qt ile), kapatma çağrısı, ayar/komut."""
import http.server
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
os.environ["JARVIS_WINDOW_LOCK"] = os.path.join(tempfile.mkdtemp(), "win.lock")
from dashboard import window as W  # noqa: E402
from skills import _store  # noqa: E402
import ui_state  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


# ---------------------------------------------------------------- tek pencere: ikinci açılış var olanı öne getirir
lock_path = os.path.join(tempfile.mkdtemp(), "l.lock")
child_code = (
    "import sys,time;sys.path.insert(0,%r);from dashboard import window as W\n"
    "f=W.claim_single_window(%r);W.install_show_signal();print('READY',f is not None,flush=True)\n"
    "t=time.time()\n"
    "while time.time()-t<8:\n"
    "    if W.take_show_request(): print('SHOWN',flush=True);break\n"
    "    time.sleep(0.05)\n" % (os.path.dirname(os.path.abspath(__file__)), lock_path))
ch = subprocess.Popen([sys.executable, "-c", child_code], stdout=subprocess.PIPE, text=True)
check("ilk pencere kilidi alır", ch.stdout.readline().strip() == "READY True")
check("ikinci açılış kilidi alamaz (None) ve ilkine sinyal yollar", W.claim_single_window(lock_path) is None)
check("var olan pencere 'göster' isteğini alır", ch.stdout.readline().strip() == "SHOWN")
ch.wait(timeout=5)
f = W.claim_single_window(lock_path)
check("pencere ölünce kilit serbest, yeni pencere açılabilir", f is not None and open(lock_path).read().strip() == str(os.getpid()))
f.close()

W.install_show_signal()
os.kill(os.getpid(), signal.SIGUSR1)
time.sleep(0.05)
check("SIGUSR1 süreci öldürmez, istek bir kez okunur", W.take_show_request() is True and W.take_show_request() is False)

dead = subprocess.Popen(["true"])
dead.wait()
check("bekçi: canlı ana süreç", W.jarvis_alive(os.getpid()) is True)
check("bekçi: ölü ana süreç", W.jarvis_alive(dead.pid) is False)

# ---------------------------------------------------------------- 'Jarvis'i kapat' çağrısı panonun kendi komutuyla
seen = []


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        seen.append((self.path, self.headers.get("X-Token"), json.loads(body)))
        ok = self.headers.get("X-Token") == "abc"
        self.send_response(200 if ok else 403)
        self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
check("kapatma: doğru anahtarla /api/cmd quit", W.request_quit(base + "/?t=abc") is True and seen[-1] == ("/api/cmd", "abc", {"id": "quit"}))
check("kapatma: yanlış anahtar reddedilir", W.request_quit(base + "/?t=zzz") is False)
srv.shutdown()
check("kapatma: sunucu yoksa False (çökmez)", W.request_quit("http://127.0.0.1:1/?t=abc") is False)

# ---------------------------------------------------------------- ayar + panodan açıp kapatma
check("tepsiye inme varsayılan açık", ui_state.close_to_tray() is True and W.close_to_tray_enabled() is True)
ui_state.set_close_to_tray(False)
check("ayar kapatılınca pencere okur", W.close_to_tray_enabled() is False)
ui_state.set_close_to_tray(True)

# ---------------------------------------------------------------- sahte Qt ile pencere/tepsi davranışı
REG = {}


class Sig:
    def __init__(s):
        s.cbs = []

    def connect(s, f):
        s.cbs.append(f)

    def emit(s, *a):
        [f(*a) for f in s.cbs]


class QUrl:
    def __init__(s, u):
        s.u = u


class QTimer:
    def __init__(s):
        s.timeout = Sig()
        REG["timer"] = s

    def start(s, ms):
        s.ms = ms

    @staticmethod
    def singleShot(ms, fn):
        REG.setdefault("shots", []).append((ms, fn))


class QIcon:
    def __init__(s, p=""):
        s.p = p


class QColor:
    def __init__(s, c):
        s.c = c


class QApplication:
    _inst = None

    def __init__(s, argv):
        QApplication._inst = s
        s.quit_called = False

    @classmethod
    def instance(cls):
        return cls._inst

    def setApplicationName(s, n): pass  # noqa: E704,N802
    def setQuitOnLastWindowClosed(s, v): s.qolwc = v  # noqa: E704,N802
    def setDesktopFileName(s, n): s.dfn = n  # noqa: E704,N802
    def setWindowIcon(s, i): pass  # noqa: E704,N802

    def quit(s):
        s.quit_called = True

    def exec(s):
        REG["scenario"]()
        return 0


class CloseEv:
    accepted = None

    def ignore(s):
        s.accepted = False

    def accept(s):
        s.accepted = True


class QMainWindow:
    def __init__(s):
        s.visible, s.shown = False, 0
        REG["win"] = s

    def setWindowTitle(s, t): s.title = t  # noqa: E704,N802
    def setWindowIcon(s, i): pass  # noqa: E704,N802
    def resize(s, w, h): pass  # noqa: E704
    def setMinimumSize(s, w, h): pass  # noqa: E704,N802
    def setCentralWidget(s, w): s.view = w  # noqa: E704,N802
    def isMinimized(s): return False  # noqa: E704,N802
    def raise_(s): pass  # noqa: E704
    def activateWindow(s): pass  # noqa: E704,N802

    def show(s):
        s.visible = True
        s.shown += 1

    def hide(s):
        s.visible = False

    def close(s):
        ev = CloseEv()
        s.closeEvent(ev)
        return ev


class QSystemTrayIcon:
    AVAIL = True

    class ActivationReason:
        Trigger = 3
        Context = 1

    def __init__(s, icon, parent):
        s.vis, s.msgs, s.activated = False, [], Sig()
        REG["tray"] = s

    @staticmethod
    def isSystemTrayAvailable():  # noqa: N802
        return QSystemTrayIcon.AVAIL

    def setToolTip(s, t): s.tip = t  # noqa: E704,N802
    def setContextMenu(s, m): s.menu = m  # noqa: E704,N802
    def show(s): s.vis = QSystemTrayIcon.AVAIL  # noqa: E704
    def hide(s): s.vis = False  # noqa: E704
    def isVisible(s): return s.vis  # noqa: E704,N802
    def showMessage(s, *a): s.msgs.append(a)  # noqa: E704,N802


class QMenu:
    def __init__(s):
        s.items = []

    def addAction(s, text, fn):  # noqa: N802
        s.items.append((text, fn))

    def addSeparator(s):  # noqa: N802
        pass


class Page:
    def setBackgroundColor(s, c): pass  # noqa: E704,N802


class QWebEngineView:
    def __init__(s, parent=None):
        REG["view"] = s

    def page(s): return Page()  # noqa: E704
    def setUrl(s, u): s.url = u.u  # noqa: E704,N802


def install_fake():
    qtpy = types.ModuleType("qtpy")
    qtpy.QtCore = types.SimpleNamespace(QUrl=QUrl, QTimer=QTimer)
    qtpy.QtGui = types.SimpleNamespace(QIcon=QIcon, QColor=QColor)
    qtpy.QtWidgets = types.SimpleNamespace(QApplication=QApplication, QMainWindow=QMainWindow, QSystemTrayIcon=QSystemTrayIcon, QMenu=QMenu)
    eng = types.ModuleType("qtpy.QtWebEngineWidgets")
    eng.QWebEngineView = QWebEngineView
    sys.modules.update({"qtpy": qtpy, "qtpy.QtWebEngineWidgets": eng})


def run(scenario, parent=None, hidden=False, avail=True):
    REG.clear()
    QApplication._inst = None
    QSystemTrayIcon.AVAIL = avail
    REG["scenario"] = scenario
    return W.run_qt("http://127.0.0.1:9/?t=x", parent, hidden)


for m in ("qtpy", "qtpy.QtWebEngineWidgets"):
    sys.modules[m] = None  # içe aktarma ImportError versin
check("Qt yoksa run_qt False döner (pywebview'e düşülür)", W.run_qt("http://x", None) is False)
install_fake()


def s_basic():
    w, t, a = REG["win"], REG["tray"], QApplication._inst
    check("açılışta pencere gösterilir, tepsi simgesi görünür", w.visible and t.vis and w.view.url.startswith("http://127.0.0.1:9/"))
    check("son pencere kapanınca uygulama bitmez", a.qolwc is False and a.dfn == "jarvis")
    ev = w.close()
    check("kapat düğmesi: pencere gizlenir, süreç yaşar", ev.accepted is False and not w.visible and not a.quit_called)
    check("ilk inişte tepsi bildirimi", len(t.msgs) == 1)
    t.activated.emit(QSystemTrayIcon.ActivationReason.Context)
    check("sağ tık (bağlam) pencereyi açmaz", not w.visible)
    t.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    check("tepsi simgesine tıklayınca pano geri gelir", w.visible)
    w.close()
    check("ikinci inişte bildirim tekrarlanmaz", len(t.msgs) == 1 and not w.visible)
    os.kill(os.getpid(), signal.SIGUSR1)
    time.sleep(0.05)
    REG["timer"].timeout.emit()
    check("ikinci JARVIS başlatışı (SIGUSR1) gizli pencereyi açar", w.visible)
    texts = [x[0] for x in t.menu.items]
    check("tepsi menüsü: Panoyu aç + Jarvis'i kapat", texts == ["Panoyu aç", "Jarvis'i kapat"])
    w.hide()
    dict(t.menu.items)["Panoyu aç"]()
    check("menüden Panoyu aç", w.visible)
    W.take_show_request()


check("sahte Qt: temel akış çalıştı", run(s_basic) is True)


def s_off():
    w, a = REG["win"], QApplication._inst
    ui_state.set_close_to_tray(False)
    ev = w.close()
    check("ayar kapalıyken kapat düğmesi pencereyi tamamen kapatır", ev.accepted is True and a.quit_called and not REG["tray"].vis)
    ui_state.set_close_to_tray(True)


run(s_off)


def s_notray():
    ev = REG["win"].close()
    check("sistem tepsisi yoksa pencere kaybolmaz (normal kapanır)", ev.accepted is True and QApplication._inst.quit_called)


run(s_notray, avail=False)


def s_hidden():
    check("--hidden: açılışta pencere gösterilmez, tepsi var", not REG["win"].visible and REG["tray"].vis)


run(s_hidden, hidden=True)


def s_guard():
    t, a = REG["timer"], QApplication._inst
    t.timeout.emit()
    t.timeout.emit()
    check("ana süreç ölüyse 2 kontrolde kapanmaz (yanlış alarm payı)", not a.quit_called)
    t.timeout.emit()
    check("ana süreç ölünce 3. kontrolde tepsi ve pencere kapanır", a.quit_called and not REG["tray"].vis)


run(s_guard, parent=dead.pid)


def s_quit():
    called = []
    W.request_quit = lambda u: called.append(u) or True
    dict(REG["tray"].menu.items)["Jarvis'i kapat"]()
    time.sleep(0.2)
    check("tepsi menüsü 'Jarvis'i kapat' pano komutunu çağırır", called and called[0].startswith("http://127.0.0.1:9/"))
    check("takılırsa 5 sn sonra pencere yine de kapanır", any(ms == 5000 for ms, _ in REG.get("shots", [])))
    [fn for ms, fn in REG["shots"] if ms == 5000][0]()
    check("zaman aşımı kapatması uygulamayı bitirir", QApplication._inst.quit_called)


run(s_quit)

# ---------------------------------------------------------------- panodan ayarı değiştirme komutu
from dashboard import server  # noqa: E402
d = server.Dashboard(types.SimpleNamespace(brain=None), lambda *a, **k: None, port=0 or 18700)
before = ui_state.close_to_tray()
d.run_command("traytoggle")
check("pano komutu 'traytoggle' ayarı tersler", ui_state.close_to_tray() is (not before))
d.run_command("traytoggle")
check("tekrar açar", ui_state.close_to_tray() is before)
d.httpd.server_close()

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
