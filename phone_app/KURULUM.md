# Jarvis Telefon – kurulum

1. **Firebase:** console.firebase.google.com → projen → Android uygulaması, paket adı `com.furkan.jarvisphone`.
   - `google-services.json` dosyasını `phone_app/android/app/google-services.json` olarak koy.
   - Proje ayarları → Hizmet hesapları → "Yeni özel anahtar oluştur": inen `.json` dosyasını `data/fcm_service_account.json` olarak koy (bilgisayarın telefona mesaj atma anahtarı; kimseyle paylaşma, git'e girmez).
2. Bilgisayarda: `pip install google-auth requests`
3. Uygulamayı yükle (telefon USB ya da kablosuz ADB ile bağlı): `cd phone_app && flutter run --release`
4. Telefonda uygulamayı aç, izinleri ver, pil kısıtlamasını kapat, Xiaomi'de "Otomatik başlatma"yı aç.
5. Eşleştir (bir kez): `python tools/phone_check.py --app-pair`, sonra `python tools/phone_check.py --app-test` (telefona bildirim gelmeli).
6. Dene: kabloyu çıkar, Jarvis'e "Anılinho'yu ara" de, onayla. "Telefonu 2 dakika sonra çaldır, deneme" de.

Sorun giderme: uygulama ekranındaki "Son olaylar" listesi her komutun sonucunu gösterir (ör. "REDDEDİLDİ: imza geçersiz" = yeniden eşleştir).
