"""Bulut modeli anahtarını ve yönlendiriciyi KENDİ bilgisayarında dener.

    python router_check.py --init     # data/keys.env şablonunu oluşturur (anahtarını oraya yazarsın; git'e gitmez)
    python router_check.py            # anahtar var mı, Groq cevap veriyor mu, gizlilik kapısı çalışıyor mu

Anahtarı sohbete ya da komut satırına YAZMA; yalnızca data/keys.env içine.
"""
from __future__ import annotations

import sys
import time

import privacy
import router


def main() -> int:
    if "--init" in sys.argv:
        p = router.init_env_file()
        print(f"Hazır: {p}\nBu dosyayı bir metin düzenleyiciyle aç (örn. xed {p}), GROQ_API_KEY= satırının sonuna anahtarı yapıştır, kaydet.")
        return 0
    r = router.Router()
    st = r.status()
    print("Okunan anahtar dosyaları:", ", ".join(router.load_env()) or "yok (ortam değişkenleri kullanılır)")
    for p in st["providers"]:
        print(f"- {p['label']}: {p['state']}; modeller: {', '.join(m['name'] for m in p['models'])}")
    if not r.ready():
        print("\nHiçbir sağlayıcı hazır değil. Önce: python router_check.py --init  ve anahtarı data/keys.env'e yaz.")
        return 1
    # gizlilik kapısı (ağa çıkmadan)
    try:
        r.chat([{"role": "user", "content": "şifrem: kedi1234"}])
        print("HATA: parola içeren mesaj engellenmedi!")
        return 2
    except privacy.Blocked as b:
        print(f"Gizlilik kapısı: parola içeren mesaj engellendi ({b.text}) ✓")
    # gerçek çağrı
    t0 = time.time()
    try:
        rep = r.chat([{"role": "user", "content": "Yalnızca 'tamam' yaz."}], max_tokens=200, effort="low")
    except router.Unavailable as e:
        print(f"Bulut cevap vermedi: {e}")
        return 3
    print(f"Bulut cevabı ✓  model: {rep.provider}/{rep.model}  süre: {time.time() - t0:.1f} sn  jeton: {rep.tokens_in}+{rep.tokens_out}  cevap: {rep.text[:80]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
