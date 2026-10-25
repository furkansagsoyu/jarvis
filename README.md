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

## Model yönlendirici (ücretsiz bulut modelleri)

Yerel model (Ollama) varsayılandır ve kişisel her şeyi o yapar. Zor işler için (kod, plan, genel sorular) **ücretsiz** bulut modelleri yedek zincirle kullanılır.

```bash
python router_check.py --init     # data/keys.env şablonu (git'e gitmez); GROQ_API_KEY= satırına anahtarı yaz
python router_check.py            # anahtar ve gizlilik kapısı denemesi
```
- Kullanım: "bulut: python'da sözlük nasıl sıralanır" (yalnızca bu cümle gider; geçmiş, hafıza, ekran eklenmez).
- **Gizlilik kapısı** (`privacy.py`): parola/anahtar/e-posta/telefon/adres/kart/IBAN/T.C. no içeren hiçbir şey buluta gitmez; hafıza, konuşma kaydı, ekran, kamera hiç gönderilmez. Ayarlar > Bulut modelleri ile tamamen kapatılabilir.
- Sınırlar: Groq ücretsiz katmanında dakikada ~8K token vardır; büyük girdi hiç gönderilmeden reddedilir. 429'da sıradaki modele geçilir.
- Sağlayıcı eklemek (OpenAI uyumlu herhangi biri): `data/models.json`
  ```json
  {"providers": {"mistral": {"label": "Mistral", "base_url": "https://api.mistral.ai/v1", "key_env": "MISTRAL_API_KEY", "models": ["mistral-small-latest"]}}}
  ```
  ve anahtarı `data/keys.env`'e yaz. Model adlarını sağlayıcının güncel listesinden doğrula.

## Ekip modu (çoklu ajan)

Çok adımlı işleri uzman ajanlar yapar: **Planlayıcı → Araştırma Ajanı / Dosya Ajanı / Kod Ajanı / Bakım Ajanı → Yazar**. Bakım Ajanı (sistem sağlık raporu) Dosya Ajanı gibi yalnızca yerelde çalışır. Her ajan yalnızca kendi rolünün araçlarını kullanır.

- Başlatma: **"ekip: <görev>"** (planı model çıkarır) ya da **"araştır: <konu>"** (hazır plan: Araştırma + Yazar). Plan baştan okunur, tek "evet" ile başlar; riskli adımlar kendi onayını ister.
- Model seçimi her çağrıda yapılır: **bağlam temizse ücretsiz bulut** (güçlü model), değilse ya da bulut yoksa **yerel**. Kişisel veri okuyan bir görev (Dosya Ajanı) ve ona bağlı her görev (Yazar dahil) yalnızca yerelde çalışır; sonucu buluta gitmez. Web'den gelen içerik buluta gidebilir (herkese açık kaynak).
- Güvenlik ajan modundakiyle aynıdır: plan yalnızca senin cümlenden çıkar, araç sonuçları "yalnızca veri" sayılır, rol dışı araç çağrılamaz, dosya okunduktan sonra internete giden adım onay ister. En fazla 5 görev ve 10 araç çağrısı.
- Görevler sırayla çalışır (ücretsiz bulut limiti paralel çağrıya yetmez). Panoda Ajanlar sekmesi canlı durumu gösterir; `data/team_runs.jsonl` yalnızca özet tutar (sonuç metni yok).

## Kod ajanı

"**kod: bir hesap makinesi yaz**" dersin; plan okunur, "başla" dersin. Kod Ajanı (ücretsiz bulut modeli, kişisel veri varsa yerel) küçük adımlarla kod yazar, çalıştırır, hata çıkarsa düzeltir; ardından **Denetçi** projeyi ayrı bağlamda (yazanın konuşmasını görmeden) okuyup kendisi çalıştırır ve yalnızca düzeltilmesi gereken bulguları bildirir; sonucu Yazar sesli özetler. Kod `workspace/<proje>/` klasöründe kalır (git'e girmez); beğendiğini kendin projene kopyalarsın.

- Dosya araçları yalnızca o proje klasöründe çalışır (mutlak yol, `..`, `~`, gizli dosya, sembolik bağ kaçışı, izinsiz uzantı reddedilir; boyut/sayı sınırı var). Gerçek projelerine ve ev klasörüne erişemez.
- Kod **bubblewrap güvenli kutusunda** çalışır: internet yok, ev klasörün/anahtar dosyaların görünmez, ortam değişkenleri temiz, 30 sn süre sınırı. Kutu yoksa her çalıştırma onay ister (`sudo apt install bubblewrap`).
- Yalnızca `python`, `python3`, `pytest`, `node` çalıştırılabilir (kabuk yok). Kutuyu denemek için: `python code_check.py`.
- **Büyük istekler için Mimar:** "**proje: harcamalarımı takip eden komut satırı uygulaması yaz**" dersin. Mimar isteği kod ajanının sınırlarına uyan en fazla 4 parçaya böler (parça başı en fazla 2 dosya, dosya başı ≈120 satır, dosya arayüzleriyle); plan sesli okunur, tek "evet" ile parçalar sırayla aynı proje klasöründe yazılır, her kod ajanı mimarın tasarımını görür; sonda Denetçi tüm projeyi çalıştırır. Mimarın verdiği yollar kodda doğrulanır (kaçış/mutlak yol atılır, aynı dosya iki parçaya verilmez).
- Denetçi dosya yazamaz (yalnızca `code_list/code_read/code_run`). Hükmü kod belirler: bulgu varsa "geçti" sayılmaz, programı kendisi hiç çalıştırmadıysa "geçti" kabul edilmez (doğrulanamadı). İstemezsen: "**kod: denetimsiz, …**". Hüküm `data/team_runs.jsonl` özetine de yazılır.
- Yerel modelin bozuk JSON'u (kaçışsız tırnak, eksik/fazla parantez, tek cevapta birden çok çağrı) kodda onarılır; dizge ortasında kesilmiş bir `code_write` yarım dosya yazmasın diye reddedilir. Aynı araç çağrısı tekrarlanmaz, bir dosya çalıştırılmadan en fazla 2 kez yazılır.
- Ücretsiz bulutun küçük girdi sınırı nedeniyle uzun döngülerde eski adımlar kısa özete çevrilir; ajan dosyanın güncel halini `code_read` ile görür.

## Üst kenar adası

`--island` ile (otomatik başlatma ve menü simgesi bunu varsayılan olarak açar; eski kurulumda `python autostart.py --install` ile yenile) ekranın üst ortasında, her zaman üstte duran küçük bir çubuk açılır (`island.py`, Qt). Boştayken yalnızca durumu gösterir; riskli bir işlem onayı ya da ajan/ekip planı beklerken genişler: soru, kalan süre, **Evet / Hayır**.

- Düğmeler sesli "evet/hayır" ile **aynı yoldan** geçer (pano sunucusu → Brain → onay sınıflandırma); onay kapısı değişmez.
- Her bekleyen işlemin bir kimliği var: ekrandaki soru değiştiyse eski soruya basılan Evet yeni işlemi onaylamaz.
- Ada odak almaz (klavyeyle tetiklenemez) ve fare/klavye aracı Jarvis'in kendi pencerelerine (ada, pano) tıklamaz/yazmaz: model kendi onayını veremez.
- Pano sunucusuna yalnızca 127.0.0.1 üzerinden, oturum anahtarıyla bağlanır. Fikir [coucou](https://github.com/louis-cfm/coucou)'dan (MIT) alındı; kod ve görseller bu projeye özgüdür.

## MCP araçları (yerel sunucular)

Jarvis, [Model Context Protocol](https://modelcontextprotocol.io) sunucularına stdio üzerinden bağlanabilir (`mcp_client.py`, ek bağımlılık yok). Sunucuları **sen** kurar ve `data/mcp.json` dosyasına yazarsın. Denenmiş örnek (`mcp-server-time`, ayrı sanal ortamda; `freya` ortamı kirlenmez):

```bash
python -m venv ~/.local/share/jarvis/mcp-venv && ~/.local/share/jarvis/mcp-venv/bin/pip install mcp-server-time
```

```json
{"servers": {
  "zaman": {"command": "~/.local/share/jarvis/mcp-venv/bin/mcp-server-time", "args": ["--local-timezone", "Europe/Istanbul"],
            "tools": ["get_current_time", "convert_time"], "timeout": 30}
}}
```

- Kullanım: "**mcp araçları**" (sunucular ve araçlar), "**mcp: zaman get_current_time timezone=Europe/Istanbul**" ya da `mcp: <sunucu> <araç> {"json": "argüman"}`.
- **Her çağrı onay ister** (sunucu, araç ve argümanlar okunur); model onay veremez. Araçlar modelin şemasında yok, yalnızca bu açık komutla çalışır; sonuç modele gitmeden okunur.
- `tools` verilirse yalnızca o araçlar kullanılabilir (izin listesi). Sunucuya Jarvis'in ortamı/anahtarları geçmez (yalnızca PATH, HOME, LANG + `env`). Uzaktan (Telegram/telefon) kapalı.
- Yalnızca güvendiğin yerel sunucuları ekle: sunucu kendi işini kendi yetkinle yapar (dosyaya yazabilir, internete çıkabilir). Takılan sunucu zaman aşımında kapatılır, sonraki kullanımda yeniden başlar.

## Telefon araması (Android, ADB)

Telefonu USB ile bağla (Geliştirici seçenekleri → USB hata ayıklama açık, bilgisayara izin ver). Sonra: "**Annemi ara**", "**0555 123 45 67'yi ara**" (önce "…arayacağım, onaylıyor musun?" der, "evet" dersen arar), "**aramayı kapat**", "**aramayı aç**" (çalanı), "**telefon bağlı mı**".

- Rehber: "**rehbere ekle: Annem 0555 123 45 67**" ya da "**rehberi telefondan al**". Rehber yalnızca `data/contacts.json` dosyasında kalır; buluta, Telegram'a, ekip/ajan modlarına gitmez.
- Her arama sesli onay ister; model kendi kendine arayamaz. Numara yalnızca rakam ve baştaki `+` olabilir (`*#…` kodları ve komut ekleme reddedilir). Telegram'dan telefon komutları çalışmaz.
- "Aranıyor" denmeden önce telefonun gerçek arama durumu okunur; görüşme başlamadıysa dürüstçe söyler. Telefon doğrudan aramayı engellerse arama ekranını numarayla açar, yeşil tuşa sen basarsın.
- **Kablosuz (kablosuz kablo yok):** telefon USB'deyken bir kez `python phone_check.py --wifi` çalıştır; telefon Wi-Fi üzerinden ADB'ye açılır, adres `data/phone.json`'a kaydedilir. Sonra kabloyu çıkarsan da (aynı Wi-Fi'da) otomatik bağlanır. Telefon yeniden başlarsa komutu bir kez daha çalıştır. Alternatif: Android 11+ Kablosuz hata ayıklama (`--pair`, `--connect`). Bilgisayarda iki farklı `adb` varsa (`flutter doctor` uyarısı) birini sabitle: `export JARVIS_ADB=/tam/yol/adb`.
- Aramayı kapatmak için Xiaomi'de "USB hata ayıklama (Güvenlik ayarları)" da açık olmalı. Tanılama: `python phone_check.py`.

## Telefon uygulaması (Jarvis Telefon)

USB/ADB olmadan, internet üzerinden: bilgisayar Firebase (FCM) ile telefondaki küçük uygulamaya imzalı komut yollar. Uygulama (`phone_app/`, Flutter + Kotlin) komutu doğrular ve yürütür.

- "**Anılinho'yu ara**" (onaydan sonra), "**aramayı kapat**", "**telefonu yarın saat 14'te çaldır, toplantı**" (alarmı telefon kurar; bilgisayar kapansa da çalar).
- ADB bağlıysa arama ADB ile yapılır (durumu doğrular); değilse uygulama kullanılır. Uygulamayı denemek için `python phone_check.py --via app` (geri: `--via auto`).
- **Hatırlatıcılar ve takvim:** uygulama eşleşmişse "20 dakika sonra hatırlat" ve takvime eklenen etkinlikler (10 dk önce) telefonda da alarm olarak kurulur; bilgisayar kapansa da çalar, silinince/iptal edilince telefondaki alarm da silinir. Kapatmak: `--alerts off`. Varsayılan `--detail generic`: Firebase'e metin gitmez, telefonda yalnızca "Hatırlatıcı zamanı" yazar; `--detail full` başlığı da gönderir.
- Gizlilik: mesajda numara yok, yalnızca kişi adı gider; numarayı telefon kendi rehberinden bulur. Mesajlar HMAC imzalı, 2 dakikadan eski ya da tekrar eden mesaj reddedilir. Gizli anahtar ADB ile telefona yazılır, ağdan geçmez.
- Kurulum: `phone_app/KURULUM.md`. Eşleştirme: `python phone_check.py --app-pair`, deneme: `--app-test`.

## Telefondan Jarvis (mobil ekran, Tailscale)

Telefon tarayıcısında (ana ekrana eklenebilir) çalışan sayfa: **yazışma**, **sesle konuşma**, **görevler ve takvim**, **durum ve hızlı komutlar**. Hiçbir bulut sunucusu araya girmez: bağlantı Tailscale'in özel ağı (tailnet) içinde bilgisayarla telefon arasında gider; sesin yazıya çevrilmesi bilgisayardaki Whisper'da olur.

- Kurulum: bilgisayara ve telefona Tailscale'i kur (aynı hesap), yönetim panelinde (login.tailscale.com/admin/dns) **MagicDNS** ve **HTTPS Certificates**'ı aç. Sonra `python remote_setup.py` çalıştır: yayın `tailscale serve` ile yalnızca tailnet'e açılır ve telefon için bir bağlantı (varsa QR) yazar. Telefonda Tailscale açıkken bağlantıyı Chrome'da aç, menüden "Ana ekrana ekle". `pip install qrcode` kurulu ise terminalde QR çıkar.
- Jarvis'i her zamanki gibi başlat (`python main.py ...`); telefon erişimi açıksa pano sunucusu pencere açmadan da çalışır.
- Güvenlik: telefonun anahtarı bilgisayardaki pano anahtarından **ayrıdır** (`data/remote.json`, yalnızca sana okunur) ve yalnızca `/m` sayfası ile `/api/m/*` uçlarında geçerlidir; kapatma, tema, bulut ayarı gibi pano uçları uzaktan açılmaz. Uzaktan yazışma Telegram ile aynı kısıtlı kiptedir (telefon araması, kod ajanı, dosya okuma kapalı). Yanlış anahtar denemesi 1 dakika kilitler. Anahtar adreste `#` sonrasındadır (sunucuya/günlüğe gitmez). Funnel (İnternete açık yayın) açıksa kurulum reddedilir.
- Yönetim: `python remote_setup.py --new-token` (anahtarı yenile), `--revoke` (kapat), `--status`.
- Telefondan çalışan hızlı komutlar: günün özeti, bugün, görevler, hava, pil, sistem, evet/vazgeç, sustur, mikrofon, odak.

## Bellek ve güvenlik denetimi

- **RAM:** `RAM.md` (rehber, senaryo tablosu, swap/earlyoom/Ollama ayarları) ve `python ram_report.py [--watch SN]` (kendi makinende ölçüm). Jarvis düşük bellekte uyarır, ağır işi (tarayıcı, kod çalıştırma) bellek yoksa başlatmaz, kaçak sandbox süreçleri önce öldürülür. Ayarlar: `JARVIS_MEM_LOW/CRIT`, `JARVIS_CODE_MEM`, `JARVIS_KEEP_ALIVE`, `JARVIS_NUM_CTX`.
- **Güvenlik sertleştirmesi (v2zc):** `data/` ve içindeki dosyalar yalnızca sahibine açık (0700/0600); kilit/pid dosyaları kullanıcıya özel klasörde (`$XDG_RUNTIME_DIR`); uzaktan (Telegram/telefon) dosya taşıma/silme/geri alma kapalı; kod ajanı kaynak sınırları `prlimit` ile (iş parçacıklı süreçte `preexec_fn` yok). `test_security.py` kodda `eval/exec/os.system/shell=True/pickle` ve kapalı TLS doğrulaması bulunmadığını da her seferinde doğrular.

## Neler yapabiliyor

| Alan | Örnek cümle |
|---|---|
| Sohbet ve araç çağırma | "Saat kaç?", "Yarın hava nasıl?", "Sesi yüzde otuza ayarla" |
| Dosyalar | "rapor.pdf dosyasını oku", "masaüstünde faturaları bul", "onu özetle" |
| Güvenli dosya işlemi | taşıma ve çöpe atma sesli onayla çalışır, "geri al" ile geri döner |
| Takvim ve görevler | "Yarın saat 14'te toplantı ekle", "bu hafta takvimimde ne var", "görev ekle: raporu bitir, cuma, yüksek öncelik", "görevlerim neler", "raporu bitir görevi bitti" (etkinliğe 10 dk kala sesli uyarır) |
| Üst kenar adası | `python main.py --wake --island`: ekranın üst ortasında küçük durum hapı (Dinliyor/Düşünüyor/Konuşuyor); onay ya da plan beklerken soruyu, kalan süreyi ve **Evet/Hayır** düğmelerini gösterir |
| Komut Merkezi panosu (V2) | `python main.py --dash`: kendi penceresinde canlı pano (sistem, ajanlar, modeller, akış, hızlı komutlar; görev/takvimi elle ekle-sil; gün/saate göre sohbet geçmişi, arama, otomatik silme; yetenek listesi; Yazışma sekmesinde Jarvis ile sohbet) |
| Masaüstü uygulaması | `python install_app.py`: menüde JARVIS simgesi, terminalsiz başlar; Ayarlar sekmesinde tema (cyan, amber, yeşil, mor, açık) |
| Hatırlatıcılar, hafıza | "20 dakika sonra beni uyar", "şunu hatırla…", "kedimin adı neydi" (hafıza yerel SQLite FTS5 deposunda: Türkçe ekleri ve harfleri tolere eden, alaka sıralı arama; yeniden başlatınca da durur) |
| Web | "Ankara'nın nüfusunu araştır" (sonuçları okur ve özetler) |
| Tarayıcı kontrolü | "github.com'a git", "sayfayı oku", "arama kutusuna jarvis yaz ve ara" |
| Şarkı/video oynatma | "Böyle Kahpedir Dünya şarkısını oynat", "youtube'dan sezen aksu şarkısı aç" (YouTube'da arar, ilk sonucu çalar, tarayıcıyı kapatmaz) |
| Ekran ve kamera görüşü | "Ekranda ne var?", "Kameraya bak", "Elimde ne var?" (yerel görsel model) |
| Fare ve klavye | "Fareyi sağa götür", "tıkla", "klavyeden merhaba yaz", "Enter'a bas" |
| Ajan modu | "Ajan modu: Wikipedia'da Ankara'yı araştır ve özetle" (planı okur, onay ister) |
| Ekip ve kod ajanı | "araştır: …", "ekip: …", "kod: bir hesap makinesi yaz" (Kod Ajanı yazar, Denetçi bağımsız çalıştırıp doğrular, Yazar söyler), "proje: …" (Mimar önce parçalara böler) |
| Sistem | "CPU kaç?", "Pil kaç?", "Sistem durumu nasıl?", düşük pil uyarısı |
| MCP araçları | "mcp araçları", "mcp: zaman get_current_time timezone=Europe/Istanbul" (JSON sonuç sesli okunur cümleye çevrilir; yalnızca senin `data/mcp.json`'da tanımladığın yerel sunucular; her çağrı onay ister) |
| Sistem bakımı | "Sistem bakımı yap", "Bilgisayarım neden yavaş" (bellek, swap, VRAM, modeller, disk, günlük, unutulmuş derleme süreçleri; kendi başına değişiklik yapmaz, güvenli düzeltmeleri onayla önerir) |
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
python main.py --wake --dash           # + Komut Merkezi panosu (pip install pywebview)
python main.py --wake --island         # + üst kenar adası (Evet/Hayır düğmeli durum/onay çubuğu; Qt)
python main.py --text                  # mikrofon yerine klavyeden yaz (hata ayıklama)
python main.py --list-speakers         # hoparlörleri listele, --speaker <numara|ad> ile seç
python main.py --help                  # tüm bayraklar
```

Çıkmak için "görüşürüz" deyin ya da `q` yazın. "Konuşmayı sıfırla" yeni bir konuşma başlatır.

| Ayar | Komut |
|---|---|
| Uygulama menüsüne simge | `python install_app.py` (masaüstüne de: `--desktop`, kaldırmak: `--remove`) |
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
main.py            konuşma döngüsü (mikrofon → STT → beyin → TTS)
mcp_client.py      yerel MCP istemcisi (stdio JSON-RPC; araçlar skills/mcp.py, sunucular data/mcp.json)
island.py          üst kenar adası (durum + Evet/Hayır; Qt, pano sunucusunun /api/island uçları)
brain.py           model, araç çağırma, kural tabanlı hızlı yol, oturum, bağlam özetleme
agent.py           ajan modu (planla, onayla, adım adım yürüt)
team.py            Ekip modu (çoklu ajan: planlayıcı, mimar, uzman ajanlar [araştırma, dosya, kod, bakım], denetçi, yazar)
router.py, privacy.py   Model yönlendirici (ücretsiz bulut, yedek zinciri) ve gizlilik kapısı
convlog.py         kalıcı konuşma günlüğü (panodaki Konuşmalar; süreli otomatik silme)
stt.py, tts.py, wake.py   konuşma tanıma, sentez, uyanma sözcüğü
skills/            beceriler: her dosya kendini tanımlar ve otomatik yüklenir
  _confirm.py        onay kapısı
  _store.py          data/ klasörü: güvenli kayıt (0600/0700), çalışma zamanı yolları
  browser.py         Playwright ile tarayıcı kontrolü
  desktop_input.py   fare/klavye (xdotool)
  codeagent.py       Kod ajanı araçları (workspace/, güvenli kutu)
  phone.py           telefon araması (ADB ya da uygulama), alarm, yerel rehber
  agenda.py          takvim ve görevler (yerel, Türkçe tarih ayrıştırıcı: _trdate.py)
  memory.py          hafıza (data/memory.db, SQLite FTS5; eski memory.json bir kez içeri alınır, .bak olarak kalır)
  maintenance.py     Sistem bakım ajanı (sağlık raporu + onaylı güvenli düzeltmeler)
  screen.py, camera.py, files.py, web.py, reminders.py, hardware.py, volume.py, brightness.py, apps.py, ...
phonelink.py       telefon uygulamasına imzalı FCM komutu; eşleştirme
phone_app/         Jarvis Telefon uygulaması (Flutter + Kotlin; Firebase Messaging)
memguard.py        bellek koruması (düzey, ağır iş kontrolü, uyarı)
ram_report.py      bellek ölçüm aracı (senaryo tahmini, --watch); RAM.md rehberi
model_bench.py     yerel modelleri hız ve bellek açısından karşılaştırır
remote.py          mobil sayfa erişimi: ayrı anahtar, Host denetimi, kilitleme, Tailscale yardımcıları (remote_setup.py)
dashboard/         Komut Merkezi: server.py (yalnızca 127.0.0.1, rastgele anahtar), state.py (panel sağlayıcıları),
                   window.py (Qt penceresi + sistem tepsisi), static/ (app.js = pano, m.html/m.js/m.css = telefon sayfası)
app.py, install_app.py   masaüstü uygulaması (başlatıcı, simge/.desktop kurulumu), assets/ simgeler
ui.py, ui_state.py, telegram_bot.py, autostart.py
check_all.py       tek komutlu test ve ortam kontrolü
```

Panoya yeni panel eklemek için `dashboard/state.py` içinde `@provider("ad")` ile veri üreten bir fonksiyon yazın, `static/app.js` içindeki `PANELS` ve `index.html`'e çizimini ekleyin; yeni sayfa için `VIEWS` listesine girin. Pano yalnızca bu bilgisayardan erişilir, tehlikeli işlemler panodan da onay ister.

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
