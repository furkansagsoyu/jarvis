"""Zamanlanmış görevler: kurma (onaylı), listeleme, silme. Çalıştırma core/scheduler.py + main.py'de (kısıtlı kip).

Araçlar gizli; yalnızca açık cümleyle hızlı yoldan çağrılır ("her gün 9'da hava nasıl", "zamanlanmış görevler",
"zamanlanmış görevi sil 2"). Model kendi başına görev kuramaz; kurmak her zaman sesli onay ister. Uzaktan kapalı.
"""
from __future__ import annotations

from core import scheduler as S

from . import _confirm as confirm


def schedule_add(text: str) -> str:
    spec = S.parse(text)
    if isinstance(spec, str):
        return spec
    if len(S.load()) >= S.MAX_JOBS:
        return f"En fazla {S.MAX_JOBS} zamanlanmış görev olabilir; önce birini sil."
    desc = S.describe(spec)

    def run() -> str:
        job = S.add(spec)
        return f"Kurdum: {job['id']} numaralı görev, {desc}."
    return confirm.request(f"Zamanlanmış görev kurulacak: {desc}. Zamanı gelince bilgisayarın başında olmasan da kısıtlı kipte çalışır.", run)


def schedule_list() -> str:
    jobs = S.load()
    if not jobs:
        return "Zamanlanmış görev yok. Örnek: “her gün 9'da hava nasıl”."
    return "Zamanlanmış görevler. " + " ".join(f"{j['id']}: {S.describe(j)}." for j in jobs)


def schedule_delete(number: int | str = 0) -> str:
    try:
        n = int(str(number).strip())
    except ValueError:
        return "Hangi numaralı görevi sileceğimi anlamadım."
    hit = S.remove(n)
    return f"{n} numaralı zamanlanmış görevi sildim: {S.describe(hit)}." if hit else f"{n} numaralı zamanlanmış görev yok."


SKILLS = [
    {"name": "schedule_add", "description": "Tekrarlayan zamanlanmış görev kurar (onaylı).", "hidden": True, "run": schedule_add,
     "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "her gün 9'da: hava nasıl"}}, "required": ["text"]}},
    {"name": "schedule_list", "description": "Zamanlanmış görevleri listeler.", "hidden": True, "run": schedule_list,
     "parameters": {"type": "object", "properties": {}}},
    {"name": "schedule_delete", "description": "Numarasıyla zamanlanmış görevi siler.", "hidden": True, "run": schedule_delete,
     "parameters": {"type": "object", "properties": {"number": {"type": "integer", "description": "görev numarası"}}, "required": ["number"]}},
]
