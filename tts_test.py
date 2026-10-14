#!/usr/bin/env python3
"""Aşama 0 - Test 3: Metin -> ses (Piper, Türkçe).

Kullanım:
    python tts_test.py                  # sentezle, ölç, hoparlörden çal
    python tts_test.py --no-play        # sadece ölç, wav dosyalarını out/ klasörüne yaz
    python tts_test.py --voice tr_TR-dfki-medium

Ses dosyası yoksa piper.download_voices ile voices/ klasörüne indirilir.
Sesin adı değiştiyse güncel listeye bak:
    https://huggingface.co/rhasspy/piper-voices/tree/main/tr/tr_TR
"""
import argparse
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_VOICE = "tr_TR-dfki-medium"

SENTENCES = [
    "Merhaba, ben Jarvis. Seni dinliyorum.",
    "Firefox'u açıyorum.",
    "Ses seviyesini yüzde otuza ayarladım.",
    "Yarın saat dokuzda toplantın var, yirmi dakika önce hatırlatayım mı?",
]


def ensure_voice(voice: str, voices_dir: Path) -> Path:
    onnx = voices_dir / f"{voice}.onnx"
    if onnx.exists():
        return onnx
    voices_dir.mkdir(parents=True, exist_ok=True)
    print(f"[ses] {voice} indiriliyor...")
    try:
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", voice],
            cwd=voices_dir,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Ses indirilemedi ({exc}). Adı değişmiş olabilir, güncel liste:\n"
            "https://huggingface.co/rhasspy/piper-voices/tree/main/tr/tr_TR"
        )
    if not onnx.exists():
        raise SystemExit(f"{onnx} bulunamadı; indirme beklenen klasöre yazmamış olabilir (voices/ içine bak).")
    return onnx


def play_wav(path: Path):
    import sounddevice as sd

    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    sd.play(data, rate)
    sd.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--voice", default=DEFAULT_VOICE)
    p.add_argument("--no-play", action="store_true")
    args = p.parse_args()

    from piper import PiperVoice

    onnx = ensure_voice(args.voice, HERE / "voices")
    t0 = time.perf_counter()
    voice = PiperVoice.load(str(onnx))
    print(f"[ses] yüklendi: {time.perf_counter() - t0:.1f} sn")

    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)

    for i, text in enumerate(SENTENCES, 1):
        path = out_dir / f"cumle_{i}.wav"
        t0 = time.perf_counter()
        with wave.open(str(path), "wb") as wf:
            voice.synthesize_wav(text, wf)
        synth = time.perf_counter() - t0
        with wave.open(str(path), "rb") as wf:
            audio_sec = wf.getnframes() / wf.getframerate()
        rtf = synth / audio_sec if audio_sec else float("nan")
        print(f"\n{text}\n  sentez {synth:.2f} sn, ses {audio_sec:.1f} sn, RTF {rtf:.2f} (1'in altı = gerçek zamandan hızlı)")
        if not args.no_play:
            play_wav(path)

    print(f"\nWav dosyaları: {out_dir}")


if __name__ == "__main__":
    main()
