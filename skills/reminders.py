"""Hatırlatıcı / zamanlayıcı. Süre dolunca main.py'nin verdiği bildirici sesli söyler."""
import datetime as dt
import subprocess
import threading

_lock = threading.Lock()
_active: list[dict] = []   # {"id", "when", "message", "timer"}
_next_id = 1
_notifier = None           # callable(str); main.py seslendirme için kaydeder


def set_notifier(fn) -> None:
    global _notifier
    _notifier = fn


def _fire(rid: int) -> None:
    with _lock:
        item = next((r for r in _active if r["id"] == rid), None)
        if item:
            _active.remove(item)
    if not item:
        return
    text = f"Hatırlatma: {item['message']}" if item["message"] else "Süre doldu."
    print(f"\n[hatırlatıcı] {text}", flush=True)
    try:
        subprocess.Popen(["notify-send", "Jarvis", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
    if _notifier:
        _notifier(text)


def _duration_text(sec: float) -> str:
    sec = int(round(sec))
    if sec < 60:
        return f"{sec} saniye"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m} dakika" + (f" {s} saniye" if s else "")
    h, m = divmod(m, 60)
    return f"{h} saat" + (f" {m} dakika" if m else "")


def set_reminder(minutes: float = 0, at: str = "", message: str = "") -> str:
    global _next_id
    now = dt.datetime.now()
    if at:
        try:
            hh, mm = (int(x) for x in at.replace(".", ":").split(":")[:2])
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except ValueError:
            return "Hata: saat biçimi anlaşılamadı (SS:DD olmalı)."
        if target <= now:
            target += dt.timedelta(days=1)
        delay = (target - now).total_seconds()
    else:
        try:
            delay = float(minutes) * 60
        except (TypeError, ValueError):
            return "Hata: süre anlaşılamadı."
    if delay < 1 or delay > 7 * 24 * 3600:
        return "Hata: süre 1 saniye ile 7 gün arasında olmalı."
    with _lock:
        rid = _next_id
        _next_id += 1
        timer = threading.Timer(delay, _fire, args=(rid,))
        timer.daemon = True
        _active.append({"id": rid, "when": now + dt.timedelta(seconds=delay), "message": (message or "").strip(), "timer": timer})
    timer.start()
    return f"Tamam, {_duration_text(delay)} sonra hatırlatacağım."


def list_reminders() -> str:
    with _lock:
        items = sorted(_active, key=lambda r: r["when"])
    if not items:
        return "Kurulu hatırlatıcı yok."
    now = dt.datetime.now()
    parts = [f"{_duration_text((r['when'] - now).total_seconds())} sonra" + (f": {r['message']}" if r["message"] else "") for r in items]
    return f"{len(items)} hatırlatıcı var. " + ". ".join(parts) + "."


def cancel_reminders() -> str:
    with _lock:
        n = len(_active)
        for r in _active:
            r["timer"].cancel()
        _active.clear()
    return f"{n} hatırlatıcıyı iptal ettim." if n else "İptal edilecek hatırlatıcı yok."


SKILLS = [
    {
        "name": "set_reminder",
        "description": "Belirli bir süre sonra veya belirli bir saatte hatırlatma kurar. 'Yirmi dakika sonra hatırlat', 'zamanlayıcı kur', 'saat beşte uyar' denince kullanılır.",
        "parameters": {"type": "object", "properties": {
            "minutes": {"type": "number", "description": "Kaç dakika sonra (ör. 20; yarım saat = 30; 90 saniye = 1.5)"},
            "at": {"type": "string", "description": "Belirli saat için SS:DD (ör. 17:30). Süre verildiyse boş bırak"},
            "message": {"type": "string", "description": "Hatırlatılacak şey (ör. 'ekmeği çıkar'); yoksa boş"}}},
        "run": set_reminder,
    },
    {
        "name": "list_reminders",
        "description": "Kurulu hatırlatıcıları ve zamanlayıcıları listeler.",
        "run": list_reminders,
    },
    {
        "name": "cancel_reminders",
        "description": "Kurulu tüm hatırlatıcıları ve zamanlayıcıları iptal eder.",
        "run": cancel_reminders,
    },
]
