"""Fare/klavye kontrolü testleri (xdotool sahte)."""
import os
import tempfile

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
from skills import _confirm as confirm  # noqa: E402
from skills import desktop_input as d  # noqa: E402


def check(name, cond):
    print(("OK   " if cond else "HATA ") + name)
    return bool(cond)


def run() -> bool:
    ok = True
    log, state = [], {"cls": "firefox", "title": "Sayfa", "mouse": (500, 400)}

    def fake(*a):
        log.append(a)
        if a[:2] == ("getactivewindow", "getwindowclassname"):
            return state["cls"]
        if a[:2] == ("getactivewindow", "getwindowname"):
            return state["title"]
        if a[0] == "getdisplaygeometry":
            return "1920 1080"
        if a[0] == "getmouselocation":
            return f"X={state['mouse'][0]}\nY={state['mouse'][1]}\nSCREEN=0"
        return ""
    real, d._xdo = d._xdo, fake
    try:
        r = d.mouse_move("sağa", "")
        ok &= check("fare sağa 200 px", ("mousemove", "700", "400") in log)
        log.clear(); state["mouse"] = (1900, 10)
        d.mouse_move("sağa", "çok"); d.mouse_move("yukarı", "")
        ok &= check("ekran dışına çıkmaz", ("mousemove", "1919", "10") in log and ("mousemove", "1900", "0") in log)
        log.clear(); d.mouse_move("sol üst", "")
        ok &= check("köşeye gider", ("mousemove", "96", "86") in log)
        log.clear(); d.scroll("aşağı", "")
        ok &= check("kaydırma tekeri 5", any(c[0] == "click" and c[-1] == "5" for c in log))

        log.clear(); r = d.mouse_click("sol", False)
        ok &= check("tıklama onay ister, henüz tıklamadı", confirm.has_pending() and not any(c[0] == "click" for c in log))
        confirm.cancel()
        log.clear(); d.mouse_click("sağ", True); out = confirm.approve()
        ok &= check("onaylayınca çift sağ tıklar", "Tıkladım" in out and ("click", "--repeat", "2", "--delay", "80", "3") in log)

        log.clear(); r = d.keyboard_type("merhaba dünya")
        ok &= check("yazma onay ister", confirm.has_pending() and not any(c[0] == "type" for c in log))
        confirm.approve()
        ok &= check("onaylayınca yazar", ("type", "--delay", "25", "--", "merhaba dünya") in log)

        for cls, title, label in (("gnome-terminal-server", "furkan@pc", "terminal"), ("keepassxc", "KeePassXC", "parola yöneticisi"),
                                  ("firefox", "Ziraat Bankası - Giriş", "banka başlığı"), ("polkit-gnome", "Authentication Required", "polkit")):
            state.update(cls=cls, title=title); log.clear()
            r = d.keyboard_type("ls"); r2 = d.mouse_click("sol", False); r3 = d.press_key("enter")
            ok &= check(f"{label}: yazma/tıklama/tuş reddi", not confirm.has_pending() and "Güvenlik" in r + r2 + r3
                        and not any(c[0] in ("type", "click", "key") for c in log))
        state.update(cls="firefox", title="Sayfa")
        d.keyboard_type("x")
        state.update(cls="gnome-terminal-server", title="bash")  # onay beklerken pencere terminale döndü
        ok &= check("onay sonrası pencere değişti: yazılmaz", "yazmadım" in confirm.approve())
        state.update(cls="firefox", title="Sayfa")
        for k in ("ctrl+alt+t", "alt+f2", "ctrl+alt+f3", "Ctrl + Alt + Delete"):
            ok &= check(f"yasak kısayol {k}", "kullanmıyorum" in d.press_key(k))
        log.clear(); d.press_key("aşağı ok")
        ok &= check("gezinti tuşu onaysız", ("key", "Down") in log and not confirm.has_pending())
        d.press_key("kopyala")
        ok &= check("kopyala onay ister", confirm.has_pending()); confirm.approve()
        ok &= check("kopyala ctrl+c basar", ("key", "ctrl+c") in log)
    finally:
        d._xdo = real
        confirm.cancel()
    # xdotool yoksa anlaşılır hata
    import shutil
    if not shutil.which("xdotool"):
        ok &= check("xdotool yok: açık mesaj", "xdotool" in d.mouse_move("sağa", ""))
    return bool(ok)


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
