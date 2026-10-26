"""Zamanlanmış (tekrarlayan) görevler: "her gün 9'da: hava nasıl", "hafta içi her gün 8:30'da günün özeti", "her cuma 17'de görevlerim".

Görev = kullanıcının kendi cümlesi + gün/saat. Zamanı gelince Jarvis o cümleyi **kısıtlı kipte** (Telegram ile aynı: dosya, tarayıcı,
fare/klavye, kod, telefon araması, MCP… kapalı; bilgisayarda bekleyen onay verilemez) çalıştırır ve sonucu bildirir (odak modunda
yalnızca panoya). Kurmak onay ister (skills/schedule.py). Bilgisayar kapalıyken kaçırılanlar sonradan topluca çalıştırılmaz:
yalnızca WINDOW sn gecikme tanınır. Kayıt: data/schedules.json.
"""
from __future__ import annotations

import datetime as dt
import re
import threading

from skills import _store

FILE = "schedules.json"
WINDOW = 600          # sn: zamanından en fazla bu kadar geç kalmış görev yine çalışır (açılış/meşguliyet)
TICK = 20             # sn: kontrol sıklığı
MAX_JOBS = 30
DAYS = ["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"]
EVERY = list(range(7))
_DAY_RX = "|".join(DAYS)
SPEC = re.compile(
    rf"^\W*(?P<when>her\s+(?:gün|sabah|akşam|gece|öğlen?)|hafta\s+içi(?:\s+her\s+gün)?|hafta\s+sonu(?:\s+her\s+gün)?|her\s+(?P<day>{_DAY_RX})(?:\s+(?:günü|sabah|akşam))?)"
    r"\s+(?:saat\s+)?(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?(?:['’]?(?:te|ta|de|da|'de|'da))?\s*[:,\-–]?\s*(?P<cmd>.+)$", re.I | re.S)
# zamanlanamaz: onay ya da plan gerektiren başlatmalar (gözetimsizken kimse "evet" diyemez) ve iç içe zamanlama
NOT_SCHEDULABLE = re.compile(r"^\W*(?:ajan\b|görev\s*:|ekip\b|araştır\b|kod\b|kod\s*:|proje\s*:|mimar\b|mcp\s*:)|\bher\s+(?:gün|sabah|akşam|hafta)", re.I)


def _lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def parse(text: str) -> dict | str:
    """'her gün 9'da: hava nasıl' -> {"days", "hh", "mm", "cmd"}; anlaşılamazsa açıklayıcı cümle (str)."""
    m = SPEC.match((text or "").strip())
    if not m:
        return "Zamanlamayı anlayamadım. Örnek: “her gün 9'da hava nasıl” ya da “her cuma 17:30'da görevlerim”."
    when, day = _lower(m.group("when")), m.group("day")
    hh, mm = int(m.group("h")), int(m.group("m") or 0)
    if when.startswith("hafta içi"):
        days = [0, 1, 2, 3, 4]
    elif when.startswith("hafta sonu"):
        days = [5, 6]
    elif day:
        days = [DAYS.index(_lower(day))]
    else:
        days = list(EVERY)
    if ("akşam" in when or "gece" in when) and 1 <= hh <= 11:
        hh += 12
    if "öğle" in when and 1 <= hh <= 5:
        hh += 12
    cmd = " ".join(m.group("cmd").split()).strip(" .")
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return "Saat geçersiz."
    if len(cmd) < 3:
        return "Ne yapacağımı söylemedin."
    if NOT_SCHEDULABLE.search(cmd):
        return "Bunu zamanlayamam: ajan, ekip, kod ve MCP görevleri onay ister, gözetimsiz çalışamaz."
    return {"days": days, "hh": hh, "mm": mm, "cmd": cmd[:200]}


def describe(job: dict) -> str:
    d = job["days"]
    when = ("her gün" if d == EVERY else "hafta içi her gün" if d == [0, 1, 2, 3, 4] else "hafta sonu" if d == [5, 6]
            else "her " + ", ".join(DAYS[i] for i in d))
    return f"{when} {job['hh']:02d}:{job['mm']:02d}: {job['cmd']}"


def load() -> list[dict]:
    jobs = _store.load(FILE, [])
    return [j for j in jobs if isinstance(j, dict) and {"id", "days", "hh", "mm", "cmd"} <= set(j)] if isinstance(jobs, list) else []


def save(jobs: list[dict]) -> None:
    _store.save(FILE, jobs[:MAX_JOBS])


def add(spec: dict) -> dict:
    jobs = load()
    job = {"id": max((j["id"] for j in jobs), default=0) + 1, **spec, "last": ""}
    save([*jobs, job])
    return job


def remove(job_id: int) -> dict | None:
    jobs = load()
    hit = next((j for j in jobs if j["id"] == job_id), None)
    if hit:
        save([j for j in jobs if j["id"] != job_id])
    return hit


def due(job: dict, now: dt.datetime, window: float = WINDOW) -> bool:
    """Bugün çalışma günü mü, saati geçti mi (en fazla window sn önce), bugün çalıştı mı?"""
    if now.weekday() not in job["days"]:
        return False
    at = now.replace(hour=job["hh"], minute=job["mm"], second=0, microsecond=0)
    late = (now - at).total_seconds()
    return 0 <= late <= window and job.get("last") != now.date().isoformat()


class Scheduler:
    """Arka plan iş parçacığı: TICK sn'de bir zamanı gelen görevleri run(job) ile çalıştırır.
    run False dönerse (ör. bilgisayarda onay bekliyor, beyin meşgul) görev pencere içinde sonra yeniden denenir."""

    def __init__(self, run, clock=dt.datetime.now):
        self.run, self.clock = run, clock
        self._stop = threading.Event()

    def tick(self) -> list[int]:
        now = self.clock()
        done = []
        for job in load():
            if not due(job, now):
                continue
            try:
                ok = self.run(job) is not False
            except Exception as exc:  # noqa: BLE001  (bir görevin hatası zamanlayıcıyı öldürmesin)
                print(f"[zamanlayıcı] görev {job['id']} hata: {type(exc).__name__}", flush=True)
                ok = True                     # aynı gün tekrar tekrar denenmesin
            if ok:
                jobs = load()
                for j in jobs:
                    if j["id"] == job["id"]:
                        j["last"] = now.date().isoformat()
                save(jobs)
                done.append(job["id"])
        return done

    def start(self) -> None:
        def loop():
            while not self._stop.wait(TICK):
                self.tick()
        threading.Thread(target=loop, daemon=True, name="zamanlayici").start()

    def stop(self) -> None:
        self._stop.set()

