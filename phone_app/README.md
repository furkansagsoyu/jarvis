# phone_app/ — Jarvis Telefon (Android)

Flutter + Kotlin uygulaması (`com.furkan.jarvisphone`). Bilgisayardaki Jarvis, Firebase Cloud Messaging ile **HMAC imzalı** komut yollar;
uygulama doğrular ve yürütür: arama yapma/kapatma, alarm kurma, hatırlatıcı ve takvim alarmları. Mesajda numara yok; numarayı telefon
kendi rehberinden bulur. 2 dakikadan eski ya da tekrar eden mesaj reddedilir.

- Kurulum adım adım: [KURULUM.md](KURULUM.md)
- Eşleştirme (bir kez, telefon ADB ile bağlıyken): `python tools/phone_check.py --app-pair`; deneme: `--app-test`
- Bilgisayar tarafı: `connect/phonelink.py`, `skills/phone.py` (bkz. `connect/README.md`)
- `android/app/google-services.json` git'e girmez (kullanıcı kendisi koyar).
