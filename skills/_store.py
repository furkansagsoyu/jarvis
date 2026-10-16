"""Kalıcı veri klasörü (data/). İçindeki .gitignore her şeyi git dışında tutar."""
import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("JARVIS_DATA", Path(__file__).resolve().parent.parent / "data"))


def path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ignore = DATA_DIR / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")  # kişisel veriler asla commit edilmesin
    return DATA_DIR / name


def load(name: str, default):
    try:
        return json.loads(path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(name: str, obj) -> None:
    p = path(name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)  # yarım yazılmış dosya kalmasın
