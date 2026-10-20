"""Takvim ve görevler (yerel, data/agenda.json). Hepsi "hidden": kural tabanlı hızlı yoldan (route) çağrılır.

Örnek cümleler:
  "yarın saat 14'te toplantı ekle", "takvime cuma akşam 8'de yemek koy", "bu hafta takvimimde ne var", "yarın ne var"
  "görev ekle: raporu bitir, cuma, yüksek öncelik", "görevlerim neler", "raporu bitir görevi bitti", "geciken görevler"
  "toplantı etkinliğini sil" (silme sesli onay ister)
Etkinlikten 10 dakika önce Jarvis sesli uyarır (Monitor); sabah özetine bugünün etkinlikleri ve görevleri girer.
"""
import datetime as dt
import re
import subprocess
import threading
import time

from . import _confirm, _store
from ._trdate import AYLAR, GUNLER, capitalize, lower, parse_when

FILE = "agenda.json"
PRIORITIES = ("yüksek", "orta", "düşük")
REMIND_MIN = 10
_lock = threading.RLock()
_GUN_AD = ["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"]
_AY_AD = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


# ------------------------------------------------------------------ depo
def _load() -> dict:
    d = _store.load(FILE, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("events", [])
    d.setdefault("tasks", [])
    d.setdefault("next", 1)
    return d


def _save(d: dict) -> None:
    _store.save(FILE, d)


def _new_id(d: dict) -> int:
    n = d["next"]
    d["next"] = n + 1
    return n


def _now() -> dt.datetime:
    return dt.datetime.now()


# ------------------------------------------------------------------ konuşma biçimi
def _day_text(day: dt.date, today: dt.date | None = None) -> str:
    today = today or _now().date()
    delta = (day - today).days
    if delta == 0:
        return "bugün"
    if delta == 1:
        return "yarın"
    name = _GUN_AD[day.weekday()]
    if 1 < delta < 7:
        return name
    return f"{day.day} {_AY_AD[day.month - 1]} {name}"


def _time_text(t: dt.time) -> str:
    return f"{t.hour:02d}.{t.minute:02d}"


def _ev_start(e: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(e["start"])


def _ev_line(e: dict) -> str:
    s = _ev_start(e)
    return e["title"] if e.get("all_day") else f"saat {_time_text(s.time())} {e['title']}"


def _find(items: list[dict], query: str) -> list[dict]:
    q = lower(query).strip()
    if not q:
        return []
    words = [w for w in re.split(r"\W+", q) if len(w) >= 3]
    exact = [i for i in items if q in lower(i["title"])]
    if exact:
        return exact
    # "raporu" -> "rapor": ek yutan kaba eşleşme (kelime başlangıcı)
    return [i for i in items if words and all(any(tw.startswith(w[:max(3, len(w) - 2)]) or w.startswith(tw[:max(3, len(tw) - 2)])
                                                  for tw in re.split(r"\W+", lower(i["title"])) if tw) for w in words)]


# ------------------------------------------------------------------ etkinlikler
def add_event(title: str = "", date: str = "", time_: str = "", duration: int = 0, remind: int = REMIND_MIN) -> str:
    title = capitalize((title or "").strip()) or "Etkinlik"
    now = _now()
    try:
        day = dt.date.fromisoformat(date) if date else None
        at = dt.time.fromisoformat(time_) if time_ else None
    except ValueError:
        return "Hata: tarih ya da saat anlaşılamadı."
    if day is None and at is None:
        return "Ne zaman olduğunu anlayamadım. Örnek: yarın saat 14'te toplantı ekle."
    if day is None:
        day = now.date() if dt.datetime.combine(now.date(), at) > now else now.date() + dt.timedelta(days=1)
    start = dt.datetime.combine(day, at or dt.time(0, 0))
    if at and start < now - dt.timedelta(minutes=1):
        return "Bu saat geçmiş görünüyor. Başka bir zaman söyler misin?"
    with _lock:
        d = _load()
        clash = [e for e in d["events"] if not e.get("all_day") and at and abs((_ev_start(e) - start).total_seconds()) < 1800]
        ev = {"id": _new_id(d), "title": title, "start": start.isoformat(timespec="minutes"), "all_day": at is None,
              "duration": int(duration or 0), "remind": int(remind), "notified": False}
        d["events"].append(ev)
        _save(d)
    text = f"Tamam, {_day_text(day)} " + (f"saat {_time_text(at)} " if at else "") + f"{title} takvime eklendi."
    if clash:
        text += f" Dikkat, aynı saate yakın {clash[0]['title']} etkinliği var."
    return text


def _range(which: str, now: dt.datetime) -> tuple[dt.date, dt.date, str]:
    today = now.date()
    which = (which or "upcoming").lower()
    if which == "today":
        return today, today, "Bugün"
    if which == "tomorrow":
        return today + dt.timedelta(days=1), today + dt.timedelta(days=1), "Yarın"
    if which == "week":
        return today, today + dt.timedelta(days=6), "Bu hafta"
    try:
        d = dt.date.fromisoformat(which)
        return d, d, _day_text(d).capitalize()
    except ValueError:
        return today, today + dt.timedelta(days=6), "Önümüzdeki yedi gün"


def list_events(range: str = "upcoming") -> str:  # noqa: A002
    now = _now()
    a, b, label = _range(range, now)
    with _lock:
        evs = [e for e in _load()["events"] if a <= _ev_start(e).date() <= b
               and (_ev_start(e) >= now - dt.timedelta(minutes=max(e.get("duration") or 0, 1)) or e.get("all_day") and _ev_start(e).date() >= now.date())]
    evs.sort(key=_ev_start)
    if not evs:
        return f"{label} takvimde etkinlik yok."
    by_day: dict[dt.date, list[dict]] = {}
    for e in evs:
        by_day.setdefault(_ev_start(e).date(), []).append(e)
    parts, shown = [], 0
    for day, items in by_day.items():
        if shown >= 6:
            break
        take = items[: 6 - shown]
        shown += len(take)
        parts.append(f"{_day_text(day).capitalize()}: " + ", ".join(_ev_line(e) for e in take) + ".")
    more = len(evs) - shown
    head = f"{label} {len(evs)} etkinlik var. "
    return head + " ".join(parts) + (f" Ve {more} tane daha." if more > 0 else "")


def cancel_event(query: str = "") -> str:
    with _lock:
        d = _load()
        upcoming = [e for e in d["events"] if _ev_start(e) >= _now() - dt.timedelta(days=1)]
        hits = _find(upcoming, query)
    if not hits:
        return f"'{query}' adında bir etkinlik bulamadım." if query else "Hangi etkinliği sileceğimi anlamadım."
    if len(hits) > 1:
        return f"{len(hits)} etkinlik eşleşti: " + ", ".join(f"{_day_text(_ev_start(e).date())} {e['title']}" for e in hits[:4]) + ". Hangisi?"
    ev = hits[0]

    def run():
        with _lock:
            dd = _load()
            dd["events"] = [e for e in dd["events"] if e["id"] != ev["id"]]
            _save(dd)
        return f"{ev['title']} etkinliğini sildim."
    return _confirm.request(f"{_day_text(_ev_start(ev).date())} {ev['title']} etkinliği silinecek.", run)


# ------------------------------------------------------------------ görevler
def add_task(title: str = "", due: str = "", priority: str = "orta") -> str:
    title = capitalize((title or "").strip())
    if not title:
        return "Görevin ne olduğunu anlayamadım."
    priority = priority if priority in PRIORITIES else "orta"
    try:
        day = dt.date.fromisoformat(due) if due else None
    except ValueError:
        return "Hata: bitiş tarihi anlaşılamadı."
    with _lock:
        d = _load()
        d["tasks"].append({"id": _new_id(d), "title": title, "due": day.isoformat() if day else "", "priority": priority,
                           "status": "açık", "created": _now().isoformat(timespec="minutes")})
        _save(d)
    extra = (f", bitiş {_day_text(day)}" if day else "") + (f", öncelik {priority}" if priority != "orta" else "")
    return f"Görev eklendi: {title}{extra}."


def _open_tasks(d: dict) -> list[dict]:
    rank = {p: i for i, p in enumerate(PRIORITIES)}
    return sorted((t for t in d["tasks"] if t["status"] == "açık"),
                  key=lambda t: (t["due"] or "9999-99-99", rank.get(t["priority"], 1)))


def list_tasks(filter: str = "open") -> str:  # noqa: A002
    today = _now().date()
    with _lock:
        tasks = _open_tasks(_load())
    if filter == "overdue":
        tasks = [t for t in tasks if t["due"] and dt.date.fromisoformat(t["due"]) < today]
        empty = "Geciken görev yok."
    elif filter == "today":
        tasks = [t for t in tasks if t["due"] and dt.date.fromisoformat(t["due"]) <= today]
        empty = "Bugün bitmesi gereken görev yok."
    else:
        empty = "Açık görev yok."
    if not tasks:
        return empty
    parts = []
    for t in tasks[:6]:
        s = t["title"]
        if t["due"]:
            dd = dt.date.fromisoformat(t["due"])
            s += f", {'gecikmiş' if dd < today else _day_text(dd)}"
        if t["priority"] == "yüksek":
            s += ", öncelikli"
        parts.append(s)
    more = len(tasks) - len(parts)
    return f"{len(tasks)} açık görev var. " + ". ".join(parts) + "." + (f" Ve {more} tane daha." if more > 0 else "")


def done_task(query: str = "") -> str:
    with _lock:
        d = _load()
        hits = _find(_open_tasks(d), query)
        if not hits:
            return f"'{query}' adında açık bir görev bulamadım." if query else "Hangi görev bitti anlamadım."
        if len(hits) > 1:
            return f"{len(hits)} görev eşleşti: " + ", ".join(t["title"] for t in hits[:4]) + ". Hangisi?"
        for t in d["tasks"]:
            if t["id"] == hits[0]["id"]:
                t["status"] = "bitti"
                t["done"] = _now().isoformat(timespec="minutes")
        _save(d)
    left = len(_open_tasks(d))
    return f"Tamam, {hits[0]['title']} görevi bitti." + (f" {left} açık görev kaldı." if left else " Açık görev kalmadı.")


def delete_task(query: str = "") -> str:
    with _lock:
        hits = _find(_open_tasks(_load()), query)
    if not hits:
        return f"'{query}' adında açık bir görev bulamadım."
    if len(hits) > 1:
        return f"{len(hits)} görev eşleşti: " + ", ".join(t["title"] for t in hits[:4]) + ". Hangisi?"
    task = hits[0]

    def run():
        with _lock:
            d = _load()
            d["tasks"] = [t for t in d["tasks"] if t["id"] != task["id"]]
            _save(d)
        return f"{task['title']} görevini sildim."
    return _confirm.request(f"{task['title']} görevi silinecek.", run)


# ------------------------------------------------------------------ sabah özeti
def brief_text() -> str:
    today = _now().date()
    parts = []
    with _lock:
        d = _load()
    evs = sorted((e for e in d["events"] if _ev_start(e).date() == today), key=_ev_start)
    if evs:
        parts.append(f"Bugün {len(evs)} etkinlik var: " + ", ".join(_ev_line(e) for e in evs[:4]) + ".")
    tasks = _open_tasks(d)
    overdue = [t for t in tasks if t["due"] and dt.date.fromisoformat(t["due"]) < today]
    due = [t for t in tasks if t["due"] and dt.date.fromisoformat(t["due"]) == today]
    if due:
        parts.append("Bugün bitmesi gereken görev: " + ", ".join(t["title"] for t in due[:3]) + ".")
    if overdue:
        parts.append(f"{len(overdue)} görevin süresi geçmiş.")
    return " ".join(parts)


def counts() -> dict:
    """Pano için: açık görev, geciken görev ve bugünkü etkinlik sayıları."""
    today = _now().date()
    with _lock:
        d = _load()
    tasks = _open_tasks(d)
    return {"open_tasks": len(tasks),
            "overdue": sum(1 for t in tasks if t["due"] and dt.date.fromisoformat(t["due"]) < today),
            "events_today": sum(1 for e in d["events"] if _ev_start(e).date() == today)}


def snapshot(max_tasks: int = 6, horizon_days: int = 60) -> dict:
    """Pano için ham veri: bugünkü etkinlikler, yaklaşan etkinlikler (kimlikli) ve açık görevler (kimlikli)."""
    now = _now()
    today = now.date()
    with _lock:
        d = _load()
    evs = sorted(d["events"], key=_ev_start)
    todays = [{"time": "" if e.get("all_day") else _ev_start(e).strftime("%H:%M"), "title": e["title"],
               "past": (not e.get("all_day")) and _ev_start(e) < now} for e in evs if _ev_start(e).date() == today]
    end = today + dt.timedelta(days=horizon_days)
    upcoming = [{"id": e["id"], "date": _ev_start(e).date().isoformat(), "time": "" if e.get("all_day") else _ev_start(e).strftime("%H:%M"),
                 "title": e["title"], "past": (not e.get("all_day")) and _ev_start(e) < now}
                for e in evs if today <= _ev_start(e).date() <= end]
    nxt = next(({"when": _ev_start(e).strftime("%d.%m %H:%M") if not e.get("all_day") else _ev_start(e).strftime("%d.%m"),
                 "title": e["title"]} for e in evs if _ev_start(e) >= now.replace(hour=0, minute=0) and
                (e.get("all_day") or _ev_start(e) >= now)), None)
    tasks = [{"id": t["id"], "title": t["title"], "due": t["due"], "priority": t["priority"],
              "overdue": bool(t["due"]) and dt.date.fromisoformat(t["due"]) < today}
             for t in _open_tasks(d)]
    return {"events_today": todays, "events": upcoming, "next_event": nxt, "tasks": tasks[:max_tasks], "all_tasks": tasks[:100],
            "open_tasks": len(tasks), "overdue": sum(1 for t in tasks if t["overdue"])}


# ------------------------------------------------------------------ kimlikle işlemler (pano düğmeleri)
def done_task_id(task_id: int) -> bool:
    with _lock:
        d = _load()
        for t in d["tasks"]:
            if t["id"] == task_id and t["status"] == "açık":
                t["status"] = "bitti"
                _save(d)
                return True
    return False


def delete_task_id(task_id: int) -> bool:
    with _lock:
        d = _load()
        keep = [t for t in d["tasks"] if t["id"] != task_id]
        if len(keep) == len(d["tasks"]):
            return False
        d["tasks"] = keep
        _save(d)
        return True


def cancel_event_id(event_id: int) -> bool:
    with _lock:
        d = _load()
        keep = [e for e in d["events"] if e["id"] != event_id]
        if len(keep) == len(d["events"]):
            return False
        d["events"] = keep
        _save(d)
        return True


# ------------------------------------------------------------------ uyarı iş parçacığı
class Monitor(threading.Thread):
    """Etkinliğe 'remind' dakika kala bir kez sesli uyarır ve masaüstü bildirimi gösterir."""

    def __init__(self, say, interval: int = 30):
        super().__init__(daemon=True)
        self.say, self.interval = say, interval

    def check(self, now: dt.datetime | None = None) -> list[str]:
        now = now or _now()
        said = []
        with _lock:
            d = _load()
            for e in d["events"]:
                if e.get("all_day") or e.get("notified"):
                    continue
                left = (_ev_start(e) - now).total_seconds() / 60
                if -2 <= left <= e.get("remind", REMIND_MIN):
                    e["notified"] = True
                    mins = max(int(round(left)), 0)
                    said.append(f"{mins} dakika sonra {e['title']}." if mins > 0 else f"Şimdi {e['title']} zamanı.")
            if said:
                _save(d)
        for text in said:
            print(f"\n[takvim] {text}", flush=True)
            try:
                subprocess.Popen(["notify-send", "Jarvis", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
            self.say(text)
        return said

    def run(self):
        while True:
            try:
                self.check()
            except Exception as exc:  # noqa: BLE001
                print(f"[uyarı] takvim izleyici: {type(exc).__name__}", flush=True)
            time.sleep(self.interval)


# ------------------------------------------------------------------ hızlı yol
_NOT_AGENDA = re.compile(r"hatırlat|alarm|zamanlayıcı|sayaç|ekran|kamera|hava\b|pil\b|şarj", re.I)
_EV_WORDS = r"(?:etkinlik|toplantı|randevu|sınav|vize|final|ders|buluşma|maç|konser|proje teslim\w*|sunum)"
TASK_ADD = [
    re.compile(r"^(?:yeni\s+)?görev\w*\s+(?:ekle|koy|yaz|oluştur|kaydet)\w*\W+(?P<r>.+)$"),
    re.compile(r"^(?:yeni\s+görev|görev|yapılacak)\s*[:,\-]\s*(?P<r>.+)$"),
    re.compile(r"^(?P<r>.+?)\s+(?:görevlerime|görev listeme|yapılacaklar listeme|yapılacaklara|görev olarak|göreve)\s*(?:ekle|koy|yaz)\w*$"),
]
TASK_LIST = re.compile(r"\bgörev\w*\s*(?:neler|ne|listem\w*|listesi|var mı|göster\w*|oku\w*|söyle\w*)|\bgörevlerim\b|\bgecik\w*\s+görev\w*|\bgörev\w*\s+gecik\w*|\byapılacak\w*|\bne yapmam (?:lazım|gerek)")
TASK_DONE = re.compile(r"^(?:(?P<a>.+?)\s+görev\w*\s+(?:bitti|tamamlandı|tamamladım|bitirdim|yapıldı|tamam)|görev\w*\s+(?:tamamla|bitir)\w*\W+(?P<b>.+))$")
TASK_DEL = re.compile(r"^(?:(?P<a>.+?)\s+görev\w*\s+(?:sil|kaldır|iptal et)\w*|görev\w*\s+(?:sil|kaldır|iptal et)\w*\W+(?P<b>.+))$")
EV_DEL = re.compile(rf"^(?P<a>.+?)\s+(?:etkinli\w*|toplantı\w*|randevu\w*|sınav\w*|buluşma\w*)\s+(?:sil|kaldır|iptal et)\w*$")
EV_ADD_VERB = re.compile(r"\b(?:ekle|koy|kaydet|yaz|planla|oluştur)\w*\b")
EV_LIST = re.compile(rf"\bne var\b|\bne yapıyorum\b|\bnerede\b|\bneler var\b|\bvar mı\b|\bnelerim var\b|\bprogramım\b|\bplanım\b|takvim\w*\s*(?:göster|oku|söyle|ne)|{_EV_WORDS}\w*\s*(?:neler|ne|var mı)|\b{_EV_WORDS}lerim\b|\b{_EV_WORDS}larım\b")
EV_NOUN = re.compile(rf"takvim|{_EV_WORDS}\w*|programım|planım|ne var|neler var")


def _priority(t: str) -> tuple[str, str]:
    pr = "orta"
    if re.search(r"\b(yüksek|önemli|acil)\b(?:\s+öncelik\w*)?", t):
        pr = "yüksek"
    elif re.search(r"\b(düşük|önemsiz)\b(?:\s+öncelik\w*)?", t):
        pr = "düşük"
    t = re.sub(r"\b(yüksek|önemli|acil|düşük|önemsiz)\b(?:\s+öncelik\w*)?|\böncelik\w*", " ", t)
    return pr, t


def route(text: str) -> list[tuple[str, dict]]:
    """(araç, argümanlar) listesi; eşleşme yoksa boş. Brain._fast_route çağırır."""
    raw = (text or "").strip().rstrip(".!?").strip()
    t = lower(raw)
    if not t or _NOT_AGENDA.search(t):
        return []
    now = _now()

    for rx in TASK_ADD:
        m = rx.match(t)
        if m:
            r = raw[m.start("r"):m.end("r")]
            pr = _priority(lower(r))[0]
            r = re.sub(r"\b(yüksek|önemli|acil|düşük|önemsiz)\b(?:\s+öncelik\w*)?|\böncelik\w*", " ", r, flags=re.I)
            w = parse_when(r, now)
            return [("task_add", {"title": w.rest, "due": w.date.isoformat() if w.date else "", "priority": pr})]
    m = TASK_DONE.match(t)
    if m:
        a, b = m.group("a"), m.group("b")
        return [("task_done", {"query": (a or b).strip()})]
    m = TASK_DEL.match(t)
    if m:
        return [("task_delete", {"query": (m.group("a") or m.group("b")).strip()})]
    if TASK_LIST.search(t):
        return [("task_list", {"filter": "overdue" if re.search(r"gecik|süresi geç", t) else "today" if re.search(r"bugün", t) else "open"})]

    m = EV_DEL.match(t)
    if m:
        return [("agenda_cancel", {"query": m.group("a").strip()})]

    w = parse_when(raw, now)
    has_when = w.date is not None or w.time is not None
    if EV_ADD_VERB.search(t) and has_when and (re.search(r"takvim", t) or re.search(_EV_WORDS, t) or w.time):
        if "takvim" in t or re.search(_EV_WORDS, t):
            return [("agenda_add", {"title": w.rest, "date": w.date.isoformat() if w.date else "",
                                    "time_": w.time.strftime("%H:%M") if w.time else "", "duration": w.duration or 0})]
    if EV_ADD_VERB.search(t) and (re.search(r"takvim", t) or re.search(rf"\b{_EV_WORDS}\b", t)):  # zaman yok -> yardım cümlesi
        return [("agenda_add", {"title": w.rest, "date": "", "time_": ""})]
    if EV_LIST.search(t) and EV_NOUN.search(t) or (EV_LIST.search(t) and has_when and not re.search(r"ekran|kamera", t)):
        which = "upcoming"
        if re.search(r"bu hafta|haftalık|hafta", t) and w.date is None:
            which = "week"
        elif w.date == now.date():
            which = "today"
        elif w.date == now.date() + dt.timedelta(days=1):
            which = "tomorrow"
        elif w.date is not None:
            which = w.date.isoformat()
        return [("agenda_list", {"range": which})]
    return []


SKILLS = [
    {"name": "agenda_add", "hidden": True, "run": add_event,
     "description": "Takvime etkinlik ekler. 'Yarın saat 14'te toplantı ekle' denince kullanılır.",
     "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
                                                     "time_": {"type": "string", "description": "SS:DD"}, "duration": {"type": "integer"}}, "required": ["title"]}},
    {"name": "agenda_list", "hidden": True, "run": list_events,
     "description": "Takvimdeki etkinlikleri okur (bugün, yarın, bu hafta).",
     "parameters": {"type": "object", "properties": {"range": {"type": "string"}}}},
    {"name": "agenda_cancel", "hidden": True, "run": cancel_event,
     "description": "Bir etkinliği siler (onay ister).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "task_add", "hidden": True, "run": add_task,
     "description": "Göreve ekler: başlık, bitiş tarihi, öncelik.",
     "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "due": {"type": "string"}, "priority": {"type": "string"}}, "required": ["title"]}},
    {"name": "task_list", "hidden": True, "run": list_tasks,
     "description": "Açık görevleri okur.", "parameters": {"type": "object", "properties": {"filter": {"type": "string"}}}},
    {"name": "task_done", "hidden": True, "run": done_task,
     "description": "Bir görevi bitmiş işaretler.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "task_delete", "hidden": True, "run": delete_task,
     "description": "Bir görevi siler (onay ister).", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]
