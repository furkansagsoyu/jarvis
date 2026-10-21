"""Tehlikeli işlemler için onay kapısı.

Onay model tarafından VERİLEMEZ: araçlar işi hemen yapmaz, sadece bekleyen bir işlem kaydeder.
Brain, kullanıcının bir sonraki cümlesini modele göndermeden önce burada "evet / hayır" diye kontrol eder.
Modelin "confirmed" gibi bir parametresi yoktur; yani model kendi kendine onaylayamaz.
"""
import re
import threading
import time

TTL = 60  # saniye; süre dolarsa işlem iptal sayılır
YES = re.compile(r"^\W*(evet|onaylıyorum|onayla|tamam|olur|peki|yap|sil|taşı|aynen|kesinlikle)\b", re.I)
# Plan onayı ("Başlayayım mı?") için doğal cevaplar da geçerli; tehlikeli işlem onayında (classify) KULLANILMAZ.
PLAN_YES = re.compile(r"^\W*(?:evet|onaylıyorum|onayla|tamam|olur|peki|yap|aynen|kesinlikle|başla\w*|başlat\w*|devam\w*|hadi|haydi|buyur|çalıştır\w*)\b", re.I)
PLAN_NO = re.compile(r"\b(?:başlama\w*|başlatma\w*|etme\w*|çalıştırma\w*)\b", re.I)
NO = re.compile(r"\b(hayır|hayir|vazgeç|vazgeçtim|iptal|yapma|olmaz|dur|istemiyorum)\b", re.I)

_lock = threading.Lock()
_pending: dict | None = None


def request(description: str, run) -> str:
    """Bekleyen işlemi kaydeder; kullanıcıya söylenecek soruyu döndürür."""
    global _pending
    with _lock:
        _pending = {"run": run, "expires": time.time() + TTL}
    return f"{description} Onaylıyor musun?"


def has_pending() -> bool:
    global _pending
    with _lock:
        if _pending and time.time() > _pending["expires"]:
            _pending = None
        return _pending is not None


def classify(text: str) -> str:
    """'yes' | 'no' | 'other'. Önce hayır kontrol edilir."""
    if NO.search(text or ""):
        return "no"
    if YES.search(text or ""):
        return "yes"
    return "other"


def classify_plan(text: str) -> str:
    """Plan onayı için 'yes' | 'no' | 'other' ("başla", "devam et" de evet sayılır; hayır önceliklidir)."""
    if NO.search(text or "") or PLAN_NO.search(text or ""):
        return "no"
    return "yes" if PLAN_YES.search(text or "") else "other"


def approve() -> str:
    global _pending
    with _lock:
        item, _pending = _pending, None
    if not item or time.time() > item["expires"]:
        return "Onay süresi dolmuştu, işlem yapılmadı."
    try:
        return item["run"]()
    except Exception as exc:  # noqa: BLE001
        return f"Hata: {type(exc).__name__}: {exc}"


def wrap(fn) -> None:
    """Bekleyen işlemin sonucunu fn'den geçirir (ajan modu adımı sürdürmek için kullanır). Süre ve onay kuralı değişmez."""
    with _lock:
        if _pending:
            orig = _pending["run"]
            _pending["run"] = lambda: fn(orig())


def cancel() -> None:
    global _pending
    with _lock:
        _pending = None
