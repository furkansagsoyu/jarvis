#!/usr/bin/env python3
"""Aşama 0 - Test 1: Mikrofon -> metin (faster-whisper).

Kullanım:
    python stt_test.py --list-devices          # ses cihazlarını listele
    python stt_test.py                         # varsayılan mikrofon, 5 sn kayıt
    python stt_test.py --model small --device cpu   # sorun ayıklarken en hafif hali
    python stt_test.py --model medium          # daha küçük model dene
    python stt_test.py --file ornek.wav        # mikrofon yerine dosya
"""
print("stt_test.py başladı...", flush=True)

import argparse
import faulthandler
import os
import sys
import threading
import time
from pathlib import Path

faulthandler.enable()  # çökme olursa nerede olduğunu yazdırır

import numpy as np

SAMPLE_RATE = 16000


def log(msg: str):
    print(msg, flush=True)


def _hf_cache_mb() -> float:
    """HuggingFace önbelleğinin boyutu (MB). Model inerken büyüdüğünü göstermek için."""
    root = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    total = 0
    try:
        for dirpath, _, files in os.walk(root):
            for name in files:
                try:
                    total += os.lstat(os.path.join(dirpath, name)).st_size
                except OSError:
                    pass
    except Exception:  # noqa: BLE001
        pass
    return total / 1e6


class Heartbeat:
    """Uzun süren bir işlem sırasında her birkaç saniyede bir 'hâlâ çalışıyorum' yazar."""

    def __init__(self, label: str, every: float = 10.0):
        self.label, self.every = label, every
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        t0 = time.perf_counter()
        while not self._stop.wait(self.every):
            log(f"   ... {self.label} ({time.perf_counter() - t0:.0f} sn, önbellek {_hf_cache_mb():.0f} MB)")

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        return False


def build_model(name: str, device_pref: str):
    """Modeli yükler. GPU açılmazsa CPU'ya düşer ve bunu açıkça söyler."""
    log("[1/3] faster-whisper kütüphanesi yükleniyor (ilk seferde birkaç saniye sürebilir)...")
    from faster_whisper import WhisperModel

    attempts = []
    if device_pref in ("auto", "cuda"):
        attempts.append(("cuda", "float16"))
    if device_pref in ("auto", "cpu"):
        attempts.append(("cpu", "int8"))

    last_error = None
    for device, compute in attempts:
        try:
            log(
                f"[2/3] '{name}' modeli {device}/{compute} ile yükleniyor. "
                "İlk çalıştırmada model internetten iner (large-v3-turbo için yaklaşık 1.5 GB), "
                "birkaç dakika sürebilir."
            )
            t0 = time.perf_counter()
            with Heartbeat("model hâlâ yükleniyor/iniyor"):
                model = WhisperModel(name, device=device, compute_type=compute)
            log(f"      yüklendi ({time.perf_counter() - t0:.1f} sn)")

            # Gerçek hatalar (ör. eksik cuDNN) çoğu zaman ilk çalıştırmada çıkar.
            log("[3/3] ısınma testi yapılıyor...")
            t1 = time.perf_counter()
            with Heartbeat("ısınma sürüyor"):
                segments, _ = model.transcribe(
                    np.zeros(SAMPLE_RATE, dtype=np.float32), language="tr"
                )
                list(segments)
            log(f"[model] HAZIR: {name} {device}/{compute} (ısınma {time.perf_counter() - t1:.1f} sn)")
            return model
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log(f"[model] {device}/{compute} olmadı: {type(exc).__name__}: {exc}")
    raise SystemExit(f"Model yüklenemedi: {last_error}")


def record(seconds: float, mic_index):
    import sounddevice as sd

    log(f"\n>>> {seconds:g} sn kayıt başlıyor, konuş...")
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=mic_index,
    )
    sd.wait()
    log(">>> kayıt bitti")
    return audio[:, 0]


def transcribe(model, audio, beam_size: int):
    t0 = time.perf_counter()
    segments, info = model.transcribe(
        audio, language="tr", beam_size=beam_size, vad_filter=True
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    elapsed = time.perf_counter() - t0
    duration = info.duration if hasattr(info, "duration") else 0.0
    return text, elapsed, duration


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model", default="large-v3-turbo", help="whisper modeli (large-v3-turbo, medium, small ...)")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--beam", type=int, default=1, help="beam size (1 = en hızlı)")
    p.add_argument("--mic", type=int, default=None, help="mikrofon indeksi (--list-devices ile bak)")
    p.add_argument("--file", default=None, help="mikrofon yerine ses dosyası")
    p.add_argument("--list-devices", action="store_true")
    args = p.parse_args()

    log(f"Python: {sys.executable}")
    log(f"Ayarlar: model={args.model}, device={args.device}, mic={args.mic}")

    if args.list_devices:
        import sounddevice as sd

        print(sd.query_devices(), flush=True)
        return

    model = build_model(args.model, args.device)

    if args.file:
        text, elapsed, duration = transcribe(model, args.file, args.beam)
        log(f"\nMetin   : {text}")
        log(f"Süre    : {elapsed:.2f} sn (ses uzunluğu {duration:.1f} sn)")
        return

    while True:
        cmd = input("\nKayıt için Enter, çıkmak için q: ").strip().lower()
        if cmd == "q":
            break
        audio = record(args.seconds, args.mic)
        text, elapsed, duration = transcribe(model, audio, args.beam)
        rtf = elapsed / duration if duration else float("nan")
        log(f"Metin   : {text or '(boş / ses algılanmadı)'}")
        log(f"Süre    : {elapsed:.2f} sn  (ses {duration:.1f} sn, RTF {rtf:.2f}; 1'in altı gerçek zamandan hızlı)")


if __name__ == "__main__":
    main()
