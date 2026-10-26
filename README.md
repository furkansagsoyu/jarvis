# Jarvis

Tamamen **yerel**, ücretsiz, **Türkçe** konuşan sesli bilgisayar asistanı. "Hey Jarvis" dersin; konuşmanı bilgisayarındaki Whisper yazıya
çevirir, yerel dil modeli (Gemma) ne istediğini anlar, gerekirse bilgisayarı senin için kullanır (dosya, tarayıcı, takvim, telefon…) ve
cevabı sesli verir. Ses, metin ve görüntü makineden çıkmaz; ücretsiz bulut modelleri yalnızca kişisel veri içermeyen zor işlerde ve bir
gizlilik kapısından geçerek kullanılır. Riskli her eylem senin sesli "evet"ine bağlıdır; bu kural modelin iyi niyetine değil **koda**
bırakılmıştır.

```
"Hey Jarvis" ─► Whisper (STT) ─► Gemma + hızlı yol (araç seçimi) ─► beceriler ─► EMA Lightning (TTS) ─► hoparlör
                                        │                                ▲
                          ajan / ekip modu (plan + onay)        pano · üst kenar adası · Telegram · telefon
```

Bir öğrenci projesidir; Linux Mint (X11), RTX 3070 Ti (8 GB VRAM) ve 15 GB RAM'li bir dizüstünde geliştirildi ve denendi.

## Neler yapabiliyor

| Alan | Örnek |
|---|---|
| Sohbet ve günlük işler | "Saat kaç?", "Yarın hava nasıl?", "Sesi yüzde otuza ayarla", "Günaydın" (sabah özeti) |
| Takvim, görev, hatırlatıcı | "Yarın 14'te toplantı ekle", "görev ekle: raporu bitir, cuma", "20 dakika sonra beni uyar" |
| Hafıza | "Şunu hatırla: kedimin adı Pamuk", "kedimin adı neydi" (Türkçe ekleri tolere eden yerel arama) |
| Dosyalar | "rapor.pdf'yi oku", "masaüstünde faturaları bul", taşıma/çöpe atma onaylı ve "geri al" ile geri döner |
| Web ve tarayıcı | "Ankara'nın nüfusunu araştır", "github.com'a git", "sayfayı oku", "Sezen Aksu şarkısı aç" |
| Ekran, kamera, fare/klavye | "Ekranda ne var?", "Kameraya bak", "tıkla", "klavyeden merhaba yaz" (onaylı) |
| Ajanlar | "ajan modu: …", "ekip: …", "araştır: …", "kod: hesap makinesi yaz" (Kod Ajanı + Denetçi), "proje: …" (Mimar parçalar) |
| Sistem | "CPU kaç?", "Pil kaç?", "Sistem bakımı yap" (bellek, disk, VRAM, modeller; düzeltmeler onaylı) |
| Telefon | "Annemi ara", "aramayı kapat", "telefonu yarın 14'te çaldır" (ADB ya da Jarvis Telefon uygulaması) |
| Uzaktan | Telegram ve telefon web sayfası (Tailscale) — kısıtlı kip, uzaktan onay yok |
| MCP | "mcp araçları", "mcp: zaman get_current_time …" (yalnızca senin eklediğin yerel sunucular) |
| Arayüz | Komut Merkezi panosu, üst kenar adası (büyüyen, otomatik gizlenen; Evet/Hayır), Çekirdek maskotu, 5 tema |

## Kurulum

```bash
sudo apt install -y python3-venv python3-dev portaudio19-dev xdotool bubblewrap
git clone https://github.com/furkansagsoyu/jarvis.git && cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12            # GPU'da Whisper için
ollama pull gemma4:e4b && ollama pull qwen3:8b               # ana ve yedek model (https://ollama.com)
python -c "import openwakeword; openwakeword.utils.download_models()"
playwright install chromium                                  # isteğe bağlı: tarayıcı kontrolü
```

## Kullanım

```bash
python main.py --wake --dash --island      # "Hey Jarvis" + pano + üst kenar adası (önerilen)
python main.py --text                      # klavyeden yaz (hata ayıklama)
python main.py --help                      # tüm bayraklar
python tools/install_app.py                # menüye JARVIS simgesi
python tools/autostart.py --install        # oturum açılınca başlat
```
Çıkmak için "görüşürüz"; "konuşmayı sıfırla" yeni konuşma başlatır. Telegram, telefon ve bulut modelleri için ilgili klasörün README'sine bak.

## Güvenlik ilkeleri

- **Onay kapısı kodda:** riskli araç işi yapmaz, bekleyen işlem kaydeder; bir sonraki cümlen modele gitmeden evet/hayır sayılır. Model onay veremez; uzaktan da (Telegram/telefon) bilgisayardaki işlem onaylanamaz.
- **Dış içerik komut değildir:** dosya, web, ekran, kamera okunduktan sonra model o turda araç çağıramaz.
- **Yasaklı yüzeyler:** terminal, parola, banka/ödeme/giriş pencereleri ve Jarvis'in kendi pencerelerine tıklama/yazma reddedilir; tarayıcı ayrı profilde, izin listesiyle.
- **Kişisel veri buluta gitmez;** `data/` git dışında, 0700/0600. Kod ajanı internetsiz bubblewrap kutusunda, yalnızca `workspace/` içinde.

> Bu yazılım bilgisayarında gerçek eylemler yapar. Önce `python check_all.py` çalıştır; riskli becerileri önemli bir işle uğraşmıyorken dene.

## Klasörler

| Klasör | İçerik |
|---|---|
| kök | `main.py` (konuşma döngüsü), `app.py` (menü simgesi başlatıcısı), `check_all.py` (testler) |
| [`core/`](core/README.md) | beyin, ajan/ekip modu, model yönlendirici, gizlilik kapısı, bellek koruması, MCP istemcisi |
| [`voice/`](voice/README.md) | konuşma tanıma, ses sentezi, uyanma sözcüğü |
| [`skills/`](skills/README.md) | beceriler (araçlar) ve yeni beceri ekleme kuralları |
| [`desktop/`](desktop/README.md) | üst kenar adası, durum ve maskot eşlemesi |
| [`dashboard/`](dashboard/README.md) | Komut Merkezi panosu ve telefon sayfası |
| [`connect/`](connect/README.md) | Telegram, telefon web sayfası, telefon araması ve uygulaması |
| [`tools/`](tools/README.md) | kurulum, tanılama ve ölçüm betikleri |
| [`tests/`](tests/README.md) | modelsiz testler |
| [`assets/`](assets/README.md) · [`phone_app/`](phone_app/README.md) | simgeler ve maskot · Android uygulaması |

Bellek ve donanım ölçümleri: [`RAM.md`](RAM.md). Geliştirme notları: `HANDOFF.md`, `TASKS.md`.

## Test

```bash
python check_all.py --quick      # mantık testleri (model ve donanım gerekmez)
python check_all.py              # + ortam kontrolü
python check_all.py --model      # + gerçek modelle araç seçimi
```

## Bilinen sınırlar

- Yalnızca Türkçe için ayarlandı ve tek bir donanımda denendi; Windows desteği planlanıyor.
- Fare imleç konumuna göre çalışır, ekrandaki öğeyi görüntüden bulup tıklamaz. Fare/klavye X11 ister.
- Gemma küçük bir modeldir; karmaşık işlerde plan dışına çıkabilir (bu yüzden plan onaylanır, adımlar kısıtlıdır).

## Teşekkür

Fikir kaynakları (kod ya da görsel alınmadı): [Mark-LV](https://github.com/FaithMakes/Mark-LV) (özellik listesi),
[coucou](https://github.com/louis-cfm/coucou) (üst kenar adası fikri). Ada ve Çekirdek maskotu bu projeye özgüdür.

Kullanılan açık kaynak bileşenler ve hizmetler (her biri kendi lisansıyla): [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[openWakeWord](https://github.com/dscripka/openWakeWord), [Ollama](https://ollama.com) (Gemma, Qwen), [Groq](https://groq.com) (isteğe bağlı),
EMA Lightning ve Freya TTS, [Playwright](https://playwright.dev), Qt ([qtpy](https://github.com/spyder-ide/qtpy)), [pywebview](https://pywebview.flowrl.com),
[pystray](https://github.com/moses-palmer/pystray), SQLite FTS5, [bubblewrap](https://github.com/containers/bubblewrap),
[Model Context Protocol](https://modelcontextprotocol.io), Flutter, Firebase Cloud Messaging, [Tailscale](https://tailscale.com).

## Lisans

[MIT](LICENSE). Kullanılan modellerin lisansları ayrıdır.
