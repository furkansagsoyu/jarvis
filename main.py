#!/usr/bin/env python3
"""Jarvis - Faz 1: konuş -> yazıya dök -> düşün -> seslendir.

Çalıştırma (freya ortamında, şarja takılı):
    python main.py
    python main.py --mic 3          # mikrofon numarası (python stt.py --list-devices)
    python main.py --text           # mikrofon yerine klavyeden yaz (hata ayıklama)
    python main.py --steps 12       # TTS adım sayısı (düşük = hızlı)

Her tur: Enter -> konuş -> Enter. Çıkmak için "görüşürüz" de ya da q yaz.
"""
import stt

stt.ensure_cuda_libs()  # LD_LIBRARY_PATH'i ayarlar (gerekirse programı bir kez yeniden başlatır)

import argparse  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402

from brain import Brain  # noqa: E402
from tts import FreyaSpeaker  # noqa: E402

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
EXIT_WORDS = ("görüşürüz", "kapat kendini", "çıkış yap", "hoşça kal")


def pop_sentences(buffer: str):
    """Tamamlanmış cümleleri ayırır; bitmemiş son parçayı geri verir."""
    parts = SENTENCE_END.split(buffer)
    return parts[:-1], parts[-1]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--mic", type=int, default=None)
    p.add_argument("--text", action="store_true", help="klavyeden yaz (mikrofon/Whisper kullanılmaz)")
    p.add_argument("--steps", type=int, default=16)
    p.add_argument("--quiet-tts", action="store_true", help="TTS süre satırlarını gizle")
    args = p.parse_args()

    t0 = time.perf_counter()
    listener = None
    if not args.text:
        print("[1/3] Whisper yükleniyor...", flush=True)
        listener = stt.Listener(mic=args.mic)
    print("[2/3] Freya (TTS) yükleniyor...", flush=True)
    speaker = FreyaSpeaker(device="cpu", steps=args.steps)
    speaker.verbose = not args.quiet_tts
    print("[3/3] Gemma ısınıyor...", flush=True)
    brain = Brain()
    brain.warm_up()
    print(f"\nHazır ({time.perf_counter() - t0:.0f} sn). Konuşabilirsin.\n", flush=True)
    speaker.say("Hazırım.")
    speaker.wait()

    while True:
        try:
            if args.text:
                text = input("\nSen> ").strip()
            else:
                text = listener.listen_once()
                print(f"Sen> {text}")
        except (KeyboardInterrupt, EOFError):
            break
        if not text:
            continue
        if text.lower() in ("q", "quit", "exit") or any(w in text.lower() for w in EXIT_WORDS):
            speaker.say("Görüşürüz.")
            speaker.wait()
            break

        t_start = time.perf_counter()
        first_audio_queued = None
        buffer = ""
        print("Jarvis> ", end="", flush=True)
        for piece in brain.reply_stream(text):
            print(piece, end="", flush=True)
            buffer += piece
            sentences, buffer = pop_sentences(buffer)
            for s in sentences:
                if first_audio_queued is None:
                    first_audio_queued = time.perf_counter() - t_start
                speaker.say(s)
        if buffer.strip():
            speaker.say(buffer)
        print(f"\n  (ilk cümle TTS'e {first_audio_queued or 0:.2f} sn'de gitti)", flush=True)
        speaker.wait()


if __name__ == "__main__":
    main()
