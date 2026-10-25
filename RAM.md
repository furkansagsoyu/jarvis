# Bellek (RAM/VRAM) rehberi

Hedef makine: 15 GB RAM, 8 GB VRAM (RTX 3070 Ti), swap yok. Bellek biterse çekirdeğin OOM-killer'ı rastgele bir süreci
(çoğu kez Ollama'yı ya da masaüstünü) öldürür ve sistem dakikalarca donabilir. Aşağıdaki katmanlar bunu önler.

## Jarvis'in kendi korumaları (kodda)
| Koruma | Ne yapar |
|---|---|
| `memguard.Monitor` | Boş bellek 1,5 GB'ın altına inince (ya da bellek baskısı PSI ≥ %15) bir kez uyarır ve en çok kullananları sayar; 0,8 GB'ın altında "kritik" der. Spam yok. Eşikler: `JARVIS_MEM_LOW`, `JARVIS_MEM_CRIT` (GB). |
| Ağır işten önce kontrol | Tarayıcı açmak ve kod çalıştırmak, boş bellek (iş için gereken + 0,8 GB) yoksa **başlamaz**, nedenini söyler. |
| Kod ajanı bellek tavanı | Sandbox içindeki tüm süreçler toplam `JARVIS_CODE_MEM` (varsayılan 3G) ile sınırlı (systemd cgroup, varsa). Python ayrıca 3 GB adres alanıyla sınırlı. |
| OOM'da önce sandbox ölür | Sandbox süreçleri `oom_score_adj=1000` ile başlar: bellek bitince çekirdek önce onları öldürür, Ollama'yı ya da masaüstünü değil. |
| `JARVIS_KEEP_ALIVE` | Modelin boşta bellekte kalma süresi (varsayılan 30m). RAM/VRAM sıkışıksa `5m` yap; ilk cevap biraz gecikir. |
| Sistem bakım ajanı | "**Sistem bakımı yap**" / "**bilgisayarım neden yavaş**": bellek, swap, PSI, VRAM, yüklü modeller ve CPU'ya taşma, Ollama servis ayarları, disk, workspace boyutu, Jarvis günlüğündeki hata izleri ve unutulmuş Gradle/Kotlin daemon'ları tek raporda (`skills/maintenance.py`, model çağrısı yok). Kendi başına bir şey yapmaz; yalnızca fazladan yüklü modeli boşaltmayı ve daemon'ları durdurmayı **onayla** önerir, sudo gerektirenleri (swap, sysctl, Ollama ayarı) yalnızca söyler. |
| `JARVIS_NUM_CTX` | Bağlam uzunluğunu sabitler (ör. 4096 ya da 8192). KV önbelleği bununla orantılı büyür; ayarsızsa Ollama varsayılanı. |

## Sistem tarafı (bir kez, sen yap)
**1) Swap dosyası (4 GB) — emniyet kemeri.** Model ağırlıkları dosya-destekli olduğundan swap'a yazılmaz; swap, Chromium/Python
gibi sayfalanabilir belleğe zaman kazandırır ve ani OOM'u donmadan yavaşlamaya çevirir.
```
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf && sudo sysctl --system
free -h   # Swap satırı 4,0Gi görünmeli (btrfs kullanıyorsan fallocate yerine ayrı rehber gerekir)
```
**2) earlyoom — donmadan önce müdahale.** Bellek %5'in altına inince en yüksek OOM puanlı süreci erkenden, kontrollü öldürür (sandbox süreçleri 1000 puanla başladığı için ilk onlar gider).
```
sudo apt install earlyoom
sudo sed -i 's/^EARLYOOM_ARGS=.*/EARLYOOM_ARGS="-m 5 -s 10"/' /etc/default/earlyoom
sudo systemctl restart earlyoom && systemctl status earlyoom --no-pager | head -5
```
**3) Ollama ayarları.** (Yedek model devreye girince iki modelin birden bellekte kalmasını, boşuna büyüyen KV önbelleğini önler.)
```
sudo systemctl edit ollama
```
Açılan editöre yapıştır, kaydet, sonra `sudo systemctl restart ollama`:
```
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
```
Not: `MAX_LOADED_MODELS=1` iken model değişince (ör. yedeğe düşünce) yeni model yüklenirken birkaç sn gecikme olur; karşılığında iki model aynı anda RAM'i yemez.

## Ölçülen değerler (geliştiricinin makinesi: 15,3 GB RAM, RTX 3070 Ti 8 GB, Ekim 2026)
Tahmin tablosunun yerine geçen gerçek `--watch` ölçümleri. "Boş" = çalışırken görülen en düşük kullanılabilir bellek.

| Senaryo | En az boş RAM | En çok kullanım | VRAM tepe | Durum |
|---|---|---|---|---|
| Sesli sohbet (Jarvis + pano) | 9,3 GB | 6,0 GB | 6,8 GB | rahat |
| Kod ajanı + tarayıcı (Chromium) | 7,4 GB | 7,9 GB | 6,8 GB | rahat |
| Yedek model `qwen3:8b` (Jarvis açık) | 9,7 GB | 5,6 GB | 6,8 GB | rahat; model %21 CPU'ya taşıyor (yavaşlar) |
| Flutter/Gradle derlemesi biter bitmez (Jarvis açık, java 1,7–2,2 GB kalır) | 5,8 GB | 9,6 GB | 6,8 GB | rahat |

- `gpt-oss:20b` (13 GB) denendi: doğruluk `gemma4:e4b` ile aynı (65/68 ve 64/68) ama karar 2,3 sn (gemma 0,2 sn), ilk cümle 3,7 sn, %51/49 CPU/GPU; sesli asistan için uygun değil, kaldırıldı.
- Derleme 25–55 sn sürdü; ölçümler derleme bittikten hemen sonrasını kapsıyor (anlık tepe birkaç yüz MB daha yüksek olabilir, pay bol). `-Xmx2G` sınırı işe yarıyor; ama Gradle arka plan süreçleri derlemeden sonra da yaklaşık 2 GB tutar: bitince `./gradlew --stop`.
- Swap, boş bellek bolken bile dolabilir (çekirdek soğuk sayfaları atar): zararsızdır; `vm.swappiness=10` ile azalır.
- Sınır VRAM'de: Jarvis açıkken `qwen3:8b` tam GPU'ya sığmaz (yaklaşık %21 CPU'ya taşar).

## Senaryolar (kaba tahmin; 15 GB RAM için)
`python ram_report.py` çalışan bileşenleri ölçüp aynı tabloyu senin gerçek değerlerinle hesaplar.

| Senaryo | RAM | VRAM | Durum |
|---|---|---|---|
| A Boşta (açık, dinliyor) | ~5,5 GB | ~6,8 GB | rahat |
| B Sesli sohbet (STT+LLM+TTS tepe) | ~6,1 | ~7,1 | rahat |
| C B + pano penceresi (Qt WebEngine) | ~6,8 | ~7,1 | rahat |
| D C + tarayıcı ajanı (2 sekme) | ~7,8 | ~7,1 | rahat |
| E C + kod ajanı (kutu tavanı 3 GB) | ~9,8 | ~7,1 | tamam |
| F D + E (hepsi bir arada) | ~10,8 | ~7,1 | **sıkı** |
| G C + yedek model (qwen3:8b) da yüklendi | ~12,3 | taşar | **sıkı** → `MAX_LOADED_MODELS=1` |
| H gpt-oss:20b denemesi (Jarvis kapalı) | ~10,5 | 8 GB dolu + RAM'e taşar | tamam ama yavaş (CPU/GPU bölünür) |

VRAM tarafı sınırda (≈7 / 8 GB): ikinci bir GPU işi (örn. bir oyun, başka bir model) Whisper'ı CPU'ya düşürür ya da modeli RAM'e taşırır.

## Kendi senaryonu ölç
Her senaryo için ayrı bir terminalde izleyip diğerinde senaryoyu uygula:
```
python ram_report.py --watch 180 --label "sesli-sohbet"
python ram_report.py --watch 300 --label "kod+tarayici"      # kod ajanına bir iş ver, tarayıcıda bir site aç
python ram_report.py --watch 240 --label "yedek-model"       # birincil modeli kapatıp (ollama stop gemma4:e4b) yedeğe düşür
```
Özet şunları verir: en az boş bellek, en yüksek swap/PSI/VRAM, bileşen tepeleri, en kötü anda en çok kullananlar. Tüm örnekler `data/ram_watch.csv`'ye eklenir.
Yorum: **en az boş bellek 1,5 GB üstü** → rahat; 0,8–1,5 GB → sıkı (Jarvis uyarır); 0,8 GB altı → riskli (bu senaryoyu sınırla ya da swap/earlyoom kur).

## Flutter/Gradle derlemesi (telefon uygulaması) bellek yer
Gradle/Kotlin arka plan süreçleri (`java`) derleme bittikten sonra da bellekte kalır (varsayılan 3 saat) ve Flutter şablonu
`android/gradle.properties` içine büyük bir yığın sınırı (`-Xmx8G`) yazar: derleme sırasında 8 GB'a kadar çıkabilir.
Jarvis + Ollama açıkken bu, 15 GB'lık makinede riskli. Çözüm (bir kez):
```
# 1) uygulama klasöründe: phone_app/android/gradle.properties  -> ilk satırı şöyle yap
org.gradle.jvmargs=-Xmx2G -XX:MaxMetaspaceSize=1G -XX:+HeapDumpOnOutOfMemoryError
# 2) tüm projeler için: ~/.gradle/gradle.properties
org.gradle.daemon.idletimeout=600000
kotlin.daemon.jvmargs=-Xmx768m
# 3) şu an kalan arka plan süreçlerini kapat
cd phone_app/android && ./gradlew --stop ; pkill -f KotlinCompileDaemon
```
Derleme biraz yavaşlayabilir; bellek zaten kısıtlıysa buna değer. 3. adımı Jarvis'e de yaptırabilirsin: "sistem bakımı yap" kalan
daemon'ları bulur ve onay verirsen durdurur.
