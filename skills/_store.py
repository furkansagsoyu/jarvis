"""Kalıcı veri klasörü (data/). İçindeki .gitignore her şeyi git dışında tutar."""
import json
import os
import tempfile
from pathlib import Path

DATA_DIR = Path(os.environ.get("JARVIS_DATA", Path(__file__).resolve().parent.parent / "data"))


_secured = False


def _secure_dir() -> None:
    """data/ yalnızca sahibine açık (içinde Telegram/Groq/Firebase anahtarları, pano adresi, telefon sırrı var)."""
    global _secured
    if _secured:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    _secured = True


def runtime_path(name: str) -> Path:
    """Kilit/pid dosyaları için kullanıcıya özel klasör: $XDG_RUNTIME_DIR (0700), yoksa /tmp/jarvis-<uid> (0700).
    /tmp'de sabit adlı dosya başka bir yerel kullanıcının önceden oluşturup engelleyebileceği/yönlendirebileceği bir yoldur."""
    base = os.environ.get("XDG_RUNTIME_DIR", "")
    if base and os.path.isdir(base) and os.access(base, os.W_OK):
        return Path(base) / name
    d = Path(tempfile.gettempdir()) / f"jarvis-{os.getuid()}"
    d.mkdir(mode=0o700, exist_ok=True)
    st = d.stat()
    if st.st_uid != os.getuid():
        raise PermissionError(f"{d} başka bir kullanıcıya ait; kilit dosyası güvenli değil")
    if st.st_mode & 0o077:
        d.chmod(0o700)
    return d / name


def path(name: str) -> Path:
    _secure_dir()
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
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # sır içerebilir: yalnızca sahibi okur
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(p)  # yarım yazılmış dosya kalmasın
