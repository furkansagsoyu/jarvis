#!/usr/bin/env python3
"""Jarvis TTS modülü (Freya). Faz 1.

Başka dosyalardan kullanım:
    from tts import make_speaker
    tts = make_speaker("ema")     # varsayılan: EMA Lightning (CPU); "freya" eski motor
    tts.speak("firefox'u açıyorum. başka bir şey var mı?")

Elle deneme:
    python tts.py "yirmi dakika sonra hatırlatırım"
    python tts.py --interactive

Notlar:
- Freya küçük harfle başlayan cümlelerde bozuluyor; bu yüzden her cümlenin ilk harfi büyütülür.
- Metin cümlelere bölünür. Bir cümle çalarken sıradaki cümle arka planda üretilir,
  böylece ilk cümle hemen başlar.
- Modül değiştirilebilir olsun diye arayüz basit tutuldu: speak(text), stop().
"""
import argparse
import queue
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

REPO = Path("~/jarvis_deneme/FreyaTTS").expanduser()

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def tr_upper_first(s: str) -> str:
    """İlk harfi Türkçe kurallarına göre büyütür (i -> İ, ı -> I)."""
    s = s.strip()
    if not s:
        return s
    first = s[0]
    first = {"i": "İ", "ı": "I"}.get(first, first.upper())
    return first + s[1:]


_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")


def clean_for_speech(text: str) -> str:
    """Sesli okunmayacak işaretleri (markdown, emoji, kod) temizler."""
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [yazı](bağlantı) -> yazı
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)  # madde işaretleri
    text = re.sub(r"[*_`#>~|]", "", text)
    return _EMOJI.sub("", text)


def split_sentences(text: str) -> list[str]:
    """Metni cümlelere böler, boşları atar, her cümlenin ilk harfini büyütür."""
    text = re.sub(r"\s+", " ", clean_for_speech(text)).strip()
    parts = [p.strip() for p in _SENTENCE_END.split(text) if p.strip()]
    out = []
    for p in parts:
        p = tr_upper_first(p)
        if p[-1] not in ".!?…":
            p += "."
        out.append(p)
    return out


class BaseSpeaker:
    """Ortak kuyruk mantığı: say() cümleleri kuyruğa atar, wait() hepsi çalınana dek bekler.

    Alt sınıflar _synth(cümle) -> float32 dizisi ve self.sample_rate sağlar.
    """

    verbose = False

    def scale_for(self, n_chars: int) -> float:
        return 1.0

    # ---- akışlı kullanım: say() cümleleri kuyruğa atar, wait() hepsi çalınana dek bekler ----
    def _ensure_workers(self):
        if getattr(self, "_workers", False):
            return
        self._text_q: "queue.Queue[str]" = queue.Queue()
        self._audio_q: "queue.Queue[np.ndarray | None]" = queue.Queue(maxsize=3)
        self._pending = 0
        self._cv = threading.Condition()
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()
        self._workers = True

    def _synth_loop(self):
        while True:
            sentence = self._text_q.get()
            if self._stop.is_set():
                self._audio_q.put(None)  # atlandı; sayaç oynatıcıda düşer
                continue
            try:
                audio = self._synth(sentence)
            except Exception as exc:  # noqa: BLE001
                print(f"[tts] hata: {type(exc).__name__}: {exc}", flush=True)
                audio = None
            if audio is not None and self.verbose:
                sec = len(audio) / self.sample_rate
                print(f"  [tts] {len(sentence)} karakter, dur={self.scale_for(len(sentence)):.2f}, {sec:.2f} sn", flush=True)
            self._audio_q.put(audio)

    def _play_loop(self):
        import sounddevice as sd  # noqa: PLC0415

        while True:
            audio = self._audio_q.get()
            if audio is not None and not self._stop.is_set():
                sd.play(audio, self.sample_rate)
                sd.wait()
            with self._cv:
                self._pending -= 1
                self._cv.notify_all()

    def say(self, text: str):
        """Metni cümlelere bölüp kuyruğa ekler ve hemen döner (bloklamaz)."""
        self._ensure_workers()
        for sentence in split_sentences(text):
            with self._cv:
                self._pending += 1
            self._text_q.put(sentence)

    def wait(self):
        """Kuyruktaki her şey çalınana kadar bekler."""
        if not getattr(self, "_workers", False):
            return
        with self._cv:
            self._cv.wait_for(lambda: self._pending == 0)
        self._stop.clear()

    def stop(self):
        """Konuşmayı hemen keser (ör. kullanıcı araya girerse)."""
        self._stop.set()
        try:
            import sounddevice as sd  # noqa: PLC0415

            sd.stop()
        except Exception:  # noqa: BLE001
            pass

    def speak(self, text: str, block: bool = True):
        import sounddevice as sd  # noqa: PLC0415

        sentences = split_sentences(text)
        if not sentences:
            return
        self._stop.clear()
        q: "queue.Queue[np.ndarray | None]" = queue.Queue(maxsize=2)

        def producer():
            for s in sentences:
                if self._stop.is_set():
                    break
                audio = self._synth(s)
                if self.verbose:
                    sec = len(audio) / self.sample_rate
                    print(f"  [tts] {len(s)} karakter, dur={self.scale_for(len(s)):.2f}, {sec:.2f} sn, {sec / len(s):.3f} sn/karakter", flush=True)
                q.put(audio)
            q.put(None)

        t = threading.Thread(target=producer, daemon=True)
        t.start()

        def consumer():
            while not self._stop.is_set():
                audio = q.get()
                if audio is None:
                    break
                sd.play(audio, self.sample_rate)
                sd.wait()

        if block:
            consumer()
        else:
            threading.Thread(target=consumer, daemon=True).start()




class FreyaSpeaker(BaseSpeaker):
    def __init__(
        self,
        device: str = "cpu",
        steps: int = 16,
        short_dur: float = 0.7,
        short_from: int = 8,
        short_to: int = 18,
        repo: Path = REPO,
    ):
        if Path(repo).exists():
            sys.path.insert(0, str(repo))
        import math  # noqa: PLC0415

        import torch  # noqa: PLC0415
        from freyatts import FreyaTTS  # noqa: PLC0415

        self.steps = steps
        self._tts = FreyaTTS.from_pretrained("freyavoice/freya-tts", device=device)

        # Süre tahmini (log kare sayısı) katsayıyla küçültülür/büyütülür.
        # Freya bazen süreyi fazla tahmin ediyor; fazlalık "mı", "u" gibi ekler olarak duyuluyor.
        speaker = self

        class _ScaledDur(torch.nn.Module):
            def __init__(self, inner):
                super().__init__()
                self.inner = inner

            def forward(self, x):
                return self.inner(x) + math.log(speaker.dur_scale)

        # Kısa cümlelerde süre tahmini fazla çıkıyor (kayma/yankı). Katsayı karakter sayısına göre:
        # <= short_from karakter: short_dur, >= short_to karakter: 1.0, arası doğrusal.
        self.short_dur, self.short_from, self.short_to = short_dur, short_from, short_to
        self.dur_scale = 1.0
        self._tts.model.dur = _ScaledDur(self._tts.model.dur)
        self.sample_rate = int(getattr(self._tts, "sample_rate", 48000) or 48000)
        self._stop = threading.Event()
        self.verbose = False
        self._tts.synthesize("Merhaba.", steps=self.steps)  # ısınma

    def scale_for(self, n_chars: int) -> float:
        if n_chars <= self.short_from:
            return self.short_dur
        if n_chars >= self.short_to:
            return 1.0
        frac = (n_chars - self.short_from) / (self.short_to - self.short_from)
        return self.short_dur + (1.0 - self.short_dur) * frac

    def _synth(self, sentence: str) -> np.ndarray:
        self.dur_scale = self.scale_for(len(sentence))
        wav = self._tts.synthesize(sentence, steps=self.steps)
        if hasattr(wav, "detach"):
            wav = wav.detach().cpu().numpy()
        return np.asarray(wav, dtype=np.float32).squeeze()



class EmaSpeaker(BaseSpeaker):
    """EMA Lightning (pip install ema-lightning): 8,6M parametre, tek Türkçe ses, Apache-2.0.

    Kulak testinde (tts_compare.py) Freya'dan belirgin şekilde iyi çıktı. CPU'da yaklaşık 6 kat gerçek zamanlı;
    GPU'da yaklaşık 1 GB VRAM ister (Whisper + Gemma yanında sığmayabilir), bu yüzden varsayılan CPU.
    """

    def __init__(self, device: str = "cpu", seed: int = 0, speed: float = 1.0):
        import threading as _t  # noqa: PLC0415

        from ema_lightning import EMA  # noqa: PLC0415

        try:
            self._tts = EMA(device=device)
        except TypeError:  # bu sürüm device argümanı almıyor
            self._tts = EMA()
        self.seed, self.speed = seed, speed
        self.sample_rate = 48000
        self._stop = _t.Event()
        self.verbose = False
        self._synth("Merhaba.")  # ısınma

    def _synth(self, sentence: str) -> np.ndarray:
        kw = {"seed": self.seed}
        if self.speed != 1.0:
            kw["speed"] = self.speed
        speech = self._tts.say(sentence, **kw)
        for attr in ("audio", "samples", "wav", "waveform", "data"):
            arr = getattr(speech, attr, None)
            if arr is not None and not callable(arr):
                for sr_attr in ("sample_rate", "sr", "rate"):
                    sr = getattr(speech, sr_attr, None)
                    if sr:
                        self.sample_rate = int(sr)
                        break
                if hasattr(arr, "detach"):
                    arr = arr.detach().cpu().numpy()
                return np.asarray(arr, dtype=np.float32).squeeze()
        # Nesne biçimi bilinmiyorsa dosya yoluyla al
        import tempfile  # noqa: PLC0415
        import wave  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.wav"
            self._tts.say(sentence, path=str(path), **kw)
            with wave.open(str(path), "rb") as w:
                self.sample_rate = w.getframerate()
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        return pcm.astype(np.float32) / 32768.0


def make_speaker(engine: str = "ema", steps: int = 16, device: str = "cpu"):
    """engine: 'ema' (varsayılan) ya da 'freya'. EMA kurulu değilse Freya'ya düşer."""
    if engine == "ema":
        try:
            return EmaSpeaker(device=device)
        except ImportError:
            print("[tts] ema-lightning kurulu değil (pip install ema-lightning); Freya'ya dönülüyor", flush=True)
    return FreyaSpeaker(device=device, steps=steps)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("text", nargs="?", help="seslendirilecek metin")
    p.add_argument("--engine", default="ema", choices=["ema", "freya"], help="ses motoru (varsayılan ema)")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    p.add_argument("--steps", type=int, default=16)
    p.add_argument("--short-dur", type=float, default=0.7, help="kısa cümlelerde süre katsayısı (1.0 = model tahmini)")
    p.add_argument("--short-from", type=int, default=8, help="bu karakter sayısı ve altı: tam short-dur")
    p.add_argument("--short-to", type=int, default=18, help="bu karakter sayısı ve üstü: katsayı 1.0")
    p.add_argument("--interactive", action="store_true")
    args = p.parse_args()

    print("[tts] model yükleniyor...", flush=True)
    t0 = time.perf_counter()
    if args.engine == "freya":
        tts = FreyaSpeaker(device=args.device, steps=args.steps, short_dur=args.short_dur,
                           short_from=args.short_from, short_to=args.short_to)
    else:
        tts = make_speaker("ema", args.steps, args.device)
    tts.verbose = True
    print(f"[tts] hazır ({time.perf_counter() - t0:.1f} sn), motor={type(tts).__name__}", flush=True)

    if args.interactive or not args.text:
        print("Komutlar (yalnızca Freya motoru): /short 0.8 8 18   /steps 12   |   çıkış: q")
        while True:
            text = input("\nMetin (çıkış: q)> ").strip()
            if text.lower() in ("q", "quit", "exit"):
                break
            if text.startswith("/short") or text.startswith("/steps"):
                try:
                    cmd, *vals = text.split()
                    if cmd == "/short":
                        tts.short_dur = float(vals[0])
                        if len(vals) > 1:
                            tts.short_from = int(vals[1])
                        if len(vals) > 2:
                            tts.short_to = int(vals[2])
                    else:
                        tts.steps = int(vals[0])
                    print(f"  ayarlandı: steps={tts.steps}, kısa={tts.short_dur} ({tts.short_from}-{tts.short_to} karakter)")
                except (ValueError, IndexError):
                    print("  kullanım: /short 0.8 8 18  veya  /steps 12")
                continue
            if text:
                print("  cümleler:", split_sentences(text))
                tts.speak(text)
    else:
        print("  cümleler:", split_sentences(args.text))
        tts.speak(args.text)


if __name__ == "__main__":
    main()
