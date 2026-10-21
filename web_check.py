"""Web arama arka uçlarını KENDİ bilgisayarında dener (hangisi çalışıyor?).

    python web_check.py "RTX 3070 Ti fiyatı"
"""
from __future__ import annotations

import sys
import time

from skills import web


def main() -> int:
    q = " ".join(sys.argv[1:]) or "RTX 3070 Ti fiyatı"
    print(f"Sorgu: {q}\n")
    ok = 0
    for name, fn in web.BACKENDS:
        t0 = time.time()
        try:
            res = fn(q)
            err = "" if res else "sonuç yok (anahtar yok / engellendi / boş)"
        except Exception as exc:  # noqa: BLE001
            res, err = [], f"{type(exc).__name__}: {str(exc)[:80]}"
        ms = int((time.time() - t0) * 1000)
        if res:
            ok += 1
            print(f"✓ {name:9} {ms:5} ms  {len(res)} sonuç  ilki: {res[0][0][:50]} — {res[0][1][:90]}")
        else:
            print(f"✗ {name:9} {ms:5} ms  {err}")
    print(f"\n{ok} arka uç çalışıyor." + ("" if ok else " Hiçbiri çalışmıyor: ağ/güvenlik duvarı ya da engel olabilir."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
