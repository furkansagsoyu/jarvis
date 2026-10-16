#!/usr/bin/env python3
"""Jarvis STT modülü (faster-whisper + push-to-talk). Faz 1.

Başka dosyalardan kullanım:
    import stt
    stt.ensure_cuda_libs()            # programın EN BAŞINDA, başka import'lardan önce
    listener = stt.Listener()
    text = listener.listen_once()     # Enter'a bas, konuş, tekrar Enter'a bas

Elle deneme:
    python stt.py                     # sürekli dinler, q ile çıkılır
    python stt.py --list-devices
    python stt.py --mic 3

Notlar:
- Whisper GPU'da (cuda/float16) çalışır. cuBLAS/cuDNN kütüphaneleri pip paketlerinden gelir ve
  LD_LIBRARY_PATH'e programın başlamasından ÖNCE eklenmesi gerekir. ensure_cuda_libs() bunu
  bir kez kendini yeniden başlatarak halleder, elle export gerekmez.
- Kayıt 16 kHz mono. Çok kısa (0.4 sn altı) kayıtlar boş sayılır.
"""
import os
import sys

SAMPLE_RATE = 16000
MIN_SECONDS = 0.4

# Whisper'a özel isimleri ve komut kalıplarını ipucu olarak verir (yanlış yazımları azaltır).
DEFAULT_PROMPT = (
    "Jarvis, Firefox'u aç. Terminali aç. Sesi yüzde otuza ayarla. Parlaklığı artır. "
    "Ekranı karart. Parlaklığı yüzde elliye ayarla. Hesap makinesini aç. "
    "İnternette ara. Chrome, Spotify, Visual Studio Code."
)


def ensure_cuda_libs():
    """nvidia-cublas-cu12 / nvidia-cudnn-cu12 kütüphanelerini LD_LIBRARY_PATH'e ekler.

    LD_LIBRARY_PATH süreç başlarken okunduğu için, değişiklik gerekiyorsa program
    aynı argümanlarla bir kez yeniden başlatılır.
    """
    if os.environ.get("JARVIS_CUDA_REEXEC") == "1":
        return
    paths = []
    for mod in ("nvidia.cublas.lib", "nvidia.cudnn.lib"):
        try:
            m = __import__(mod, fromlist=["x"])
            paths.append(list(m.__path__)[0])  # namespace paket: __file__ yok, __path__ var
        except Exception:  # noqa: BLE001
            pass
    if not paths:
        return
    current = os.environ.get("LD_LIBRARY_PATH", "")
    missing = [p for p in paths if p not in current.split(":")]
    if not missing:
        return
    os.environ["LD_LIBRARY_PATH"] = ":".join(missing + ([current] if current else []))
    os.environ["JARVIS_CUDA_REEXEC"] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


import threading  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402


class Listener:
    def __init__(
        self,
        model: str = "large-v3-turbo",
        device: str = "cuda",
        mic=None,
        beam: int = 1,
        prompt: str = DEFAULT_PROMPT,
    ):
        from faster_whisper import WhisperModel  # noqa: PLC0415

        self.mic = mic
        self.beam = beam
        self.prompt = prompt
        compute = "float16" if device == "cuda" else "int8"
        try:
            self.model = WhisperModel(model, device=device, compute_type=compute)
            self.model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="tr")  # ısınma
            self.device = device
        except Exception as exc:  # noqa: BLE001
            print(f"[stt] {device} olmadı ({type(exc).__name__}: {exc}); CPU'ya düşülüyor", flush=True)
            self.model = WhisperModel(model, device="cpu", compute_type="int8")
            self.device = "cpu"

    def record_push_to_talk(self) -> np.ndarray:
        """Enter ile başlar, Enter ile biter. Float32 mono 16 kHz döndürür."""
        import sounddevice as sd  # noqa: PLC0415

        chunks: list[np.ndarray] = []

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            chunks.append(indata[:, 0].copy())

        answer = input("\n[Enter] konuşmaya başla (çıkmak için q + Enter)...").strip().lower()
        if answer in ("q", "quit", "exit"):
            raise KeyboardInterrupt
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.mic, callback=callback
        )
        with stream:
            print("🎙  dinliyorum... (bitirmek için Enter)", flush=True)
            input()
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def transcribe(self, audio: np.ndarray) -> str:
        if len(audio) < MIN_SECONDS * SAMPLE_RATE:
            return ""
        segments, _ = self.model.transcribe(
            audio,
            language="tr",
            beam_size=self.beam,
            vad_filter=True,
            initial_prompt=self.prompt or None,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def listen_once(self) -> str:
        audio = self.record_push_to_talk()
        t0 = time.perf_counter()
        text = self.transcribe(audio)
        dt = time.perf_counter() - t0
        print(f"[stt] {len(audio) / SAMPLE_RATE:.1f} sn ses, {dt:.2f} sn işlem", flush=True)
        return text


def main():
    import argparse  # noqa: PLC0415

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model", default="large-v3-turbo")
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    p.add_argument("--mic", type=int, default=None)
    p.add_argument("--list-devices", action="store_true")
    args = p.parse_args()

    if args.list_devices:
        import sounddevice as sd  # noqa: PLC0415

        print(sd.query_devices())
        return

    print("[stt] model yükleniyor...", flush=True)
    t0 = time.perf_counter()
    listener = Listener(model=args.model, device=args.device, mic=args.mic)
    print(f"[stt] hazır ({time.perf_counter() - t0:.1f} sn, {listener.device})", flush=True)

    while True:
        try:
            text = listener.listen_once()
        except (KeyboardInterrupt, EOFError):
            break
        print(f"Metin: {text or '(boş / ses algılanmadı)'}")


if __name__ == "__main__":
    ensure_cuda_libs()
    main()
