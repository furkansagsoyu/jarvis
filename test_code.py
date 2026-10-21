"""Kod ajanı araçları testleri: yol güvenliği, sınırlar, çalıştırma kısıtları, güvenli kutu komutu (bubblewrap olmadan, kuru çalıştırma)."""
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

WS = tempfile.mkdtemp()
os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
os.environ["JARVIS_WORKSPACE"] = WS
os.environ["JARVIS_CODE_SANDBOX"] = "off"          # yalnızca bu test süreci: gerçek kutu yok, işlevi deneriz
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
os.environ["GROQ_API_KEY"] = "gsk_gizli_anahtar_asla_gorunmemeli"
from skills import _confirm as confirm  # noqa: E402
from skills import codeagent as C  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


check("slug: Türkçe harfler, 4 kelime sınırı, boşsa 'proje'", C.slugify("Hesap Makinesi Yaz: çok güzel şirin bir şey") == "hesap-makinesi-yaz-cok" and C.slugify("???") == "proje" and C.slugify("Çığlık Öğüt") == "ciglik-ogut")
check("proje yokken araçlar hata verir", C.code_write("a.py", "x").startswith("Hata") and C.code_run("python a.py").startswith("Hata"))
root = C.new_project("Hesap makinesi")
p2 = C.new_project("Hesap makinesi")
check("proje workspace altında açılır, aynı ad çakışmaz", root.parent == Path(WS) and p2.name == "hesap-makinesi-2" and C.rel_name(root) == "workspace/hesap-makinesi")
C.set_project(root)

# yol güvenliği
os.symlink("/tmp", root / "kacis")
for bad_path in ("/etc/passwd", "../x.py", "a/../../x.py", "~/x.py", ".gizli.py", ".git/config", "kacis/x.py", ""):
    check(f"yol reddedilir: {bad_path!r}", C.code_write(bad_path, "x").startswith("Hata") and not (Path("/tmp") / "x.py").exists())
check("sembolik bağ üzerinden okuma da reddedilir", C.code_read("kacis/x.py").startswith("Hata"))
check("izinsiz uzantı reddedilir (.sh, .so, uzantısız)", all(C.code_write(n, "x").startswith("Hata") for n in ("a.sh", "b.so", "Makefile")))
check("büyük dosya reddedilir", C.code_write("big.txt", "x" * (C.MAX_FILE + 1)).startswith("Hata: dosya çok büyük"))

# modelin eklediği dahili önekler temizlenir (iç içe workspace/ klasörü oluşmasın)
check("norm_rel: workspace/ ve workspace/<proje>/ önekleri atılır, diğerleri korunur",
      C.norm_rel("workspace/main.py", "hesap-makinesi") == "main.py" and C.norm_rel("workspace/hesap-makinesi/src/a.py", "hesap-makinesi") == "src/a.py"
      and C.norm_rel("./main.py", "x") == "main.py" and C.norm_rel("src/workspace/a.py", "x") == "src/workspace/a.py" and C.norm_rel("workspace", "x") == "workspace")
C.code_write("workspace/ic.py", "print('ic')")
C.code_write("workspace/hesap-makinesi/ic2.py", "print('ic2')")
check("yazma: 'workspace/...' yolu proje köküne yazılır, iç içe klasör OLUŞMAZ", (root / "ic.py").exists() and (root / "ic2.py").exists() and not (root / "workspace").exists())
check("okuma/çalıştırma: 'workspace/ic.py' da çalışır", C.code_read("workspace/ic.py").startswith("1: print") and C.code_run("python workspace/ic.py") == "Çıkış kodu 0.\nic")
for f in ("ic.py", "ic2.py"):
    (root / f).unlink()

# yaz/oku/listele
out = C.code_write("calc/main.py", "def topla(a, b):\n    return a + b\n\nprint(topla(2, 3))\n")
check("yazma: alt klasör oluşur, satır sayısı döner", out == "Yazıldı: calc/main.py (5 satır)." and (root / "calc/main.py").exists(), out)
check("üzerine yazma bildirilir", C.code_write("calc/main.py", "print(1)").startswith("Üzerine yazıldı"))
C.code_write("calc/main.py", "def topla(a, b):\n    return a + b\n\nprint(topla(2, 3))\n")
r = C.code_read("calc/main.py")
check("okuma: satır numaralı", r.startswith("1: def topla") and "4: print(topla(2, 3))" in r)
C.code_write("uzun.txt", "\n".join(f"satir {i}" for i in range(1, 301)))
r = C.code_read("uzun.txt")
check("uzun dosya parça parça okunur, devam satırı söylenir", r.count("\n") <= C.READ_LINES + 1 and "start_line=121" in r and "toplam 300 satır" in r, r[-80:])
check("start_line ile devam", C.code_read("uzun.txt", "121").startswith("121: satir 121") and C.code_read("yok.py").startswith("Hata"))
lst = C.code_list()
check("listeleme: dosyalar ve boyut", "calc/main.py" in lst and "uzun.txt" in lst and "kacis" not in lst.replace("kacis/x", ""), lst)
for i in range(C.MAX_FILES):
    C.code_write(f"f{i}.txt", "x")
check("dosya sayısı sınırı", C.code_write("fazla.txt", "x").startswith("Hata: proje en fazla"))
for f in root.glob("f*.txt"):
    f.unlink()

# çalıştırma
r = C.code_run("python calc/main.py")
check("çalıştırma: çıktı ve çıkış kodu", r == "Çıkış kodu 0.\n5", r)
C.code_write("hata.py", "raise ValueError('bozuk')")
r = C.code_run("python hata.py")
check("hata: çıkış kodu 1 ve traceback ajana döner (düzeltsin diye)", r.startswith("Çıkış kodu 1.") and "ValueError: bozuk" in r)
C.code_write("env.py", "import os\nprint(sorted(os.environ))\nprint(os.getcwd())")
r = C.code_run("python env.py")
check("ortam temiz: API anahtarı/oturum değişkeni alt sürece GEÇMEZ", "GROQ" not in r and "gsk_" not in r and "DISPLAY" not in r and "HOME" in r, r)
C.code_write("uyu.py", "import time\nprint('basladi', flush=True)\ntime.sleep(60)")
C.RUN_TIMEOUT = 1
r = C.code_run("python uyu.py")
C.RUN_TIMEOUT = 30
check("takılan işlem zaman aşımında öldürülür, çıktısı korunur", r.startswith("Hata: 1 sn içinde bitmedi") and "basladi" in r, r)
C.code_write("cok.py", "print('a' * 6000)\nprint('SON')")
r = C.code_run("python cok.py")
check("uzun çıktı baş+son kalacak şekilde kısaltılır", len(r) < C.OUT_HEAD + C.OUT_TAIL + 200 and r.rstrip().endswith("SON") and "kısaltıldı" in r)
C.code_write("test_ornek.py", "import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1 + 1, 2)\nif __name__ == '__main__':\n    unittest.main()")
r = C.code_run("python -m unittest test_ornek -v")
check("unittest çalışır", "Çıkış kodu 0." in r and "OK" in r, r)
for cmd in ("bash -c 'echo hi'", "rm -rf /", "curl http://x.com", "python /etc/passwd", "python ../x.py", "python ~/x.py", "ls", "", "python 'tirnak"):
    check(f"komut reddedilir: {cmd!r}", C.code_run(cmd).startswith("Hata"))
check("shell ayrıştırması: ';' ve '&&' kabuğa gitmez (python argümanı olur)", "Çıkış kodu" in C.code_run("python calc/main.py ; echo kotu") and "kotu" not in C.code_run("python calc/main.py ; echo kotu").replace("echo kotu", ""))

# güvenli kutu komutu (bwrap çalıştırmadan)
argv = C.bwrap_args(root, [sys.executable, "main.py"], "/usr/bin/bwrap")
s = " ".join(argv)
check("kutu: ağ/pid/kullanıcı ayrık, ana süreç ölünce kapanır, ortam temiz", argv[0] == "/usr/bin/bwrap" and "--unshare-all" in argv and "--die-with-parent" in argv and "--clearenv" in argv and "--share-net" not in argv)
home = os.path.expanduser("~")
binds = [argv[i + 1] for i, a in enumerate(argv) if a in ("--bind", "--ro-bind")]
check("kutu: ev klasörü ve veri/anahtar klasörleri BAĞLANMAZ, yalnızca proje yazılabilir", home not in binds and not any(b == "/" for b in binds)
      and [argv[i + 1:i + 3] for i, a in enumerate(argv) if a == "--bind"] == [[str(root), "/work"]], str(binds))
check("kutu: komut '--' sonrasında, çalışma klasörü /work", argv[argv.index("--") + 1:] == [sys.executable, "main.py"] and "--chdir" in argv and argv[argv.index("--chdir") + 1] == "/work")
check("kutu: /usr salt-okunur", ["--ro-bind", "/usr", "/usr"] == argv[argv.index("--ro-bind"):argv.index("--ro-bind") + 3])

# kutu yoksa: her çalıştırma onay ister
os.environ.pop("JARVIS_CODE_SANDBOX")
C.reset_sandbox_cache()
_which = C.shutil.which
C.shutil.which = lambda n: None if n == "bwrap" else _which(n)
mode, why = C.sandbox_mode()
check("bubblewrap yoksa mod None ve neden söylenir", mode is None and "bubblewrap" in why, why)
r = C.code_run("python calc/main.py")
check("kutu yokken kod SESSİZCE çalışmaz: onay sorusu döner", "Güvenli kutu yok" in r and "Onaylıyor musun" in r and confirm.has_pending(), r)
confirm.cancel()
r = C.code_run("python calc/main.py")
out = confirm.approve()
check("onaylanırsa çalışır", out == "Çıkış kodu 0.\n5", out)

# bwrap var ama çekirdek izin vermiyorsa (kullanıcı ad alanı kapalı) -> mod None, neden gösterilir
C.reset_sandbox_cache()
C.shutil.which = lambda n: "/usr/bin/bwrap" if n == "bwrap" else _which(n)
_run = subprocess.run
subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=1, stderr=b"bwrap: setting up uid map: Permission denied")
mode, why = C.sandbox_mode()
check("bwrap çalışmazsa (izin yok) mod None, hata metni nedende", mode is None and "Permission denied" in why, why)
C.reset_sandbox_cache()
subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=b"")
check("bwrap sağlamsa mod 'bwrap' ve sonuç önbelleğe alınır", C.sandbox_mode() == ("bwrap", "hazır") and C.sandbox_mode() == ("bwrap", "hazır"))
subprocess.run = _run
C.shutil.which = _which

check("araçlar şemada gizli (sesli modele görünmez)", all(s["hidden"] for s in C.SKILLS) and {s["name"] for s in C.SKILLS} == {"code_list", "code_read", "code_write", "code_run"})
print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
