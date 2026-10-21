#!/usr/bin/env python3
"""Telefon (ADB) tanılama: bağlantı, model, arama durumu okuma, tuş izni, rehber erişimi.

    python phone_check.py                 # yalnızca okuma/yoklama, hiçbir şey aramaz
    python phone_check.py --dial 05XXXXXXXXX   # arama ekranını numarayla açar (aramaz)
    python phone_check.py --call 05XXXXXXXXX   # GERÇEKTEN arar (önce sorar); beklediğin biri için kullan
"""
import re
import sys

from skills import phone as P


def step(ok, text):
    print(("✓ " if ok else "✗ ") + text)
    return ok


def main():
    args = sys.argv[1:]
    if not step(bool(P.adb_path()), "adb kurulu" if P.adb_path() else "adb yok: sudo apt install adb"):
        return 1
    rows = P.devices()
    step(bool(rows), f"cihazlar: {rows or 'yok (USB hata ayıklama açık mı, kablo takılı mı?)'}")
    serial, err = P.pick_device()
    if not serial:
        print("  →", err)
        return 1
    for label, prop in (("marka", "ro.product.manufacturer"), ("model", "ro.product.model"), ("Android", "ro.build.version.release")):
        print(f"  {label}: {P._sh(serial, 'getprop', prop)[1]}")
    st = P.call_state(serial)
    step(st is not None, f"arama durumu okunabiliyor (şu an: {st})")
    code, out = P._key(serial, "KEYCODE_UNKNOWN")
    ok_key = code == 0 and not re.search(r"inject_events|securityexception|permission", out, re.I)
    step(ok_key, "tuş gönderme izni (aramayı kapatmak için gerekli)")
    if not ok_key:
        print("  → Xiaomi: Ayarlar > Ek ayarlar > Geliştirici seçenekleri > “USB hata ayıklama (Güvenlik ayarları)” aç (Mi hesabı/SIM ister).")
    code, out = P._sh(serial, "content", "query", "--uri", "content://com.android.contacts/data/phones", "--projection", "display_name:data1", timeout=30)
    n = len(P.parse_contacts_output(out)) if code == 0 else 0
    step(n > 0, f"rehber okunabiliyor ({n} kişi)" if n else "rehber okunamadı (elle ekleme: “rehbere ekle: Annem 0555…”)")
    if "--dial" in args:
        num = P.clean_number(args[args.index("--dial") + 1])
        print("  →", "numara geçersiz" if not num else P._sh(serial, "am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{num}")[1])
    if "--call" in args:
        num = P.clean_number(args[args.index("--call") + 1])
        if not num:
            print("numara geçersiz")
            return 1
        if input(f"GERÇEKTEN {num} aranacak. Devam? (evet/hayır) ").strip().lower() != "evet":
            return 0
        print(P._do_call("bu numara", num))
        input("Kapatmak için Enter… ")
        print(P.phone_hangup())
    return 0


if __name__ == "__main__":
    sys.exit(main())
