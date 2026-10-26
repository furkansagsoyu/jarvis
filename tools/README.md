# tools/ — tanılama, ölçüm ve kurulum

Jarvis çalışırken gerekmezler; kök klasörden çalıştırılır (`python tools/<ad>.py`).

| Betik | Ne yapar |
|---|---|
| `install_app.py` | Uygulama menüsüne JARVIS simgesi (`--desktop` masaüstüne de, `--remove`, `--status`). |
| `autostart.py` | Oturum açılışında başlatma: `--install` (pano + ada + uyanma), `--remove`, `--status`. |
| `browser_sites.py` | Tarayıcının izinli site listesi: `list`, `add <site>`, `remove <site>`, `reset`. |
| `router_check.py` | Bulut anahtarı ve gizlilik kapısı: `--init` (data/keys.env şablonu), argümansız deneme. |
| `phone_check.py` | Telefon/ADB/FCM tanılama ve ayar: `--wifi`, `--pair`, `--connect`, `--app-pair`, `--app-test`, `--via`, `--alerts`, `--detail`. |
| `code_check.py` | Kod ajanının bubblewrap kutusunu dener (internet yok, anahtar yok, sistem yazılamaz). |
| `ram_report.py` | Bellek raporu ve ölçüm: `--watch SN --label X` (`RAM.md` rehberi). Sistem bakım ajanı da kullanır. |
| `tool_check.py` | Gerçek modelle araç seçimi ölçümü (`check_all.py --model` çağırır). |
| `tool_diag.py` | Araç seçimi tanısı; ortak cümle listesi (`CASES`) `tool_check` ve `model_bench` tarafından kullanılır. |
| `model_bench.py` | Yerel modelleri hız ve bellek açısından karşılaştırır (`--models … --repeat N`). |
