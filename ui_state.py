"""Jarvis ile arayüz (ui.py) arasındaki paylaşılan durum: data/status.json ve data/control.json.

main.py durumu yazar (set_state / add_turn), ui.py okur. Arayüzden "sessize al" control.json'a yazılır.
Dosyalar data/ altında; .gitignore içinde.
"""
import os
import time

from skills import _store

STATES = {
    "starting": "Başlıyor",
    "listening": "Dinliyor",          # uyanma sözcüğünü bekliyor (maskot: idle)
    "recording": "Seni dinliyor",     # uyandı / mikrofon açık, komut kaydediliyor (maskot: listening)
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


ERROR_SHOW = 8.0   # sn: bir hatadan sonra maskot bu kadar 'error' gösterir
MASCOT = {"recording": "listening", "thinking": "thinking", "speaking": "speaking"}


def flag_error() -> None:
    """Bir komut hata verdi: maskot kısa süre 'error' gösterir (status.json'a zaman damgası)."""
    st = _status()
    st["error_ts"] = time.time()
    _store.save("status.json", st)


def mascot_state(state: str, pending: bool = False, error_ts: float = 0.0, now: float | None = None) -> str:
    """Çekirdek maskotunun data-state değeri: idle | listening | thinking | speaking | alert | error.
    Öncelik: yeni hata > bekleyen onay/plan > çalışma durumu. Bekleme, sessiz ve kapalı -> idle."""
    now = time.time() if now is None else now
    if state == "error" or (error_ts and now - error_ts < ERROR_SHOW):
        return "error"
    if pending:
        return "alert"
    return MASCOT.get(state, "idle")


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


def chat_voice() -> bool:
    """Panodaki Yazışma sekmesinde cevaplar sesli okunsun mu? (kalıcı ayar; varsayılan açık)"""
    return bool(_store.load("settings.json", {}).get("chat_voice", True))


def set_chat_voice(value: bool) -> None:
    st = _store.load("settings.json", {})
    st["chat_voice"] = bool(value)
    _store.save("settings.json", st)


def close_to_tray() -> bool:
    """Pano penceresini kapatınca Jarvis sistem tepsisine insin mi? (kalıcı ayar; varsayılan açık)"""
    return bool(_store.load("settings.json", {}).get("close_to_tray", True))


def set_close_to_tray(value: bool) -> None:
    st = _store.load("settings.json", {})
    st["close_to_tray"] = bool(value)
    _store.save("settings.json", st)


def cloud_enabled() -> bool:
    """Ücretsiz bulut modelleri kullanılabilsin mi? (kalıcı ayar; varsayılan açık; kapalıyken hiçbir şey buluta gitmez)"""
    return bool(_store.load("settings.json", {}).get("cloud", True))


def set_cloud_enabled(value: bool) -> None:
    st = _store.load("settings.json", {})
    st["cloud"] = bool(value)
    _store.save("settings.json", st)


THEMES = ("cyan", "amber", "green", "violet", "light")


def theme() -> str:
    t = _store.load("settings.json", {}).get("theme", "cyan")
    return t if t in THEMES else "cyan"


def set_theme(name: str) -> bool:
    if name not in THEMES:
        return False
    st = _store.load("settings.json", {})
    st["theme"] = name
    _store.save("settings.json", st)
    return True


# Üst kenar adası ayarları (settings.json "island"): pano Ayarlar > ADA ve tepsi menüsü değiştirir, ada her yoklamada okur.
ISLAND_DEFAULTS = {"enabled": True, "on_top": True, "mascot": True, "position": "center", "size": "normal", "theme": "auto"}
ISLAND_CHOICES = {"position": ("center", "left", "right"), "size": ("small", "normal", "large"), "theme": ("auto", *THEMES)}


def island_settings() -> dict:
    """Doğrulanmış ada ayarları (bozuk/eksik değer varsayılana düşer)."""
    raw = _store.load("settings.json", {}).get("island")
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k, d in ISLAND_DEFAULTS.items():
        v = raw.get(k, d)
        ok = isinstance(v, bool) if isinstance(d, bool) else v in ISLAND_CHOICES[k]
        out[k] = v if ok else d
    return out


def set_island(key: str, value) -> bool:
    """Tek bir ada ayarını kaydeder; bilinmeyen anahtar ya da geçersiz değer -> False (hiçbir şey yazılmaz)."""
    if key not in ISLAND_DEFAULTS:
        return False
    d = ISLAND_DEFAULTS[key]
    if (isinstance(d, bool) and not isinstance(value, bool)) or (not isinstance(d, bool) and value not in ISLAND_CHOICES[key]):
        return False
    st = _store.load("settings.json", {})
    st["island"] = {**island_settings(), key: value}
    _store.save("settings.json", st)
    return True


def island_theme() -> str:
    """Adanın kullanacağı tema: 'auto' ise panonun teması."""
    t = island_settings()["theme"]
    return theme() if t == "auto" else t


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
