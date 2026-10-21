"""Kod ajanı araçları (yalnızca Ekip modunun Kod Ajanı rolü kullanır; sesli modelin şemasında görünmez).

Güvenlik tasarımı:
- Dosya araçları YALNIZCA workspace/<proje>/ içinde çalışır: mutlak yol, "..", "~", gizli dosya/klasör ve sembolik bağ kaçışı reddedilir;
  uzantı izin listesi, dosya boyutu/sayısı sınırı vardır. Gerçek projelerine ve ev klasörüne erişemez.
- Kod, bubblewrap ("bwrap") güvenli kutusunda çalışır: İNTERNET YOK, ev klasörün ve anahtar dosyaların GÖRÜNMEZ (yalnızca sistem kütüphaneleri,
  Python ortamı ve proje klasörü bağlanır), ortam değişkenleri temizdir, süre/bellek/dosya boyutu sınırı vardır, takılan işlem öldürülür.
- Güvenli kutu çalışmıyorsa (kurulu değil / çekirdek izin vermiyor) kod ASLA sessizce çalışmaz: her çalıştırma için sana onay sorulur.
- Çalıştırma izin listesi: python, python3, pytest, node (kabuk yok; "rm", "curl", "bash" reddedilir).
"""
from __future__ import annotations

import os
import resource
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from skills import _confirm as confirm

WORKSPACE = Path(os.environ.get("JARVIS_WORKSPACE") or Path(__file__).resolve().parent.parent / "workspace")
EXTS = {".py", ".js", ".mjs", ".ts", ".html", ".css", ".json", ".md", ".txt", ".csv", ".yaml", ".yml", ".toml", ".ini", ".xml", ".sql",
        ".java", ".c", ".h", ".cpp", ".cs", ".go", ".rs"}
MAX_FILE = 60_000
MAX_FILES = 60
MAX_TOTAL = 2_000_000
READ_LINES = 120
READ_CHARS = 3500
OUT_HEAD, OUT_TAIL = 1200, 1800
RUN_TIMEOUT = 30
RUNNERS = ("python", "python3", "pytest", "node")

_project: Path | None = None
_sandbox_cache: tuple[str | None, str] | None = None


# ------------------------------------------------------------------ proje klasörü
def slugify(text: str, words: int = 4) -> str:
    fold = str.maketrans("çğıöşüâîûÇĞİÖŞÜ", "cgiosuaiuCGIOSU")
    out = []
    for w in "".join(c if c.isalnum() else " " for c in text.translate(fold).lower()).split():
        if w.isascii():
            out.append(w)
        if len(out) >= words:
            break
    return "-".join(out)[:40] or "proje"


def new_project(goal: str) -> Path:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    base = slugify(goal)
    path, n = WORKSPACE / base, 2
    while path.exists():
        path, n = WORKSPACE / f"{base}-{n}", n + 1
    path.mkdir()
    set_project(path)
    return path


def set_project(path: Path | None) -> None:
    global _project
    _project = path


def current() -> Path | None:
    return _project


def rel_name(path: Path) -> str:
    try:
        return f"workspace/{path.relative_to(WORKSPACE)}"
    except ValueError:
        return str(path)


# ------------------------------------------------------------------ yol güvenliği
def norm_rel(rel: str, root_name: str) -> str:
    """Modelin yola eklediği dahili önekleri temizler: 'workspace/main.py' ve 'workspace/<proje>/main.py' -> 'main.py'
    (iç içe workspace/ klasörü oluşmasın). Dahili adlar kullanıcı programı için zaten anlamsızdır."""
    rel = str(rel or "").strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    parts = rel.split("/")
    if len(parts) > 1 and parts[0] == "workspace":
        parts = parts[1:]
        if len(parts) > 1 and parts[0] == root_name:
            parts = parts[1:]
    return "/".join(parts)


def _safe(rel: str, allow_root: bool = False) -> Path:
    root = _project
    if root is None:
        raise ValueError("Proje klasörü yok.")
    root = root.resolve()
    rel = norm_rel(rel, root.name)
    if rel in ("", "."):
        if allow_root:
            return root
        raise ValueError("Dosya adı boş.")
    parts = Path(rel).parts
    if rel.startswith(("/", "~")) or ".." in parts or any(p.startswith(".") for p in parts):
        raise ValueError("Yol proje klasörünün içinde ve göreli olmalı (mutlak yol, '..', '~' ve gizli dosya yok).")
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise ValueError("Yol proje klasörünün dışına çıkıyor (sembolik bağ da olsa).")
    return p


def _all_files(root: Path):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "__pycache__"]
        for f in fn:
            yield Path(dp) / f


# ------------------------------------------------------------------ dosya araçları
def code_list(path: str = ".") -> str:
    try:
        base = _safe(path, allow_root=True)
        root = _project.resolve()
        rows = []
        for f in sorted(_all_files(base)):
            rel = f.relative_to(root)
            if len(rel.parts) <= 4:
                rows.append(f"{rel} ({f.stat().st_size} bayt)")
        return "Proje dosyaları:\n" + "\n".join(rows[:80]) if rows else "Proje klasörü boş."
    except (ValueError, OSError) as exc:
        return f"Hata: {exc}"


def code_read(path: str, start_line: int | str = 1) -> str:
    try:
        p = _safe(path)
        if not p.is_file():
            return f"Hata: '{path}' dosyası yok."
        start = max(1, int(start_line or 1))
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        chunk, used = [], 0
        for i, ln in enumerate(lines[start - 1:start - 1 + READ_LINES], start):
            if used + len(ln) > READ_CHARS:
                break
            chunk.append(f"{i}: {ln}")
            used += len(ln) + 1
        end = start - 1 + len(chunk)
        more = f"\n(devamı için start_line={end + 1}; toplam {len(lines)} satır)" if end < len(lines) else ""
        return "\n".join(chunk) + more if chunk else "(dosya boş)"
    except (ValueError, OSError, TypeError) as exc:
        return f"Hata: {exc}"


def code_write(path: str, content: str) -> str:
    try:
        p = _safe(path)
        if p.suffix.lower() not in EXTS:
            return f"Hata: '{p.suffix or path}' uzantısı yazılamaz. İzinli: {', '.join(sorted(EXTS))}"
        data = str(content)
        if len(data.encode("utf-8")) > MAX_FILE:
            return f"Hata: dosya çok büyük (en fazla {MAX_FILE // 1000} KB). Parçalara böl."
        files = list(_all_files(_project.resolve()))
        if not p.exists() and len(files) >= MAX_FILES:
            return f"Hata: proje en fazla {MAX_FILES} dosya olabilir."
        if sum(f.stat().st_size for f in files if f != p) + len(data) > MAX_TOTAL:
            return "Hata: proje toplam boyut sınırına ulaştı."
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")
        return f"{'Üzerine yazıldı' if existed else 'Yazıldı'}: {path} ({data.count(chr(10)) + 1} satır)."
    except (ValueError, OSError) as exc:
        return f"Hata: {exc}"


# ------------------------------------------------------------------ güvenli kutu
def _roots() -> list[str]:
    """Kutuya salt-okunur bağlanacak Python ortamı klasörleri (/usr zaten bağlı)."""
    out = []
    for p in {sys.prefix, sys.base_prefix, os.path.dirname(os.path.dirname(os.path.realpath(sys.executable)))}:
        if p and not p.startswith(("/usr", "/bin", "/lib")) and p not in ("/", "") and os.path.isdir(p) and p not in out:
            out.append(p)
    return sorted(out)


def bwrap_args(root: Path, argv: list[str], bwrap: str = "bwrap") -> list[str]:
    a = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--ro-bind", "/usr", "/usr"]
    for d in ("/bin", "/sbin", "/lib", "/lib32", "/lib64"):
        if os.path.islink(d):
            a += ["--symlink", os.readlink(d), d]
        elif os.path.isdir(d):
            a += ["--ro-bind", d, d]
    for p in _roots():
        a += ["--ro-bind", p, p]
    a += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--bind", str(root), "/work", "--chdir", "/work",
          "--setenv", "HOME", "/tmp", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
          "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--"]
    return a + argv


def sandbox_mode() -> tuple[str | None, str]:
    """('bwrap' | 'off' | None, neden). Sonuç önbelleğe alınır; bwrap gerçekten çalışıyor mu bir kez denenir."""
    global _sandbox_cache
    if os.environ.get("JARVIS_CODE_SANDBOX") == "off":  # YALNIZCA testler için
        return "off", "kapalı (test)"
    if _sandbox_cache:
        return _sandbox_cache
    exe = shutil.which("bwrap")
    if not exe:
        _sandbox_cache = (None, "bubblewrap kurulu değil (sudo apt install bubblewrap)")
        return _sandbox_cache
    try:
        r = subprocess.run(bwrap_args(WORKSPACE if WORKSPACE.exists() else Path("/tmp"), ["/usr/bin/true"], exe), capture_output=True, timeout=10)
        _sandbox_cache = ("bwrap", "hazır") if r.returncode == 0 else (None, "bubblewrap çalışmadı: " + r.stderr.decode("utf-8", "replace").strip()[:120])
    except (OSError, subprocess.SubprocessError) as exc:
        _sandbox_cache = (None, f"bubblewrap denenemedi ({type(exc).__name__})")
    return _sandbox_cache


def reset_sandbox_cache() -> None:
    global _sandbox_cache
    _sandbox_cache = None


def _limits(is_python: bool):
    def apply():
        resource.setrlimit(resource.RLIMIT_CPU, (RUN_TIMEOUT + 5, RUN_TIMEOUT + 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (20_000_000, 20_000_000))
        if is_python:
            resource.setrlimit(resource.RLIMIT_AS, (3 << 30, 3 << 30))
    return apply


def _argv(command: str) -> list[str] | str:
    """Komutu doğrular; (argv) ya da hata metni döndürür."""
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return f"Hata: komut çözümlenemedi ({exc})."
    if not parts or parts[0] not in RUNNERS:
        return f"Hata: yalnızca şunlar çalıştırılabilir: {', '.join(RUNNERS)}. (kabuk, rm, curl, bash yok)"
    name = _project.name if _project else ""
    parts = [parts[0]] + [norm_rel(a, name) if a.startswith("workspace/") else a for a in parts[1:]]
    for a in parts[1:]:
        if a.startswith(("/", "~")) or ".." in Path(a).parts:
            return "Hata: argümanlarda mutlak yol, '~' ya da '..' olamaz (proje klasörüne göreli yaz)."
    if parts[0] in ("python", "python3"):
        return [sys.executable, *parts[1:]]
    if parts[0] == "pytest":
        return [sys.executable, "-m", "pytest", *parts[1:]]
    node = shutil.which("node")
    return [node, *parts[1:]] if node else "Hata: node kurulu değil."


def _trim(out: str) -> str:
    if len(out) <= OUT_HEAD + OUT_TAIL:
        return out
    return out[:OUT_HEAD] + f"\n…(ortası kısaltıldı, {len(out) - OUT_HEAD - OUT_TAIL} karakter)…\n" + out[-OUT_TAIL:]


def _run(argv: list[str], root: Path, mode: str) -> str:
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"}  # anahtar/oturum değişkeni YOK
    cmd = bwrap_args(root, argv, shutil.which("bwrap") or "bwrap") if mode == "bwrap" else argv
    try:
        p = subprocess.Popen(cmd, cwd=str(root), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             start_new_session=True, preexec_fn=_limits(argv[0] == sys.executable))
    except OSError as exc:
        return f"Hata: başlatılamadı ({exc})."
    try:
        out, _ = p.communicate(timeout=RUN_TIMEOUT)
        text = out.decode("utf-8", errors="replace").strip()
        return f"Çıkış kodu {p.returncode}." + (f"\n{_trim(text)}" if text else " (çıktı yok)")
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        out, _ = p.communicate()
        text = (out or b"").decode("utf-8", errors="replace").strip()
        return f"Hata: {RUN_TIMEOUT} sn içinde bitmedi, durduruldu." + (f"\nŞu ana kadarki çıktı:\n{_trim(text)}" if text else "")


def code_run(command: str) -> str:
    if _project is None:
        return "Hata: Proje klasörü yok."
    argv = _argv(str(command))
    if isinstance(argv, str):
        return argv
    mode, why = sandbox_mode()
    root = _project.resolve()
    if mode is None:
        return confirm.request(f"Güvenli kutu yok ({why}). '{command}' komutu proje klasöründe doğrudan, korumasız çalışacak.",
                               lambda: _run(argv, root, "off"))
    return _run(argv, root, mode)


def _p(**props):
    return {"type": "object", "properties": {k: {"type": v[0], "description": v[1]} for k, v in props.items()}, "required": [k for k, v in props.items() if len(v) < 3]}


SKILLS = [
    {"name": "code_list", "description": "Kod projesindeki dosyaları listeler.", "hidden": True, "run": code_list,
     "parameters": _p(path=("string", "Klasör (varsayılan '.')", "opt"))},
    {"name": "code_read", "description": "Kod projesinden bir dosyayı satır numaralarıyla okur.", "hidden": True, "run": code_read,
     "parameters": _p(path=("string", "Dosya yolu"), start_line=("integer", "Başlangıç satırı", "opt"))},
    {"name": "code_write", "description": "Kod projesine dosya yazar (tam içerik).", "hidden": True, "run": code_write,
     "parameters": _p(path=("string", "Dosya yolu"), content=("string", "Dosyanın tam içeriği"))},
    {"name": "code_run", "description": "Kod projesinde python/pytest/node komutu çalıştırır (güvenli kutuda, internetsiz).", "hidden": True, "run": code_run,
     "parameters": _p(command=("string", "Örn. python main.py"))},
]
