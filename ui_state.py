"""Jarvis ile arayüz (ui.py) arasındaki paylaşılan durum: data/status.json ve data/control.json.

main.py durumu yazar (set_state / add_turn), ui.py okur. Arayüzden "sessize al" control.json'a yazılır.
Dosyalar data/ altında; .gitignore içinde.
"""
import os
import time

from skills import _store

STATES = {
    "starting": "Başlıyor",
    "listening": "Dinliyor",
    "thinking": "Düşünüyor",
    "speaking": "Konuşuyor",
    "muted": "Sessizde",
    "stopped": "Kapalı",
}
MAX_TURNS = 8


def _status() -> dict:
    return _store.load("status.json", {"state": "starting", "turns": []})


def set_state(state: str) -> None:
    st = _status()
    st.update(state=state, ts=time.time(), pid=os.getpid())
    _store.save("status.json", st)


def add_turn(who: str, text: str) -> None:
    """who: 'sen' | 'jarvis'. Son MAX_TURNS satır tutulur."""
    text = (text or "").strip()
    if not text:
        return
    try:
        import convlog  # noqa: PLC0415
        convlog.append(who, text)  # kalıcı günlük (panodaki Konuşmalar)
    except Exception:  # noqa: BLE001  (günlük hatası konuşmayı bozmasın)
        pass
    st = _status()
    st["turns"] = (st.get("turns") or []) + [{"who": who, "text": text}]
    st["turns"] = st["turns"][-MAX_TURNS:]
    st["ts"] = time.time()
    _store.save("status.json", st)


def read_status() -> dict:
    st = _status()
    st.setdefault("state", "starting")
    st.setdefault("turns", [])
    return st


def is_muted() -> bool:
    return bool(_store.load("control.json", {}).get("mute"))


def set_muted(value: bool) -> None:
    ctl = _store.load("control.json", {})
    ctl["mute"] = bool(value)
    _store.save("control.json", ctl)


def request_stop() -> None:
    """Arayüzden "Sustur": Jarvis'in o an okuduğu cevabı keser."""
    ctl = _store.load("control.json", {})
    ctl["stop"] = True
    _store.save("control.json", ctl)


def consume_stop() -> bool:
    """Sustur isteği varsa True döner ve isteği siler."""
    ctl = _store.load("control.json", {})
    if not ctl.get("stop"):
        return False
    ctl["stop"] = False
    _store.save("control.json", ctl)
    return True


def is_focus() -> bool:
    """Odak modu: arka plan bildirimleri sesli söylenmez (panoda görünür)."""
    return bool(_store.load("control.json", {}).get("focus"))


def set_focus(value: bool) -> None:
    ctl = _store.load("control.json", {})
    ctl["focus"] = bool(value)
    _store.save("control.json", ctl)


def request_listen() -> None:
    """Panodan "Jarvis ile konuş": uyanma sözcüğü beklemeden hemen dinle."""
    ctl = _store.load("control.json", {})
    ctl["listen"] = True
    _store.save("control.json", ctl)


def consume_listen() -> bool:
    ctl = _store.load("control.json", {})
    if not ctl.get("listen"):
        return False
    ctl["listen"] = False
    _store.save("control.json", ctl)
    return True


def reset() -> None:
    """Program açılırken: eski oturumdan kalan sessiz modu ve konuşma satırlarını temizler."""
    _store.save("control.json", {"mute": False, "focus": False})
    _store.save("status.json", {"state": "starting", "turns": [], "ts": time.time(), "pid": os.getpid()})
