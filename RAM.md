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
