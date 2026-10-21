"""Masaüstü uygulaması testleri: .desktop dosyası, simge kurulumu/kaldırma, başlatıcı mantığı (gerçek süreç başlatmadan)."""
import fcntl
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
import app  # noqa: E402
import install_app as I  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


home = Path(tempfile.mkdtemp())
p = I.install(home=home, desktop=True)
txt = p["desktop"].read_text(encoding="utf-8")
lines = dict(l.split("=", 1) for l in txt.split("[Desktop Action")[0].splitlines() if "=" in l and not l.startswith("["))
check(".desktop: ad, Terminal=false, Utility kategorisi", lines["Name"] == "JARVIS" and lines["Terminal"] == "false" and "Utility" in lines["Categories"])
check(".desktop: Exec mutlak python + app.py", lines["Exec"].startswith(sys.executable) and lines["Exec"].endswith("app.py") and Path(sys.executable).is_absolute())
check(".desktop: çalışma klasörü proje", lines["Path"] == str(I.HERE))
check(".desktop: hata ayıklama eylemi", "[Desktop Action debug]" in txt and "--debug" in txt.split("[Desktop Action debug]")[1])
check("simgeler kopyalandı (256, 512, svg)", all(p[k].exists() and p[k].stat().st_size > 500 for k in ("icon", "icon512", "icon_svg")))
check("kaynak simgeler gerçek PNG", (I.HERE / "assets" / "jarvis.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n")
check("masaüstü kısayolu çalıştırılabilir", p["shortcut"].exists() and os.access(p["shortcut"], os.X_OK))
check("dosya çalıştırılabilir (0755)", os.access(p["desktop"], os.X_OK))
check("boşluklu yol doğru alıntılanır", I.exec_quote("/a b/c") == '"/a b/c"' and I.exec_quote("/x/y") == "/x/y")
t2 = I.desktop_text("/opt/my py/bin/python", Path("/home/u/Jarvis Proje"))
check("boşluklu python/klasör Exec'te çift tırnaklı", 'Exec="/opt/my py/bin/python" "/home/u/Jarvis Proje/app.py"' in t2)
gone = I.remove(home=home)
check("kaldırma hepsini siler", len(gone) == 5 and not p["desktop"].exists() and not p["icon"].exists() and not p["shortcut"].exists())
check("ikinci kaldırma sorunsuz", I.remove(home=home) == [])
check("yeniden kurulum üzerine yazar", I.install(home=home)["desktop"].exists())

# başlatıcı: kilit durumu
lock = open(app.LOCK, "a+")  # noqa: SIM115
fcntl.flock(lock, fcntl.LOCK_UN)
check("Jarvis çalışmıyorsa is_running False", app.is_running() is False)
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
check("kilit tutuluyorsa (main.py çalışıyor) is_running True", app.is_running() is True)
fcntl.flock(lock, fcntl.LOCK_UN)
lock.close()
check("kilit bırakılınca tekrar False", app.is_running() is False)

# bayraklar
d = app.data_dir()
d.mkdir(parents=True, exist_ok=True)
for f in ("launch_args.txt", "telegram.json"):
    (d / f).unlink(missing_ok=True)
check("varsayılan bayraklar: --wake --dash --morning", app.default_args() == ["--wake", "--dash", "--morning"])
(d / "telegram.json").write_text('{"token": "x", "chat_id": 1}', encoding="utf-8")
check("Telegram kuruluysa --telegram eklenir", app.default_args()[-1] == "--telegram")
(d / "launch_args.txt").write_text("--text --dash\n", encoding="utf-8")
check("launch_args.txt varsa o kullanılır", app.default_args() == ["--text", "--dash"])
(d / "launch_args.txt").unlink()

# açılış: gerçek süreç yerine sahte Popen
calls = []
app.subprocess.Popen = lambda cmd, **kw: calls.append((cmd, kw)) or type("P", (), {})()
app.notify = lambda text: calls.append(("notify", text))
app.is_running = lambda: False
rc = app.main()
start = [c for c in calls if isinstance(c[0], list)][0]
check("kapalıyken main.py başlatılır (terminalsiz, ayrı oturum, log'a)", rc == 0 and start[0][1].endswith("main.py") and start[1]["start_new_session"] is True
      and start[1]["stdin"] is app.subprocess.DEVNULL and (d / "jarvis.log").exists())
check("başlarken bildirim gösterilir", any(c[0] == "notify" for c in calls))
calls.clear()
app.is_running = lambda: True
(d / "dashboard.json").write_text('{"url": "http://127.0.0.1:8765/?t=abc"}', encoding="utf-8")
rc = app.main()
win = [c for c in calls if isinstance(c[0], list)][0]
check("çalışıyorsa yalnızca pano penceresi açılır (ikinci Jarvis başlamaz)", rc == 0 and "dashboard.window" in win[0] and not any("main.py" in str(c[0]) for c in calls))
calls.clear()
(d / "dashboard.json").unlink()
check("pano adresi yoksa hata kodu + bildirim", app.main() == 1 and any(c[0] == "notify" for c in calls))
big = d / "jarvis.log"
big.write_bytes(b"x" * (app.LOG_MAX + 10))
app.is_running = lambda: False
calls.clear()
app.main()
check("büyük log döndürülür", (d / "jarvis.log.old").exists() and (d / "jarvis.log").stat().st_size < 1000)

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
