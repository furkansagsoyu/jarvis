"""Kod ajanının güvenli kutusunu KENDİ bilgisayarında dener.

    python code_check.py

Kutu (bubblewrap) çalışıyor mu, kod internete çıkabiliyor mu, ev klasörünü / anahtar dosyalarını görebiliyor mu, ortam temiz mi, süre sınırı işliyor mu?
"""
from __future__ import annotations

import json
import shutil
import sys

from skills import codeagent as C

PROBE = r'''
import json, os, socket
res = {}
def t(name, fn):
    try: res[name] = fn()
    except Exception as e: res[name] = "hata:" + type(e).__name__
def net():
    s = socket.socket(); s.settimeout(3); s.connect(("1.1.1.1", 53)); s.close(); return "BAĞLANDI"
t("internet", net)
t("ev_klasoru", lambda: sorted(os.listdir(os.path.expanduser("~")))[:5] if os.path.isdir(os.path.expanduser("~")) else "yok")
t("ssh", lambda: os.path.exists(os.path.expanduser("~/.ssh")) or os.path.exists("/home/" + (os.environ.get("USER") or "x") + "/.ssh"))
t("anahtarlar", lambda: [k for k in os.environ if "KEY" in k or "TOKEN" in k or "SECRET" in k])
def write_usr():
    open("/usr/yazma_denemesi", "w").write("x"); return "YAZILDI"
t("usr_yazma", write_usr)
open("proje_ici.txt", "w").write("ok"); res["proje_ici_yazma"] = "tamam"
print(json.dumps(res, ensure_ascii=False))
'''


def main() -> int:
    mode, why = C.sandbox_mode()
    print(f"Güvenli kutu: {mode or 'YOK'} — {why}")
    if mode is None:
        print("\nKutu yokken kod ajanı her çalıştırma için sana onay sorar (korumasız). Kutuyu kurmak için: sudo apt install bubblewrap")
        print("Kurulu ama 'çalışmadı' diyorsa hata metnini bana yapıştır.")
    print(f"bwrap yolu: {shutil.which('bwrap')}")
    root = C.new_project("_kontrol")
    try:
        print(C.code_write("probe.py", PROBE))
        out = C.code_run("python probe.py")
        print(out)
        try:
            res = json.loads(out.split("\n", 1)[1])
        except (IndexError, ValueError):
            print("\nProbe çıktısı çözülemedi.")
            return 2
        good = (res.get("internet") != "BAĞLANDI" and not res.get("anahtarlar") and res.get("usr_yazma") != "YAZILDI" and res.get("proje_ici_yazma") == "tamam")
        print("\nSONUÇ:", "kutu sağlam (internet yok, anahtar yok, sistem yazılamaz, proje yazılabilir) ✓" if good and mode == "bwrap" else
              ("kutu YOK: yukarıdakiler korumasız ortamı gösterir" if mode is None else "kontrol et: beklenmeyen değerler var"))
        C.RUN_TIMEOUT = 2
        C.code_write("uyu.py", "import time; time.sleep(30)")
        print("süre sınırı:", C.code_run("python uyu.py").splitlines()[0])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
