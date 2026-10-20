"""Kalıcı konuşma günlüğü (data/conversations.jsonl): her tur (sen / jarvis) satır satır eklenir.

- Panodaki "Konuşmalar" sekmesi ve arama bunu okur.
- Saklama süresi data/settings.json -> conv_days (varsayılan 30 gün, 0 = süresiz); eskiler otomatik silinir.
- Tek tek, güne göre ya da tümü elle silinebilir.
Sadece söylenen/duyulan metin tutulur (dosya içeriği, ekran görüntüsü vb. değil). Dosya data/ altında, git dışında.
"""
from __future__ import annotations

import json
import threading
import time

from skills import _store

FILE = "conversations.jsonl"
DEFAULT_DAYS = 30
MAX_TEXT = 2000
_lock = threading.RLock()
_last_prune = 0.0
_seq = 0


def _p():
    return _store.path(FILE)


def _norm(s: str) -> str:
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def retention_days() -> int:
    try:
        return max(0, int(_store.load("settings.json", {}).get("conv_days", DEFAULT_DAYS)))
    except (TypeError, ValueError):
        return DEFAULT_DAYS


def set_retention(days: int) -> int:
    days = max(0, min(3650, int(days)))
    st = _store.load("settings.json", {})
    st["conv_days"] = days
    _store.save("settings.json", st)
    prune(force=True)
    return days


def _read() -> list[dict]:
    out = []
    try:
        with _p().open(encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _write(items: list[dict]) -> None:
    tmp = _p().with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    tmp.replace(_p())


def append(who: str, text: str) -> None:
    global _seq
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        return
    with _lock:
        _seq += 1
        now = time.time()
        item = {"id": int(now * 1000) * 100 + _seq % 100, "ts": now, "who": who, "text": text}
        with _p().open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    prune()


def prune(force: bool = False) -> int:
    """Saklama süresinden eski satırları siler (saatte en çok bir kez, force ile hemen). Silinen sayısını döner."""
    global _last_prune
    now = time.time()
    if not force and now - _last_prune < 3600:
        return 0
    _last_prune = now
    days = retention_days()
    if not days:
        return 0
    cutoff = now - days * 86400
    with _lock:
        items = _read()
        keep = [i for i in items if i.get("ts", 0) >= cutoff]
        if len(keep) != len(items):
            _write(keep)
        return len(items) - len(keep)


def recent(n: int = 30) -> list[dict]:
    with _lock:
        return _read()[-n:]


def query(q: str = "", limit: int = 300) -> list[dict]:
    """En yeniden eskiye; q verilirse metinde geçenler (Türkçe büyük/küçük harf duyarsız)."""
    with _lock:
        items = _read()
    if q:
        nq = _norm(q.strip())
        items = [i for i in items if nq in _norm(i.get("text", ""))]
    return items[::-1][:limit]


def count() -> int:
    with _lock:
        return len(_read())


def revision() -> str:
    with _lock:
        items = _read()
    return f"{len(items)}:{items[-1]['id'] if items else 0}"


def delete(item_id: int) -> bool:
    with _lock:
        items = _read()
        keep = [i for i in items if i.get("id") != item_id]
        if len(keep) == len(items):
            return False
        _write(keep)
        return True


def delete_day(day: str) -> int:
    """day: 'YYYY-MM-DD' (yerel saat)."""
    with _lock:
        items = _read()
        keep = [i for i in items if time.strftime("%Y-%m-%d", time.localtime(i.get("ts", 0))) != day]
        if len(keep) != len(items):
            _write(keep)
        return len(items) - len(keep)


def clear() -> int:
    with _lock:
        n = len(_read())
        _write([])
        return n
