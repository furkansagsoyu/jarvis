#!/usr/bin/env python3
"""Yerel modelleri aynı araç-seçimi cümleleriyle karşılaştırır: doğruluk, gecikme, GPU/CPU dağılımı.

    conda activate freya
    ollama pull gpt-oss:20b
    python model_bench.py                              # gemma4:e4b ve gpt-oss:20b
    python model_bench.py --models gemma4:e4b qwen3:8b gpt-oss:20b --repeat 2

Yedek modele düşme KAPALI (her model kendi başına ölçülür). Araçlar çalıştırılmaz; yalnızca seçilen araç adına bakılır.
Kural tabanlı hızlı yol atlanır: amaç modelin kendisini ölçmek.
"""
import argparse
import statistics
import subprocess
import time

import brain as B
from skills import HIDDEN
from tool_diag import CASES

CHAT_PROMPT = "Türkiye'nin başkenti neresidir? Bir cümleyle söyle."


def bench(model: str, repeat: int) -> dict:
    B.FALLBACKS.clear()  # yedeğe düşüp yanlış sonuç vermesin
    brain = B.Brain(model=model)
    t0 = time.perf_counter()
    try:
        brain.warm_up()
    except Exception as exc:  # noqa: BLE001
        return {"model": model, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    load_s = time.perf_counter() - t0
    schemas = [s for n, (s, _) in brain.tools.items() if n not in HIDDEN]
    ok = total = 0
    lat, wrong = [], []
    for text, expected in CASES:
        for _ in range(repeat):
            msgs = [{"role": "system", "content": brain.system}, {"role": "user", "content": text}]
            t1 = time.perf_counter()
            try:
                _, calls = brain._decide(msgs, schemas)
            except Exception as exc:  # noqa: BLE001
                calls, wrong = [], wrong + [(text, f"hata {type(exc).__name__}")]
            lat.append(time.perf_counter() - t1)
            name = None
            if calls:
                c = calls[0]
                fn = c.get("function") if isinstance(c, dict) else getattr(c, "function", None)
                name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
            total += 1
            if name == expected:
                ok += 1
            else:
                wrong.append((text, name))
    # düz sohbet: ilk parça süresi ve toplam
    t2 = time.perf_counter()
    first, text_out = None, ""
    try:
        for piece in brain._chat([{"role": "system", "content": brain.system}, {"role": "user", "content": CHAT_PROMPT}], None, True, 0.3):
            part = (B._get(B._get(piece, "message"), "content", "") or "")
            if part and first is None:
                first = time.perf_counter() - t2
            text_out += part
    except Exception as exc:  # noqa: BLE001
        text_out = f"hata {type(exc).__name__}"
    ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.strip().splitlines()
    mine = next((ln for ln in ps if ln.startswith(model.split(":")[0])), "")
    return {"model": model, "ok": ok, "total": total, "load": load_s, "p50": statistics.median(lat), "max": max(lat),
            "first": first, "chat": text_out.strip()[:80], "ps": " ".join(mine.split()), "wrong": wrong}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemma4:e4b", "gpt-oss:20b"])
    ap.add_argument("--repeat", type=int, default=2)
    a = ap.parse_args()
    rows = []
    for m in a.models:
        print(f"\n== {m} ölçülüyor...", flush=True)
        r = bench(m, a.repeat)
        rows.append(r)
        if "error" in r:
            print(f"   ATLANDI: {r['error']} (indirdin mi? ollama pull {m})")
            continue
        print(f"   araç seçimi: {r['ok']}/{r['total']}  | yükleme+ilk çağrı: {r['load']:.1f} sn  | karar süresi ortanca {r['p50']:.1f} sn, en yavaş {r['max']:.1f} sn")
        print(f"   sohbet ilk parça: {r['first'] and round(r['first'], 1)} sn  | cevap: {r['chat']!r}")
        print(f"   ollama ps: {r['ps'] or '(okunamadı)'}   <- 'GPU' yüzdesi %100 değilse model kısmen RAM'de çalışıyor (yavaşlar)")
        for text, got in r["wrong"][:8]:
            print(f"   yanlış: {text!r} -> {got}")
    print("\nÖZET")
    for r in rows:
        if "error" not in r:
            print(f"  {r['model']:18} doğru {r['ok']}/{r['total']}  karar {r['p50']:.1f} sn  sohbet-ilk {r['first'] and round(r['first'], 1)} sn")
        else:
            print(f"  {r['model']:18} atlandı")


if __name__ == "__main__":
    main()
