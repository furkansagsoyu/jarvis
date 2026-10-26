# skills/ — beceriler (araçlar)

`_` ile başlamayan her dosya otomatik yüklenir ve bir `SKILLS` listesi tanımlar:
```python
SKILLS = [{"name": "get_time", "description": "Saati söyler. ...", "parameters": {...}, "run": get_time, "hidden": False}]
```
`run(**kwargs) -> str` döner; `description`'ın ilk cümlesi sistem istemindeki yetenek listesine girer (kısa tut).

## Yeni beceri eklerken
1. Varsayılan tercih **`hidden: True` + `core/brain.py` hızlı yol kuralı** (araç sayısı arttıkça Gemma'nın seçimi bozuluyor).
2. Riskli iş mi? Araç işi yapmaz, `_confirm.request(açıklama, run)` ile bekleyen işlem kaydeder; sonraki cümle modele gitmeden evet/hayır sayılır, 60 sn'de düşer.
3. Uzaktan kapatılmalı mı → `brain.REMOTE_BLOCKED`; dış içerik mi okuyor → `brain.UNTRUSTED_TOOLS`; modelin "yaptım" yalanı → `brain.ACTION_CLAIM`; ajan modunda kullanılacak mı → `core/agent.py` `ALLOWED/NETWORK/HELP`.
4. `tests/test_routes.py`'ye cümle → araç vakası ve becerinin kendi testi; panodaki Türkçe ad için `dashboard/state.TOOL_LABELS`.

## Yardımcılar
| Dosya | Görevi |
|---|---|
| `_confirm.py` | Onay kapısı (model onay veremez; `pending_info` yalnızca görüntü bilgisi). |
| `_store.py` | `data/` erişimi: güvenli kayıt (0600/0700), çalışma zamanı yolları. |
| `_trdate.py` | Türkçe tarih/saat ayrıştırma ("yarın 14'te", "cuma"). |
| `_undo.py` | Geri alma kaydı. `_phonenotify.py`: hatırlatıcıları telefona da gönderme. |

## Beceriler
| Dosya | Ne yapar |
|---|---|
| `agenda.py` | Takvim ve görevler (yerel; etkinliğe 10 dk kala uyarı). |
| `memory.py` | Hafıza: `data/memory.db` (SQLite FTS5, Türkçe harf katlama, bm25); eski `memory.json` göçte `.bak` olur. |
| `files.py`, `undo.py` | Dosya oku/bul/taşı/çöpe at (onaylı) ve geri al. Yalnızca ev dizini; gizli klasör ve anahtar dosyaları engelli. |
| `browser.py` | Playwright ile ayrı profilde tarayıcı; izin listesi (`tools/browser_sites.py`), şarkı/video oynatma; banka/ödeme/giriş sayfaları açılmaz. |
| `web.py` | Web araması. |
| `screen.py`, `camera.py` | Ekran ve kamera görüşü (yerel görsel model, araçsız çağrılır). |
| `desktop_input.py` | Fare/klavye (xdotool, onaylı); terminal, parola, banka ve Jarvis'in kendi pencereleri yasaklı yüzey. |
| `codeagent.py` | Kod ajanı araçları (`workspace/`, bubblewrap kutusu). |
| `phone.py` | Telefon araması, rehber, alarm (ADB ya da uygulama). |
| `maintenance.py` | Sistem bakım raporu ("sistem bakımı yap"); kendi başına değişiklik yapmaz. |
| `mcp.py` | MCP araçları (gizli, her çağrı onaylı). |
| `schedule.py` | Zamanlanmış görev kur (onaylı) / listele / sil; çalıştırma `core/scheduler.py` + `main.py`. |
| `reminders.py`, `briefing.py`, `weather.py`, `clock.py`, `battery.py`, `hardware.py`, `volume.py`, `brightness.py`, `apps.py`, `help.py` | Hatırlatıcı, günaydın özeti, hava, saat/tarih, pil, donanım, ses, parlaklık, uygulama açma, yetenek listesi. |
