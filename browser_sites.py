#!/usr/bin/env python3
"""Jarvis tarayıcısının izinli site listesi (data/browser_sites.json).

    python browser_sites.py list
    python browser_sites.py add example.com
    python browser_sites.py remove example.com
    python browser_sites.py reset          # varsayılan listeye dön

Listede olmayan siteye gitmeden önce Jarvis onay ister. Banka, ödeme, e-posta ve giriş sayfaları listede olsa bile açılmaz.
"""
import sys

from skills import browser


def main():
    cmd, *rest = sys.argv[1:] or ["list"]
    sites = browser.load_sites()
    if cmd == "add" and rest:
        host = rest[0].lower().replace("https://", "").replace("http://", "").split("/")[0]
        if browser.is_blocked("https://" + host):
            raise SystemExit(f"{host} yasak türde (banka/ödeme/e-posta/giriş); eklenemez.")
        browser.save_sites(sites + [host])
    elif cmd == "remove" and rest:
        browser.save_sites([s for s in sites if s != rest[0].lower()])
    elif cmd == "reset":
        browser.save_sites(browser.DEFAULT_ALLOWED)
    elif cmd != "list":
        raise SystemExit(__doc__)
    print("\n".join(browser.load_sites()))


if __name__ == "__main__":
    main()
