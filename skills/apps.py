"""Uygulama açma: kurulu uygulamaları .desktop dosyalarından bulur, kabuk komutu çalıştırmaz."""
import difflib
import os
import shlex
import shutil
import subprocess
from pathlib import Path

DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/snapd/desktop/applications"),
]

# Türkçe genel adlar -> olası uygulama adları/kimlikleri (sırayla denenir)
ALIASES = {
    "terminal": ["gnome-terminal", "org.gnome.Terminal", "xfce4-terminal", "konsole", "tilix", "xterm"],
    "komut satırı": ["gnome-terminal", "xfce4-terminal", "konsole", "xterm"],
    "tarayıcı": ["firefox", "google-chrome", "chromium", "brave-browser"],
    "web tarayıcısı": ["firefox", "google-chrome", "chromium", "brave-browser"],
    "dosya yöneticisi": ["nemo", "nautilus", "thunar", "dolphin", "pcmanfm"],
    "dosyalar": ["nemo", "nautilus", "thunar", "dolphin"],
    "hesap makinesi": ["calculator", "gnome-calculator", "mate-calc", "kcalc", "galculator"],
    "metin düzenleyici": ["xed", "gedit", "org.gnome.TextEditor", "kate", "mousepad"],
    "not defteri": ["xed", "gedit", "org.gnome.TextEditor", "mousepad"],
    "ayarlar": ["cinnamon-settings", "gnome-control-center", "systemsettings"],
    "sistem ayarları": ["cinnamon-settings", "gnome-control-center", "systemsettings"],
    "kod editörü": ["code", "codium"],
    "müzik": ["spotify", "rhythmbox", "org.gnome.Rhythmbox3"],
}

_cache: list[dict] | None = None


def _norm(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower().strip()


def _parse(path: Path) -> dict | None:
    data, in_entry = {}, False
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("["):
                in_entry = line == "[Desktop Entry]"
                continue
            if in_entry and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                data.setdefault(k.strip(), v.strip())
    except OSError:
        return None
    if data.get("Type", "Application") != "Application" or data.get("NoDisplay") == "true" or data.get("Hidden") == "true":
        return None
    if not data.get("Exec"):
        return None
    names = [data.get(k, "") for k in ("Name[tr]", "Name", "GenericName[tr]", "GenericName")]
    return {
        "id": path.stem,
        "title": data.get("Name[tr]") or data.get("Name") or path.stem,
        "names": [_norm(n) for n in names if n],
        "exec": data["Exec"],
    }


def index(refresh: bool = False) -> list[dict]:
    global _cache
    if _cache is None or refresh:
        found, seen = [], set()
        for d in DIRS:
            if not d.is_dir():
                continue
            for p in sorted(d.glob("*.desktop")):
                if p.stem in seen:
                    continue
                entry = _parse(p)
                if entry:
                    seen.add(p.stem)
                    found.append(entry)
        _cache = found
    return _cache


def find(query: str) -> dict | None:
    apps = index()
    q = _norm(query)
    candidates = [q] + [_norm(a) for a in ALIASES.get(q, [])]
    for cand in candidates:  # 1) tam eşleşme (kimlik veya ad)
        for a in apps:
            if cand == _norm(a["id"]) or cand in a["names"] or cand == _norm(a["id"].split(".")[-1]):
                return a
    for cand in candidates:  # 2) başlangıç / içerme
        for a in apps:
            if any(n.startswith(cand) for n in a["names"]) or _norm(a["id"]).startswith(cand):
                return a
    for cand in candidates:
        if len(cand) >= 4:
            for a in apps:
                if any(cand in n for n in a["names"]):
                    return a
    # 3) yazım hatasına tolerans
    pool = {}
    for a in apps:
        for n in a["names"] + [_norm(a["id"])]:
            pool[n] = a
    close = difflib.get_close_matches(q, list(pool), n=1, cutoff=0.75)
    return pool[close[0]] if close else None


def _launch(app: dict):
    if shutil.which("gtk-launch"):
        res = subprocess.run(["gtk-launch", app["id"]], capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            return
    cmd = [part for part in shlex.split(app["exec"]) if not (part.startswith("%") and len(part) == 2)]
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, env=os.environ.copy())


def open_app(name: str) -> str:
    app = find(str(name))
    if not app:
        return f"'{name}' adında kurulu bir uygulama bulamadım."
    try:
        _launch(app)
    except Exception as exc:  # noqa: BLE001
        return f"{app['title']} açılamadı: {type(exc).__name__}: {exc}"
    return f"{app['title']} açıldı."


SKILLS = [
    {
        "name": "open_app",
        "description": "Bilgisayarda bir uygulamayı açar. Kullanıcı bir programı açmanı isterse kullan.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Uygulama adı, örneğin firefox, terminal, hesap makinesi"}
            },
            "required": ["name"],
        },
        "run": open_app,
    }
]
