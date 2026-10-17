#!/usr/bin/env python3
"""Eller serbest dinleme: "Hey Jarvis" uyanma sözcüğü + konuşma bitince otomatik durdurma. Faz 4.

Kurulum (bir kez, freya ortamında):
    pip install openwakeword
    python -c "import openwakeword; openwakeword.utils.download_models()"

Çalıştırma:
    python main.py --wake
    python wake.py            # sadece uyanma sözcüğünü dene (Ctrl+C ile çık)

Akış: bekle -> "Hey Jarvis" -> kısa bip -> konuş -> 1 sn sessizlik -> yazıya dök.
Hoparlör yankısı: dinleme yalnızca Jarvis'in konuşması bittikten sonra başlar (akış sıralı).
"""
import re
import time

import numpy as np

SAMPLE_RATE = 16000
FRAME = 1280  # openWakeWord 80 ms'lik (16 kHz) dilimler ister
LEADING_WAKE = re.compile(r"^\W*(hey|hay|ey|hei)?\s*(jarvis|jarvıs|jervis|çarvis)\b(?!['’])[\s,.!:;-]*", re.I)


def strip_wake_phrase(text: str) -> str:
    """Kayıt uyanma sözcüğünün kuyruğunu içerebilir: 'Hey Jarvis, saat kaç' -> 'saat kaç'."""
    return LEADING_WAKE.sub("", text or "").strip()


class WakeWord:
    def __init__(self, threshold: float = 0.5, mic=None, name: str = "hey_jarvis"):
        try:
            import openwakeword  # noqa: PLC0415
            from openwakeword.model import Model  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("openwakeword kurulu değil: pip install openwakeword") from exc
        try:
            self.model = Model(wakeword_models=[name], inference_framework="onnx")
        except Exception:  # noqa: BLE001  (model dosyaları henüz inmemiş olabilir)
            print("[wake] model dosyaları indiriliyor...", flush=True)
            openwakeword.utils.download_models()
            self.model = Model(wakeword_models=[name], inference_framework="onnx")
        self.threshold, self.mic, self.name = threshold, mic, name

    def wait(self, stop_after: float | None = None) -> bool:
        """Uyanma sözcüğü duyulana kadar bloklar. stop_after saniye geçerse False döner."""
        import sounddevice as sd  # noqa: PLC0415

        try:
            self.model.reset()
        except Exception:  # noqa: BLE001
            pass
        t0 = time.time()
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME, device=self.mic) as stream:
            while stop_after is None or time.time() - t0 < stop_after:
                frame, _ = stream.read(FRAME)
                scores = self.model.predict(frame[:, 0])
                if scores and max(scores.values()) >= self.threshold:
                    return True
        return False


def beep(freq: int = 880, ms: int = 110, volume: float = 0.2) -> None:
    import sounddevice as sd  # noqa: PLC0415

    t = np.linspace(0, ms / 1000, int(SAMPLE_RATE * ms / 1000), endpoint=False)
    wave = (volume * np.sin(2 * np.pi * freq * t) * np.hanning(len(t))).astype(np.float32)
    sd.play(wave, SAMPLE_RATE)
    sd.wait()


def endpoint(read_chunk, last_speech_end, silence_s: float = 1.0, no_speech_s: float = 5.0,
             max_s: float = 15.0, check_every: float = 0.5, chunk_s: float = 0.1) -> np.ndarray:
    """Konuşma bitene kadar kaydeder.

    read_chunk() -> float32 dizisi (chunk_s saniye); last_speech_end(audio) -> son konuşmanın bitiş örnek
    indeksi (konuşma yoksa None). Test edilebilsin diye ikisi de dışarıdan verilir.
    """
    chunks: list[np.ndarray] = []
    elapsed, since_check = 0.0, 0.0
    while elapsed < max_s:
        chunks.append(read_chunk())
        elapsed += chunk_s
        since_check += chunk_s
        if since_check < check_every:
            continue
        since_check = 0.0
        audio = np.concatenate(chunks)
        end = last_speech_end(audio)
        if end is None:
            if elapsed >= no_speech_s:
                return np.zeros(0, dtype=np.float32)  # kimse konuşmadı
        elif len(audio) - end >= silence_s * SAMPLE_RATE:
            break
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def record_utterance(mic=None, **kw) -> np.ndarray:
    import sounddevice as sd  # noqa: PLC0415
    from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: PLC0415

    opts = VadOptions(min_silence_duration_ms=500)

    def last_end(audio):
        ts = get_speech_timestamps(audio, opts, sampling_rate=SAMPLE_RATE)
        return ts[-1]["end"] if ts else None

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=mic) as stream:
        return endpoint(lambda: stream.read(int(SAMPLE_RATE * 0.1))[0][:, 0].copy(), last_end, **kw)


def listen_handsfree(listener, wake: WakeWord) -> str:
    """Uyanma sözcüğünü bekler, komutu kaydeder ve yazıya döker (boş olabilir)."""
    print("\n👂 'Hey Jarvis' bekleniyor...", flush=True)
    wake.wait()
    beep()
    print("🎙  dinliyorum...", flush=True)
    audio = record_utterance(listener.mic)
    t0 = time.perf_counter()
    text = strip_wake_phrase(listener.transcribe(audio))
    print(f"[stt] {len(audio) / SAMPLE_RATE:.1f} sn ses, {time.perf_counter() - t0:.2f} sn işlem", flush=True)
    return text


def main():
    ww = WakeWord()
    print("Hazır. 'Hey Jarvis' de (Ctrl+C ile çık).", flush=True)
    try:
        while True:
            ww.wait()
            print(f"[wake] algılandı ({time.strftime('%H:%M:%S')})", flush=True)
            beep()
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
