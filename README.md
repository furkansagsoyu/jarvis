# Jarvis

Tamamen **yerel**, ücretsiz, Türkçe konuşan bir sesli bilgisayar asistanı. Konuşmayı yazıya çeviren, anlayan, bilgisayarı sizin için
kullanan ve cevabı sesli veren bir hat: ses, metin ve görüntü bu makineden dışarı çıkmaz (web araması, Telegram ve siz istediğinizde
açılan siteler hariç).

```
"Hey Jarvis" ──► Whisper (STT) ──► Gemma (araç çağıran LLM) ──► EMA Lightning (TTS) ──► hoparlör
                                       │
                          beceriler: dosyalar, tarayıcı, ekran, kamera, fare/klavye, hatırlatıcılar, ajan modu...
```

Bu proje bir öğrenci projesidir ve bir ev bilgisayarında çalışacak şekilde yazıldı. Linux (X11) için geliştirildi ve orada test edildi.

## Neler yapabiliyor

| Alan | Örnek cümle |
|---|---|
| Sohbet ve araç çağırma | "Saat kaç?", "Yarın hava nasıl?", "Sesi yüzde otuza ayarla" |
| Dosyalar | "rapor.pdf dosyasını oku", "masaüstünde faturaları bul", "onu özetle" |
| Güvenli dosya işlemi | taşıma ve çöpe atma sesli onayla çalışır, "geri al" ile geri döner |
| Hatırlatıcılar, hafıza | "20 dakika sonra beni uyar", "şunu hatırla…" (yeniden başlatınca da durur) |
| Web | "Ankara'nın nüfusunu araştır" (sonuçları okur ve özetler) |
| Tarayıcı kontrolü | "github.com'a git", "sayfayı oku", "arama kutusuna jarvis yaz ve ara" |
| Ekran ve kamera görüşü | "Ekranda ne var?", "Kameraya bak", "Elimde ne var?" (yerel görsel model) |
| Fare ve klavye | "Fareyi sağa götür", "tıkla", "klavyeden merhaba yaz", "Enter'a bas" |
| Ajan modu | "Ajan modu: Wikipedia'da Ankara'yı araştır ve özetle" (planı okur, onay ister) |
| Sistem | "CPU kaç?", "Pil kaç?", "Sistem durumu nasıl?", düşük pil uyarısı |
| Günaydın özeti | "Günaydın" (tarih, hava, hatırlatıcılar), sabahları kendiliğinden |
| Uzaktan | Telegram botu üzerinden metin komutları (hassas araçlar kapalı) |
| Konfor | Eller serbest mod, durum penceresi ve tepsi simgesi, Sustur, otomatik başlatma |

## Güvenlik tasarımı

Bilgisayarı kontrol eden bir yapay zekâ riskli bir şeydir. Bu yüzden güvenlik modelin iyi niyetine bırakılmadı, **kodda** uygulanıyor:

- **Onay kapısı kodda.** Tıklama, yazma, dosya taşıma/silme gibi riskli işlemlerde araç işi yapmaz, bekleyen bir işlem kaydeder. Bir sonraki
  cümleniz modele gitmeden "evet / hayır" olarak değerlendirilir. Modelin "onayladım" demek gibi bir yolu yoktur; 60 saniye sonra işlem düşer.
- **Dış içerik komut değildir.** Dosya, web sayfası, ekran ve kamera görüntüsü okunduktan sonra modelin sonraki turunda **araç listesi boştur**;
  içeriğe gömülü "dosyaları sil" gibi talimatlar bir şey çalıştıramaz. Ekran ve kamera modeli araçsız çağrılır.
- **Yasaklı yüzeyler.** Terminal, parola yöneticisi, banka/ödeme/giriş ve `sudo`/polkit pencerelerine yazma, tıklama ve tuş basma reddedilir.
  Banka, ödeme, e-posta ve giriş sayfaları tarayıcıda açılmaz; parola ve kart alanlarına yazılmaz; yerel ağ adresleri ve `file://` kapalıdır.
- **Tarayıcı ayrı ve boştur.** Kendi profilini kullanır (gerçek tarayıcınızın oturumlarına erişmez), sitelere `data/browser_sites.json`
  izin listesiyle gider, listede olmayan siteyi açmadan önce sorar. İndirme kapalıdır.
- **Ajan modu kısıtlıdır.** Plan yalnızca sizin cümlenizden çıkar, baştan sesli okunur ve onaylanır. Her adımda model yalnızca planın o adımdaki
  tek aracını çağırabilir; en fazla 8 adım; bir dosya okunduktan sonra internete giden adım ayrıca onay ister; aynı araç 3 hata verirse görev durur.
- **Dosya okuma sınırlıdır.** Yalnızca ev dizininiz; gizli klasörler, `.env` ve anahtar dosyaları engelli. Silme kalıcı değildir (çöp kutusu).
- **Telegram yalnızca kayıtlı sohbetten** gelen mesajlara cevap verir; dosya okuma, ekran, kamera, tarayıcı ve fare/klavye uzaktan kapalıdır.
- **Kişisel veri git dışındadır.** Token, hafıza, oturum ve hatırlatıcılar `data/` içinde tutulur; bu klasörün kendi `.gitignore`'u vardır.

> **Uyarı:** Bu yazılım bilgisayarınızda gerçek eylemler yapar. Kendi sorumluluğunuzda kullanın. Önce `python check_all.py` çalıştırın,
> riskli becerileri (fare/klavye, ajan) önemli bir şeyle uğraşmıyorken deneyin.

## Gereksinimler

Geliştirme ve test ortamı: **Linux Mint (Cinnamon, X11)**, Python 3.12, NVIDIA RTX 3070 Ti Laptop (8 GB VRAM), 15 GB RAM.

- NVIDIA GPU (8 GB VRAM ile çalışacak şekilde ayarlandı: Whisper ~2 GB, Gemma ~5 GB, TTS CPU'da)
- [Ollama](https://ollama.com/download) ve modelleri `gemma4:e4b` (ana), `qwen3:8b` (yedek)
- `portaudio19-dev`, isteğe bağlı `xdotool` (fare/klavye), `ffmpeg` (webcam yedeği)
- Fare/klavye kontrolü X11 ister; Wayland'de çalışmaz

## Kurulum

```bash
sudo apt install -y python3-venv python3-dev portaudio19-dev xdotool
git clone https://github.com/furkansagsoyu/jarvis.git && cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# GPU'da faster-whisper için (CUDA 12 kütüphaneleri):
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12

ollama pull gemma4:e4b
ollama pull qwen3:8b            # yedek model
python -c "import openwakeword; openwakeword.utils.download_models()"   # "Hey Jarvis" modeli

# isteğe bağlı
playwright install chromium     # tarayıcı kontrolü
```

## Kullanım

```bash
python main.py --wake --ui             # eller serbest: "Hey Jarvis", durum penceresi ve tepsi simgesi
python main.py                         # Enter ile konuş, Enter ile bitir
python main.py --text                  # mikrofon yerine klavyeden yaz (hata ayıklama)
python main.py --list-speakers         # hoparlörleri listele, --speaker <numara|ad> ile seç
python main.py --help                  # tüm bayraklar
```

Çıkmak için "görüşürüz" deyin ya da `q` yazın. "Konuşmayı sıfırla" yeni bir konuşma başlatır.

| Ayar | Komut |
|---|---|
| Otomatik başlatma (oturum açılışında) | `python autostart.py --install` |
| Telegram köprüsü | `python telegram_bot.py --setup`, sonra `python main.py --telegram` |
| Tarayıcı için izinli siteler | `python browser_sites.py list / add <site> / remove <site>` |
| Sabah özeti | `python main.py --morning` (05–12 arası günde bir kez) |

## Test

```bash
python check_all.py --quick            # mantık testleri (model ve donanım gerekmez)
python check_all.py --env              # ortam: kütüphaneler, Ollama, GPU belleği, kamera, xdotool...
python check_all.py --vision --agent   # gerçek modelle ekran, kamera ve ajan planı
python check_all.py --model            # gerçek model araç seçimi
```

Tarayıcı testleri gerçek bir Chromium ile yerel test sitesinde çalışır. Fare/klavye testleri sahte `xdotool` kullanır.

## Proje yapısı

```
main.py          konuşma döngüsü (mikrofon → STT → beyin → TTS)
brain.py         model, araç çağırma, kural tabanlı hızlı yol, oturum, bağlam özetleme
agent.py         ajan modu (planla, onayla, adım adım yürüt)
skills/          beceriler: her dosya kendini tanımlar ve otomatik yüklenir
  _confirm.py    onay kapısı
  browser.py     Playwright ile tarayıcı kontrolü
  desktop_input.py  fare/klavye (xdotool)
  screen.py, camera.py, files.py, web.py, reminders.py, hardware.py, ...
stt.py, tts.py, wake.py     konuşma tanıma, sentez, uyanma sözcüğü
ui.py, telegram_bot.py, autostart.py
check_all.py     tek komutlu test ve ortam kontrolü
```

Yeni bir beceri eklemek için `skills/` altına, `SKILLS` listesi tanımlayan bir dosya koymak yeterlidir.

## Tasarım notları

- **Yerel LLM ile araç çağırma kırılgandır.** Çok araçlı ve uzun istemlerde küçük model aracı seçemez. Bu yüzden sık kullanılan komutlar
  modele sorulmadan kural tabanlı **hızlı yoldan** çalışır, sistem istemi kasıtlı olarak kısa tutulur ve değiştirmeden önce
  `tool_check.py` ile ölçülür.
- **TTS CPU'da çalışır** (EMA Lightning), çünkü 8 GB VRAM Whisper ve Gemma ile birlikte başka bir şeye yetmiyor.
- **Sesle araya girme yok.** Hoparlör sesi mikrofona karışır; Enter ya da arayüzdeki Sustur ile kesilir.

## Bilinen sınırlar

- Yalnızca Türkçe için ayarlandı ve tek bir donanımda denendi.
- Fare, imleç konumuna göre çalışır; ekrandaki bir öğeyi görüntüden bulup tıklamaz.
- Gemma küçük bir modeldir; karmaşık ajan görevlerinde plan dışına çıkabilir (bu yüzden plan onaylanır ve adımlar kısıtlıdır).

## Teşekkür

Fikirler [Mark-LV](https://github.com/FaithMakes/Mark-LV) projesinin özellik listesinden esinlenmiştir (kod alınmadı).
Kullanılan açık kaynak bileşenler: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Ollama](https://ollama.com),
[openWakeWord](https://github.com/dscripka/openWakeWord), EMA Lightning, [Playwright](https://playwright.dev), Gemma ve Qwen modelleri
(kendi lisanslarıyla).

## Lisans

[MIT](LICENSE). Kullanılan modellerin lisansları ayrıdır.
