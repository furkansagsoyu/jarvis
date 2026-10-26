#!/usr/bin/env python3
"""Gerçek Brain ayarını (sistem prompt + yetenek listesi + güvenlik ağı) doğrular.

Araçları ÇALIŞTIRMAZ; modelin hangi aracı seçtiğine bakar.

    conda activate freya
    python tools/tool_check.py              # her cümle 3 kez
    python tools/tool_check.py --repeat 5
"""
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri

import argparse

from core.brain import Brain
from skills import HIDDEN
from tools.tool_diag import CASES


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repeat", type=int, default=3)
    args = p.parse_args()

    brain = Brain()
    brain.warm_up()
    schemas = [s for n, (s, _) in brain.tools.items() if n not in HIDDEN]  # gizli araçları model görmez

    ok = total = 0
    for text, expected in CASES:
        results = []
        for _ in range(args.repeat):
            messages = [{"role": "system", "content": brain.system}, {"role": "user", "content": text}]
            fast = brain._fast_route(text)  # gerçek akışta önce kural tabanlı hızlı yol çalışır
            if fast:
                content, calls = "", [{"function": {"name": fast[0][0], "arguments": fast[0][1]}}]
            else:
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
