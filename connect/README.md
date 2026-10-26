# connect/ — uzaktan erişim ve telefon

| Dosya | Görevi |
|---|---|
| `telegram_bot.py` | Telegram köprüsü: yalnızca kayıtlı sohbete cevap verir, kısıtlı kipte çalışır. |
| `remote.py` | Telefon web sayfası (`/m`) erişimi: ayrı anahtar, Host denetimi, kilitleme, Tailscale yardımcıları. |
| `remote_setup.py` | Telefon erişimini kurma/yönetme komutu. |
| `phonelink.py` | Jarvis Telefon uygulamasına Firebase (FCM) ile HMAC imzalı komut; eşleştirme. |

Telefon araması becerisi `skills/phone.py`'de, Flutter uygulaması `phone_app/`'te.

## Kısıtlı uzaktan kip (Telegram ve telefon sayfası)
Dosya okuma/arama, hafızadan okuma/silme, ekran, kamera, tarayıcı, fare/klavye, kod ajanı, telefon araması, MCP ve sistem bakımı
uzaktan kapalıdır. **Uzaktan onay verilemez:** bilgisayarda bekleyen bir işlemi ya da planı uzaktan "evet" ile çalıştıramazsın;
yalnızca uzaktan başlattığın işlemin onayı uzaktan verilir.

## Telegram
```bash
python connect/telegram_bot.py --setup      # token'ı sorar, botuna mesaj yazmanı ister, sohbet kimliğini kaydeder
python main.py --wake --telegram
```

## Telefondan Jarvis (mobil sayfa, Tailscale)
Telefon tarayıcısında yazışma, sesle konuşma, görevler/takvim ve durum. Bağlantı Tailscale'in özel ağı (tailnet) içinde kalır; ses
bilgisayardaki Whisper'da yazıya çevrilir.
1. Bilgisayara ve telefona Tailscale (aynı hesap); yönetim panelinde **MagicDNS** ve **HTTPS Certificates** açık.
2. `python connect/remote_setup.py` → `tailscale serve` ile yalnızca tailnet'e açar, telefon bağlantısını (varsa QR) yazar. Funnel açıksa kurulum reddedilir.
3. Bağlantıyı telefonda Chrome'da aç, "Ana ekrana ekle".

Yönetim: `--new-token` (anahtarı yenile), `--revoke` (kapat), `--status`. Telefonun anahtarı pano anahtarından ayrıdır, adreste `#` sonrasındadır (sunucuya/günlüğe gitmez); yanlış anahtar 1 dakika kilitler.

## Telefon araması (ADB)
USB hata ayıklama açık telefon: "Annemi ara", "0555 123 45 67'yi ara" (önce onay ister), "aramayı kapat", "telefon bağlı mı".
Rehber: "rehbere ekle: Annem 0555 123 45 67", "rehberi telefondan al" — yalnızca `data/contacts.json`'da kalır.
- Kablosuz: USB takılıyken bir kez `python tools/phone_check.py --wifi`; sonra aynı Wi-Fi'da otomatik bağlanır. Alternatif Android 11+: `--pair`, `--connect`. İki `adb` varsa `export JARVIS_ADB=/tam/yol/adb`.
- Numara yalnızca rakam ve baştaki `+`; `*#…` kodları ve komut ekleme reddedilir. Tanılama: `python tools/phone_check.py`.

## Jarvis Telefon uygulaması (FCM)
ADB olmadan internet üzerinden: "aramayı kapat", "telefonu yarın 14'te çaldır". Hatırlatıcı ve takvim etkinlikleri telefonda da alarm
olur (`--alerts on|off`; `--detail generic` iken Firebase'e metin gitmez). Mesajda numara yok; HMAC imzalı, 2 dakikadan eski/tekrar
eden mesaj reddedilir; gizli anahtar ADB ile yazılır, ağdan geçmez.
Kurulum: `phone_app/KURULUM.md`. Eşleştirme `python tools/phone_check.py --app-pair`, deneme `--app-test`, arama yolu `--via auto|app|adb`.
