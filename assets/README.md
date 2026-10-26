# assets/ — görseller

| Dosya | Ne |
|---|---|
| `jarvis.svg`, `jarvis.png`, `jarvis-64.png`, `jarvis-256.png` | Uygulama simgesi (menü, pencere, tepsi). |
| `cekirdek.svg` | **Çekirdek** maskotu (animasyonlu, özgün). |
| `cekirdek_demo.html` | Maskotun altı durumunun önizlemesi (tarayıcıda aç). |

## Çekirdek maskotu
- Satır içi (inline) gömülmelidir: `<img>` içinde durum değişmez. Durum, kök `svg` öğesinin `data-state`'i: `idle | listening | thinking | speaking | alert | error`.
- Sayfaya gömülmeye uygundur: tüm kurallar `svg.cekirdek` kapsamında, değişken/animasyon/kimlik adları `ck-` önekli (sayfanın adlarıyla çakışmaz). Tema rengi dışarıdan `--ck-tema`, `--ck-tema2`, `--ck-tema-bg` ile verilir; uyarı/hata kendi rengini korur. `prefers-reduced-motion` desteklenir.
- Pano `/static/cekirdek.svg` adresinden bu dosyayı sunar (kopya yok). Ada aynı geometriyi `desktop/island.py`'de kare kare çizer.
- XML yorumlarında `--` kullanma (dosya geçersiz olur).
