"""Telefondan erişim kurulumu (Tailscale).  Kullanım:

  python connect/remote_setup.py              # kurar, telefona açılacak bağlantıyı (ve varsa QR'ı) yazar
  python connect/remote_setup.py --new-token  # anahtarı yenile (eski telefon bağlantısı çalışmaz olur)
  python connect/remote_setup.py --status     # durum
  python connect/remote_setup.py --revoke     # uzaktan erişimi kapat (anahtar silinir)
  python connect/remote_setup.py --host pc.tailXXXX.ts.net   # adı elle ver (Tailscale okunamazsa)
  python connect/remote_setup.py --no-serve   # `tailscale serve` komutunu sen çalıştırırsın

Önkoşul: PC ve telefonda Tailscale kurulu, aynı hesapla giriş yapılmış; yönetim panelinde
(login.tailscale.com/admin/dns) MagicDNS ve HTTPS Certificates açık. Jarvis --dash ile başlatılmalı.
"""
from __future__ import annotations
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri


import argparse
import sys

from connect import remote


def _qr(text: str) -> bool:
    try:
        import qrcode  # noqa: PLC0415
    except ImportError:
        return False
    q = qrcode.QRCode(border=1)
    q.add_data(text)
    q.make(fit=True)
    q.print_ascii(invert=True)
    return True


def status() -> int:
    d = remote.load()
    print(f"Uzaktan erişim : {'AÇIK' if remote.enabled() else 'kapalı'}")
    print(f"Adres          : {remote.public_url(d['hosts'][0]) if d.get('hosts') else '(ayarlı değil)'}")
    print(f"Port           : {d.get('port', remote.DEFAULT_PORT)}")
    print(f"Tailscale      : {remote.tailscale_bin() or 'kurulu değil'}")
    if remote.tailscale_bin():
        print(f"Funnel         : {'AÇIK (tehlikeli!)' if remote.funnel_on() else 'kapalı (iyi)'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--new-token", action="store_true")
    p.add_argument("--revoke", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--no-serve", action="store_true")
    p.add_argument("--host", default="")
    p.add_argument("--port", type=int, default=0)
    a = p.parse_args()

    if a.status:
        return status()
    if a.revoke:
        remote.revoke()
        print("Uzaktan erişim kapatıldı, telefon anahtarı silindi.")
        print("Yayını da kaldırmak için:  tailscale serve reset")
        return 0

    port = a.port or int(remote.load().get("port", remote.DEFAULT_PORT))
    host = a.host.strip().lower().rstrip(".")
    if not host:
        host, why = remote.tailnet_name()
        if not host:
            print(f"HATA: {why}")
            print("Tailscale'i kurup giriş yaptıktan sonra tekrar dene ya da --host ile adı elle ver.")
            return 1
    d = remote.load()
    d["port"] = port
    remote.save(d)
    remote.set_hosts([host])
    tok = remote.token() if (remote.enabled() and not a.new_token) else remote.new_token()

    if not a.no_serve:
        ok, msg = remote.apply_serve(port)
        if not ok:
            print(f"UYARI: yayın açılamadı: {msg}")
            print("  Yetki hatasıysa bir kez:  sudo tailscale set --operator=$USER   sonra bu komutu yeniden çalıştır.")
            print(f"  Elle:  tailscale serve --bg --https=443 http://127.0.0.1:{port}")
        else:
            print(f"Yayın açıldı (yalnızca tailnet): {remote.public_url(host)}")
    else:
        print(f"Elle çalıştır:  tailscale serve --bg --https=443 http://127.0.0.1:{port}")

    url = remote.pair_url(host, tok)
    print("\nTelefonda (Tailscale açıkken) şu bağlantıyı Chrome'da aç, sonra menüden “Ana ekrana ekle”:\n")
    print(f"  {url}\n")
    if not _qr(url):
        print("(QR için: pip install qrcode — ya da bağlantıyı telefona kendi yolunla taşı; Telegram'dan gönderme.)")
    print("Anahtarı kimseyle paylaşma. Yenilemek için --new-token, kapatmak için --revoke.")
    print("Jarvis'i  python main.py --dash ...  ile (pano açık) başlatman gerekir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
