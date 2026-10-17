"""Geri alma yığını (oturum boyunca bellekte). Ayar ve taşıma işlemleri buraya önceki durumu bırakır."""
import threading

MAX = 10
_lock = threading.Lock()
_stack: list[tuple[str, object]] = []


def push(description: str, undo_fn) -> None:
    with _lock:
        _stack.append((description, undo_fn))
        del _stack[:-MAX]


def undo_last() -> str:
    with _lock:
        item = _stack.pop() if _stack else None
    if not item:
        return "Geri alınacak bir işlem yok."
    description, fn = item
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        return f"Hata: geri alınamadı ({type(exc).__name__}: {exc})"
    return f"Geri aldım: {description}."
