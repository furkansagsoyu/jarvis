#!/usr/bin/env python3
"""Telefon (ADB) tanılama: bağlantı, model, arama durumu okuma, tuş izni, rehber erişimi.

    python phone_check.py                 # yalnızca okuma/yoklama, hiçbir şey aramaz
    python phone_check.py --dial 05XXXXXXXXX   # arama ekranını numarayla açar (aramaz)
    python phone_check.py --call 05XXXXXXXXX   # GERÇEKTEN arar (önce sorar); beklediğin biri için kullan

Telefon uygulaması (internet üzerinden, kablosuz ve uzaktan):
    python phone_check.py --app-pair     # BİR KEZ: uygulamayla eşleşir (telefon USB/kablosuz ADB ile bağlıyken)
    python phone_check.py --app-test     # telefona deneme bildirimi gönderir

Kablosuz (kabloyu çıkarabilmek için):
    python phone_check.py --wifi                       # USB takılıyken BİR KEZ: telefonu Wi-Fi'dan ADB'ye açar, adresi kaydeder
    python phone_check.py --pair 192.168.1.23:37000 123456   # alternatif: Kablosuz hata ayıklama > "Eşleştirme koduyla eşleştir"
    python phone_check.py --connect 192.168.1.23:41234      # eşleştirmeden sonra ana ekrandaki IP:port ile
"""
import re
import sys

from skills import phone as P


def step(ok, text):
    print(("✓ " if ok else "✗ ") + text)
    return ok


def main():
    args = sys.argv[1:]
    if "--app-pair" in args or "--app-test" in args:
        import phonelink  # noqa: PLC0415
        if "--app-pair" in args:
            serial, err = P.pick_device()
            print(phonelink.pair(P.adb_path(), serial, P._run) if serial else err)
        else:
            ok, msg = phonelink.send("ping", ttl=30)
            print(("✓ Telefona gönderildi: bildirim gelmeli. Gelmezse uygulamayı aç, pil/otomatik başlatma ayarlarına bak." if ok else "✗ " + msg))
        return 0
    if "--wifi" in args:
        print(P.setup_wifi())
        return 0
    if "--pair" in args:
        i = args.index("--pair")
        print(P.pair_wifi(args[i + 1] if len(args) > i + 1 else "", args[i + 2] if len(args) > i + 2 else ""))
        return 0
    if "--connect" in args:
        print(P.connect_wifi(args[args.index("--connect") + 1] if len(args) > args.index("--connect") + 1 else ""))
        return 0
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
