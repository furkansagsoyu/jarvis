#!/usr/bin/env python3
"""Gerçek Brain ayarını (sistem prompt + yetenek listesi + güvenlik ağı) doğrular.

Araçları ÇALIŞTIRMAZ; modelin hangi aracı seçtiğine bakar.

    conda activate freya
    python tool_check.py              # her cümle 3 kez
    python tool_check.py --repeat 5
"""
import argparse

from brain import Brain
from tool_diag import CASES


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repeat", type=int, default=3)
    args = p.parse_args()

    brain = Brain()
    brain.warm_up()
    schemas = [s for s, _ in brain.tools.values()]

    ok = total = 0
    for text, expected in CASES:
        results = []
        for _ in range(args.repeat):
            messages = [{"role": "system", "content": brain.system}, {"role": "user", "content": text}]
            content, calls = brain._decide(messages, schemas)
            name = calls[0]["function"]["name"] if calls and isinstance(calls[0], dict) else (
                getattr(getattr(calls[0], "function", None), "name", None) if calls else None
            )
            results.append(name)
            good = name == expected
            ok += good
            total += 1
        verdict = "OK  " if all(r == expected for r in results) else "HATA"
        print(f"{verdict} {text!r:42} -> {results}  (beklenen: {expected})")
    print(f"\nTOPLAM: {ok}/{total}")


if __name__ == "__main__":
    main()
