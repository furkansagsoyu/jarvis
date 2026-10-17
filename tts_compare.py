#!/usr/bin/env python3
"""Türkçe TTS motorlarını AYNI cümlelerle üretip kulakla karşılaştırma aracı.

    python tts_compare.py --list
    python tts_compare.py --engines freya16 freya32 ema antalia          # her motor için ses_karsilastirma/<motor>/NN.wav
    python tts_compare.py --engines freya16 ema antalia --blind          # dosyalar A_01.wav, B_01.wav... (hangi harf hangi motor: key.txt, dinledikten SONRA aç)

Motorlar (eksik paket varsa o motor atlanır ve kurulum komutu yazılır):
    freya16   mevcut ayar (CPU, 16 adım)             freya32   model kartının önerdiği 32 adım (CPU'da ~2x yavaş)
    ema       EMA Lightning  -> pip install ema-lightning
    antalia   Antalia-2 Mini -> pip install antalia-mini
    ema65     EMA-TTS (65M)  -> git clone https://huggingface.co/canberkkkkkk/ema-tts ~/jarvis_deneme/ema-tts ; pip install -r requirements.txt
    chatterbox Chatterbox Multilingual -> AYRI conda ortamında: pip install chatterbox-tts   (torch sürümünü değiştirebilir!)
    edge      Microsoft Edge sesi (ONLINE, resmi olmayan; sadece referans) -> pip install edge-tts
"""
import argparse
import asyncio
import random
import sys
import time
import wave
from pathlib import Path

import numpy as np

OUT = Path("ses_karsilastirma")
SENTENCES = [
    "Anladım.",
    "Evet.",
    "Tamam, hallediyorum.",
    "Yirmi dakika sonra hatırlatacağım.",
    "Şu an saat yirmi bir otuz bir.",
    "Tokat için şu an hava parçalı bulutlu, 14 derece, hissedilen 13. Gün boyu en düşük 12, en yüksek 18 derece, yağış ihtimali yüzde 93.",
    "İndirilenler klasöründeki Staj Raporu dosyasını Belgeler klasörüne taşıyacağım. Onaylıyor musun?",
    "Merhaba Furkan, sana nasıl yardımcı olabilirim?",
    "Bugün 17 Ekim 2026, cumartesi. Bu akşam için kurulu bir hatırlatıcın yok, ama yarın sabah dokuzda bir toplantın var.",
    "Ses seviyesi yüzde kırk iken yüzde seksen yapıldı.",
]


def write_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    pcm = (np.clip(np.asarray(audio, dtype=np.float32).squeeze(), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def wav_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:  # noqa: BLE001  (mp3 ya da float wav)
        return None


# ---- motor kurucuları: (synth(text, path), uzantı) döndürür; eksikse ImportError ----
def make_freya(steps):
    def build():
        from tts import FreyaSpeaker  # noqa: PLC0415

        sp = FreyaSpeaker(device="cpu", steps=steps)

        def synth(text, path):
            from tts import split_sentences  # noqa: PLC0415

            parts = [sp._synth(s) for s in split_sentences(text)]
            write_wav(path, np.concatenate(parts), sp.sample_rate)

        return synth, ".wav"
    return build


def build_ema():
    from ema_lightning import EMA  # noqa: PLC0415

    m = EMA()
    return (lambda text, path: m.say(text, path=str(path))), ".wav"


def build_antalia():
    from antalia_mini import Antalia  # noqa: PLC0415

    m = Antalia()
    return (lambda text, path: m.say(text, path=str(path), seed=0)), ".wav"


def build_ema65():
    sys.path.insert(0, str(Path("~/jarvis_deneme/ema-tts").expanduser()))
    from inference import EmaTTS  # noqa: PLC0415

    m = EmaTTS.from_pretrained(str(Path("~/jarvis_deneme/ema-tts/ckpt").expanduser()), device="cpu")

    def synth(text, path):
        m.save(m.say(text), str(path))

    return synth, ".wav"


def build_chatterbox():
    import torchaudio  # noqa: PLC0415
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: PLC0415

    m = ChatterboxMultilingualTTS.from_pretrained(device="cuda")

    def synth(text, path):
        torchaudio.save(str(path), m.generate(text, language_id="tr"), m.sr)

    return synth, ".wav"


def build_edge():
    import edge_tts  # noqa: PLC0415

    def synth(text, path):
        asyncio.run(edge_tts.Communicate(text, "tr-TR-EmelNeural").save(str(path)))

    return synth, ".mp3"


ENGINES = {
    "freya16": (make_freya(16), "pip yok (mevcut kurulum)"),
    "freya32": (make_freya(32), "pip yok (mevcut kurulum)"),
    "ema": (build_ema, "pip install ema-lightning"),
    "antalia": (build_antalia, "pip install antalia-mini"),
    "ema65": (build_ema65, "bkz. dosya başındaki açıklama"),
    "chatterbox": (build_chatterbox, "ayrı ortamda: pip install chatterbox-tts"),
    "edge": (build_edge, "pip install edge-tts"),
}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--engines", nargs="+", choices=ENGINES, default=["freya16"])
    p.add_argument("--blind", action="store_true", help="dosya adlarında motor adı yerine A, B, C... kullan")
    p.add_argument("--list", action="store_true")
    a = p.parse_args()
    if a.list:
        for k, (_, hint) in ENGINES.items():
            print(f"{k:11} {hint}")
        return

    names = list(a.engines)
    if a.blind:
        random.shuffle(names)
    labels = {n: (chr(65 + i) if a.blind else n) for i, n in enumerate(names)}
    OUT.mkdir(exist_ok=True)
    summary = []
    for eng in names:
        build, hint = ENGINES[eng]
        print(f"\n=== {eng} yükleniyor...", flush=True)
        try:
            synth, ext = build()
        except ImportError as exc:
            print(f"  atlandı ({exc}). Kurulum: {hint}")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  atlandı: {type(exc).__name__}: {exc}")
            continue
        total_t = total_a = 0.0
        for i, text in enumerate(SENTENCES, 1):
            path = OUT / f"{labels[eng]}_{i:02d}{ext}" if a.blind else OUT / eng / f"{i:02d}{ext}"
            path.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter()
            try:
                synth(text, path)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{i:02d}] HATA {type(exc).__name__}: {exc}")
                continue
            dt = time.perf_counter() - t0
            sec = wav_seconds(path)
            total_t += dt
            total_a += sec or 0
            print(f"  [{i:02d}] {dt:5.2f} sn üretim" + (f", {sec:5.2f} sn ses, RTF {dt / sec:.2f}" if sec else "") + f"  {text[:40]!r}")
        summary.append((eng, total_t, total_a))

    if a.blind:
        (OUT / "key.txt").write_text("\n".join(f"{labels[n]} = {n}" for n in names), encoding="utf-8")
        print(f"\nHangi harf hangi motor: {OUT / 'key.txt'} (dinledikten sonra aç)")
    print("\nÖZET (toplam üretim süresi / ses süresi)")
    for eng, t, s in summary:
        print(f"  {eng:11} {t:6.1f} sn üretim" + (f", {s:5.1f} sn ses, RTF {t / s:.2f}" if s else ""))
    print(f"\nDosyalar: {OUT.resolve()}")


if __name__ == "__main__":
    main()
