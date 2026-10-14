#!/usr/bin/env python3
"""TTS alternatifi: FreyaTTS-small (Türkçe'ye özel, 183M parametre, Apache-2.0).

Piper testindeki cümlelere benzer cümleleri seslendirir, hız ölçer ve çalar.
Kod, projenin README'sindeki kullanım örneğine dayanıyor. README'yi burada
çalıştıramadım, bu yüzden API'de küçük farklar çıkabilir; hata olursa çıktıyı yapıştır.

Kurulum (AYRI bir ortamda, çalışan .venv'e dokunma):
    deactivate                      # (.venv) açıksa
    conda create -n freya python=3.12 -y
    conda activate freya
    mkdir -p ~/jarvis_deneme && cd ~/jarvis_deneme
    git clone https://github.com/freyavoiceai/FreyaTTS.git
    pip install -r FreyaTTS/requirements.txt
    pip install sounddevice numpy

Kullanım:
    HF_HUB_DISABLE_XET=1 python freya_test.py --device cuda
    python freya_test.py --device cpu          # VRAM yetmezse
    python freya_test.py --no-play             # sadece ölç, wav'ları out_freya/ içine yaz
    python freya_test.py --interactive         # yazdığın metni seslendirir (telaffuz denemesi)
    python freya_test.py --device cpu --steps 12 --no-play   # daha az ODE adımı = daha hızlı (kalite düşebilir)
    (interaktif modda "/steps 16" yazarak adım sayısını canlı değiştirebilirsin)
"""
print("freya_test.py başladı...", flush=True)

import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000  # README: çıkış 48 kHz

SENTENCES = [
    "Merhaba, ben Jarvis. Seni dinliyorum.",
    "Firefox'u açıyorum.",
    "Ses seviyesini yüzde otuza ayarladım.",
    "Sesi yüzde 30'a ayarladım.",  # rakamla yazılmış sayıyı da dener
    "Yarın saat dokuzda toplantın var, yirmi dakika önce hatırlatayım mı?",
]


def to_numpy(wav) -> np.ndarray:
    """Çıktı torch tensörü de olsa numpy dizisi de olsa float32 numpy'a çevirir."""
    if hasattr(wav, "detach"):
        wav = wav.detach().cpu().numpy()
    return np.asarray(wav, dtype=np.float32).squeeze()


def save_wav16(path: Path, audio: np.ndarray, sr: int):
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def play(audio: np.ndarray, sr: int):
    import sounddevice as sd

    sd.play(audio, sr)
    sd.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    p.add_argument("--repo", default="~/jarvis_deneme/FreyaTTS", help="FreyaTTS deposunun klasörü")
    p.add_argument("--no-play", action="store_true")
    p.add_argument("--interactive", action="store_true", help="metin yaz, dinle (çıkmak için q)")
    p.add_argument("--steps", type=int, default=None, help="ODE adım sayısı (modelin varsayılanı 32)")
    args = p.parse_args()

    repo = Path(args.repo).expanduser()
    if repo.exists():
        sys.path.insert(0, str(repo))
    try:
        from freyatts import FreyaTTS
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"freyatts içe aktarılamadı: {type(exc).__name__}: {exc}\n"
            f"Depo klasörünü --repo ile göster (şu an: {repo}) ve kurulum adımlarını kontrol et."
        )

    print(f"[model] yükleniyor ({args.device}); ilk seferde internetten iner...", flush=True)
    t0 = time.perf_counter()
    tts = FreyaTTS.from_pretrained("freyavoice/freya-tts", device=args.device)
    print(f"[model] hazır ({time.perf_counter() - t0:.1f} sn)", flush=True)
    sr = int(getattr(tts, "sample_rate", SAMPLE_RATE) or SAMPLE_RATE)

    state = {"steps": args.steps}

    def generate(text):
        kwargs = {"steps": state["steps"]} if state["steps"] else {}
        return to_numpy(tts.synthesize(text, **kwargs))

    print(f"[ayar] adım sayısı: {state['steps'] or 'varsayılan (32)'}", flush=True)
    generate("Merhaba.")  # ısınma; süre ölçümüne katılmaz

    out_dir = Path(__file__).resolve().parent / "out_freya"
    out_dir.mkdir(exist_ok=True)

    if args.interactive:
        print("\nİnteraktif mod: bir metin yaz, Enter'a bas, dinle. Çıkmak için q.", flush=True)
        while True:
            text = input("\nMetin> ").strip()
            if text.lower() in ("q", "quit", "exit"):
                break
            if not text:
                continue
            if text.startswith("/steps"):
                try:
                    state["steps"] = int(text.split()[1])
                    print(f"  adım sayısı: {state['steps']}")
                except (IndexError, ValueError):
                    print("  kullanım: /steps 16")
                continue
            t0 = time.perf_counter()
            audio = generate(text)
            synth = time.perf_counter() - t0
            seconds = len(audio) / sr
            rtf = synth / seconds if seconds else float("nan")
            print(f"  sentez {synth:.2f} sn, ses {seconds:.1f} sn, RTF {rtf:.2f}", flush=True)
            play(audio, sr)
        return

    for i, text in enumerate(SENTENCES, 1):
        t0 = time.perf_counter()
        audio = generate(text)
        synth = time.perf_counter() - t0
        seconds = len(audio) / sr
        rtf = synth / seconds if seconds else float("nan")
        print(f"\n{text}\n  sentez {synth:.2f} sn, ses {seconds:.1f} sn, RTF {rtf:.2f} (1'in altı = gerçek zamandan hızlı)", flush=True)
        save_wav16(out_dir / f"cumle_{i}.wav", audio, sr)
        if not args.no_play:
            play(audio, sr)

    try:
        import torch

        if args.device == "cuda" and torch.cuda.is_available():
            peak = torch.cuda.max_memory_allocated() / 2**20
            print(f"\n[bellek] torch'un ayırdığı en yüksek VRAM: {peak:.0f} MiB (nvidia-smi bundan yüksek gösterebilir)")
    except Exception:  # noqa: BLE001
        pass

    print(f"\nWav dosyaları: {out_dir}")


if __name__ == "__main__":
    main()
