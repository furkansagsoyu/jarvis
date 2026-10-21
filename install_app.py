#!/usr/bin/env python3
"""JARVIS'i uygulama menüsüne (ve istersen masaüstüne) simgesiyle kurar. Terminal gerekmez.

    python install_app.py                # ~/.local/share/applications/jarvis.desktop + simge
    python install_app.py --desktop      # ayrıca masaüstüne kısayol
    python install_app.py --remove       # hepsini kaldırır
    python install_app.py --status

Şu an çalışan Python (freya ortamı) ve bu klasör kaydedilir; ortamı ya da klasörü değiştirirsen yeniden kur.
Menüdeki simgeye sağ tıklayınca "Hata ayıklama (terminalde)" eylemi de çıkar.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "jarvis"


def paths(home: Path | None = None) -> dict:
    home = home or Path.home()
    return {
        "desktop": home / ".local/share/applications/jarvis.desktop",
        "icon": home / ".local/share/icons/hicolor/256x256/apps/jarvis.png",
        "icon512": home / ".local/share/icons/hicolor/512x512/apps/jarvis.png",
        "icon_svg": home / ".local/share/icons/hicolor/scalable/apps/jarvis.svg",
        "shortcut": home / "Desktop/jarvis.desktop",
    }


def exec_quote(arg: str) -> str:
    """.desktop Exec alanı kuralı: boşluk/özel karakter varsa çift tırnak, içindeki \\ " ` $ kaçırılır."""
    if arg and not any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return arg
    return '"' + "".join("\\" + c if c in '"`$\\' else c for c in arg) + '"'


def desktop_text(python: str = sys.executable, project: Path = HERE, icon: str = NAME) -> str:
    app = exec_quote(str(project / "app.py"))
    py = exec_quote(python)
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=JARVIS\n"
        "GenericName=Sesli asistan\n"
        "Comment=Yerel, ücretsiz Türkçe sesli asistan (Hey Jarvis)\n"
        f"Exec={py} {app}\n"
        f"Path={project}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;AudioVideo;\n"
        "Keywords=jarvis;asistan;sesli;ai;\n"
        "StartupNotify=false\n"
        "Actions=debug;\n\n"
        "[Desktop Action debug]\n"
        "Name=Hata ayıklama (terminalde)\n"
        f"Exec={py} {app} --debug\n"
    )


def _refresh() -> None:
    for cmd in (["update-desktop-database", str(Path.home() / ".local/share/applications")],
                ["gtk-update-icon-cache", "-f", "-t", str(Path.home() / ".local/share/icons/hicolor")]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=False, capture_output=True, timeout=20)


def install(home: Path | None = None, desktop: bool = False, python: str = sys.executable, project: Path = HERE) -> dict:
    p = paths(home)
    for k in ("desktop", "icon", "icon512", "icon_svg"):
        p[k].parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(project / "assets" / "jarvis-256.png", p["icon"])
    shutil.copy(project / "assets" / "jarvis.png", p["icon512"])
    shutil.copy(project / "assets" / "jarvis.svg", p["icon_svg"])
    text = desktop_text(python, project)
    p["desktop"].write_text(text, encoding="utf-8")
    p["desktop"].chmod(0o755)
    if desktop:
        p["shortcut"].parent.mkdir(parents=True, exist_ok=True)
        p["shortcut"].write_text(text, encoding="utf-8")
        p["shortcut"].chmod(0o755)
        if shutil.which("gio") and home is None:  # Cinnamon/Nemo: masaüstü kısayolunu "güvenilir" işaretle
            subprocess.run(["gio", "set", str(p["shortcut"]), "metadata::trusted", "true"], check=False, capture_output=True)
    if home is None:
        _refresh()
    return p


def remove(home: Path | None = None) -> list[str]:
    gone = []
    for k, f in paths(home).items():
        if f.exists():
            f.unlink()
            gone.append(str(f))
    if home is None:
        _refresh()
    return gone


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--desktop", action="store_true", help="masaüstüne de kısayol koy")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        for k, f in paths().items():
            print(f"{'VAR ' if f.exists() else 'YOK '} {k}: {f}")
        return
    if a.remove:
        print("Kaldırıldı:" if remove() else "Kurulu bir şey bulunamadı.")
        return
    p = install(desktop=a.desktop)
    print("Kuruldu. Uygulama menüsünde 'JARVIS' ara (Utility/Yardımcı Programlar altında da çıkar).")
    print(f"  Çalıştıran Python: {sys.executable}")
    print(f"  Kayıt dosyası: {HERE / 'data' / 'jarvis.log'}")
    if a.desktop:
        print(f"  Masaüstü kısayolu: {p['shortcut']} (gerekirse sağ tık > Çalıştırmaya izin ver)")


if __name__ == "__main__":
    main()
