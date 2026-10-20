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


SESSION_GAP = 1800  # iki mesaj arası 30 dakikadan uzunsa yeni sohbet başlar


def sessions(q: str = "", gap: int = SESSION_GAP) -> list[dict]:
    """Günlüğü sohbetlere böler (en yeni başta). q verilirse yalnızca metni geçen sohbetler ve eşleşen satır döner."""
    with _lock:
        items = sorted(_read(), key=lambda i: i.get("ts", 0))
    groups: list[list[dict]] = []
    for it in items:
        if groups and it.get("ts", 0) - groups[-1][-1].get("ts", 0) <= gap:
            groups[-1].append(it)
        else:
            groups.append([it])
    nq = _norm(q.strip()) if q else ""
    now = time.time()
    out = []
    for g in groups:
        hit = next((m for m in g if nq in _norm(m.get("text", ""))), None) if nq else None
        if nq and not hit:
            continue
        first_user = next((m for m in g if m.get("who") == "sen"), g[0])
        title = " ".join(first_user.get("text", "").split())
        out.append({"id": g[0]["id"], "start": g[0]["ts"], "end": g[-1]["ts"], "count": len(g),
                    "title": title if len(title) <= 70 else title[:67] + "…",
                    "snippet": " ".join(hit["text"].split())[:140] if hit else "",
                    "live": now - g[-1]["ts"] <= gap})
    return out[::-1]


def between(start: float, end: float) -> list[dict]:
    """[start, end] aralığındaki satırlar (eskiden yeniye)."""
    with _lock:
        return sorted((i for i in _read() if start - 0.001 <= i.get("ts", 0) <= end + 0.001), key=lambda i: i.get("ts", 0))


def delete_between(start: float, end: float) -> int:
    with _lock:
        items = _read()
        keep = [i for i in items if not (start - 0.001 <= i.get("ts", 0) <= end + 0.001)]
        if len(keep) != len(items):
            _write(keep)
        return len(items) - len(keep)


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
