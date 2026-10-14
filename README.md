# Jarvis – Aşama 0: yerel ses hattı testleri

Amaç: kurmaya başlamadan önce makinenin (RTX 3070 Ti 8 GB, 15 GB RAM) yerel hattı kaldırıp
kaldıramadığını ve Türkçe kalitesini **ölçmek**. Üç ayrı test var, hiçbiri diğerine bağlı değil.

| Dosya | Ne test ediyor |
|---|---|
| `stt_test.py` | Mikrofon → Türkçe metin (faster-whisper) |
| `llm_test.py` | Türkçe sohbet + araç çağırma (Ollama), birden fazla modeli karşılaştırır |
| `tts_test.py` | Türkçe metin → ses (Piper) |

> Bu betikleri geliştirme ortamımda çalıştıramadım (mikrofon, hoparlör ve GPU yok), yalnızca söz
> dizimini denetledim. İlk çalıştırmada küçük hatalar çıkabilir, çıktıyı bana yapıştır, düzeltiriz.

## 1) Kurulum (Linux Mint)

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev portaudio19-dev

cd jarvis_faz0
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### GPU için ek kütüphaneler (faster-whisper)

faster-whisper'ın GPU'da çalışması için CUDA 12 çalışma kütüphaneleri gerekir. Sürücün (CUDA 13.2
gösteriyor) bunlarla uyumlu çalışmalı, ama ben doğrulayamadım:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
export LD_LIBRARY_PATH=$(python3 -c 'import os; import nvidia.cublas.lib; import nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))')
```

`export` satırını her yeni terminalde (venv açıkken) tekrarlaman gerekir. GPU açılmazsa `stt_test.py`
otomatik olarak CPU'ya düşer ve bunu ekrana yazar, test yine de çalışır (daha yavaş).

### Ollama

Resmî kurulum yöntemi için https://ollama.com/download sayfasına bak (Linux sekmesi). Kurulunca:

```bash
ollama pull granite4.1:8b
```

Etiket, Ollama'nın araç destekli modeller sayfasından alındı ama tam etiketi doğrulayamadım.
Bulamazsa https://ollama.com/search?c=tools sayfasından 9B ve altı bir model seç.

## 2) Testleri çalıştır

```bash
# Önce mikrofonu bul (gerekirse --mic NUMARA ile seç)
python stt_test.py --list-devices

python stt_test.py                       # large-v3-turbo, 5 sn'lik kayıtlar
python stt_test.py --model medium        # sığmazsa / yavaşsa daha küçüğü

python llm_test.py --models granite4.1:8b
python llm_test.py --models granite4.1:8b baska-model:4b    # karşılaştırma

python tts_test.py
```

Testler sırasında başka bir terminalde `watch -n1 nvidia-smi` ile VRAM kullanımına bak.

## 3) Bana ne yapıştıracaksın

- `stt_test.py`: model yüklendi satırı (cuda mı cpu mu) ve 3-4 kayıt için Metin / Süre satırları.
  Türkçe cümleler, Türkçe karakterler ve sayılarla dene ("sesi yüzde otuza ayarla").
- `llm_test.py`: ÖZET tablosu ve Türkçe sohbet cevapları.
- `tts_test.py`: RTF değerleri ve sesin kulağına nasıl geldiği.
- Üçü için de `nvidia-smi` çıktısından en yüksek VRAM kullanımı.

## 4) Neye bakacağız (öneri eşikleri, bana ait tahminler)

| Test | İyi | Sınırda |
|---|---|---|
| STT | 5 sn'lik cümle 1 sn civarı veya altında, Türkçe doğru | 2-3 sn, ara sıra hata |
| LLM | Araç doğru 5/6 ve üstü, ilk token 1-2 sn | 3-4/6, Türkçe bozuk |
| TTS | RTF 0.5'in altı, ses anlaşılır | RTF 1'e yakın |

## 5) Bellek notları

- **VRAM (8 GB):** Whisper (large-v3-turbo) ve 8B'lik bir LLM aynı anda GPU'ya yüklenirse sıkışabilir.
  Sıkışırsa seçenekler: Whisper'ı `--model medium` ya da `--device cpu` ile çalıştırmak, ya da daha
  küçük bir LLM kullanmak. Piper zaten CPU'da çalışıyor.
- **Takas (swap) yok:** `free -h` çıktında Takas 0B görünüyordu. Bellek dolarsa sistem donabilir.
  İstersen bir swap dosyası ekleyebilirsin (isteğe bağlı, sistem değişikliği):

  ```bash
  sudo fallocate -l 8G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  ```

  Kalıcı olması için `/etc/fstab` dosyasına `/swapfile none swap sw 0 0` satırını eklemek gerekir.
