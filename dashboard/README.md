# dashboard/ — Komut Merkezi panosu ve telefon sayfası

| Dosya | Görevi |
|---|---|
| `server.py` | Yalnızca `127.0.0.1`'de HTTP sunucusu; her açılışta rastgele oturum anahtarı, Host denetimi. Telefon uçları ayrı anahtarla. |
| `state.py` | Panel sağlayıcıları (`@provider("ad")`): durum, sistem, model, hafıza, ajanda, ajanlar, araçlar, ada anlık durumu. |
| `window.py` | Pano penceresi (Qt/QtWebEngine → pywebview → Chromium `--app`) ve tepsi simgesi (Panoyu aç, Adayı aç, Jarvis'i kapat). |
| `static/` | `index.html`, `app.js`, `style.css` = pano; `m.html`, `m.js`, `m.css` = telefon sayfası. |

## Uçlar
| Uç | Ne yapar |
|---|---|
| `GET /api/state` | Panonun tüm verisi. |
| `POST /api/cmd` | `{"id": …}` hızlı komut, `{"say": …}` Jarvis'e cümle, `{"theme": …}`, `{"island": {"key", "value"}}`. |
| `/api/agenda`, `/api/conv`, `/api/sessions` | Görev/takvim işlemleri, konuşma günlüğü ve arama. |
| `GET /api/island`, `POST /api/island/answer` | Ada durumu; Evet/Hayır (yalnızca ekrandaki soru hâlâ bekliyorsa). |
| `/m`, `/api/m/{state,chat,voice,cmd,agenda}` | Telefon sayfası (ayrı anahtar, kısıtlı kip; bkz. `connect/README.md`). |

Yerel uçlar `X-Token` başlığı ister (tarayıcı başka siteden bu başlığı gönderemez → CSRF yok). Tehlikeli işlemler panodan da onay ister.
Panoda HTML olarak metin eklenmez (XSS kuralı; `tests/test_dashboard.py` denetler).

## Yeni panel / sayfa
`state.py`'de `@provider("ad")` ile veri üreten fonksiyon → `static/app.js` içinde `PANELS` ve `index.html`'e çizim; yeni sayfa için `VIEWS`.
Temalar: cyan (varsayılan), amber, yeşil, mor, açık (Ayarlar > TEMA). Ada ayarları Ayarlar > ADA'da.
