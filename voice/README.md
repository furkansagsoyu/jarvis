# voice/ — ses

| Dosya | Görevi |
|---|---|
| `stt.py` | Konuşma tanıma: faster-whisper `large-v3-turbo` (GPU). Mikrofon seçimi, Türkçe ipucu metni. |
| `tts.py` | Ses sentezi: EMA Lightning (CPU; varsayılan), yedek Freya TTS. Cümle cümle çalar, "Sustur" ile kesilir. |
| `wake.py` | Uyanma sözcüğü "Hey Jarvis" (openWakeWord) ve konuşmanın bitişini algılama. Uyanınca durum `recording` olur (ada büyür). |

Neden TTS CPU'da: 8 GB VRAM'in ≈6,8 GB'ı Whisper ve Gemma'ya gidiyor (ölçüm: `RAM.md`).

Tek başına deneme:
```bash
python voice/stt.py --list-devices      # mikrofonlar
python voice/stt.py --mic 3             # sürekli dinle, q ile çık
python voice/tts.py "yirmi dakika sonra hatırlatırım"
python voice/tts.py --list-devices      # hoparlörler
python voice/wake.py                    # yalnızca uyanma sözcüğünü dene
```
Jarvis içinde: `python main.py --mic 3 --speaker <numara|ad> --wake-threshold 0.5 --stt-prompt short`.
Sesle araya girme yok (hoparlör sesi mikrofona karışır); Enter ya da Sustur ile kesilir.
