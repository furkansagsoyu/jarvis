#!/usr/bin/env python3
"""Araç çağırma tanısı 2: çalışan kısa prompt'a (E) kuralları TEK TEK ekleyip hangisinin bozduğunu bulur.

    conda activate freya
    python tool_diag2.py
Araçları ÇALIŞTIRMAZ.
"""
import ollama

from brain import MODEL
from skills import capability_summary, load_skills
from tool_diag import CASES, SHORT_SYSTEM, first_tool

RULES = {
    "a sayıları yazıyla yaz": " Sayıları rakamla değil yazıyla yaz (örneğin 'yirmi üç', 'yüzde otuz').",
    "b araç sonucunu bildir": " Araç sonucunu kullanıcıya kısa bir cümleyle bildir.",
    "c anlık bilgiyi uydurma": (
        " Saat, tarih ve bilgisayarın durumu gibi anlık bilgileri asla tahmin etme veya uydurma: "
        "bunlar için mutlaka ilgili aracı çağır."
    ),
    "d bilmediğini söyle": " Bilmediğin bir şeyi uydurma, bilmediğini söyle.",
    "e en fazla 2-3 cümle": " En fazla iki üç kısa cümle kur.",
}


def main():
    tools = load_skills()
    schemas = [s for s, _ in tools.values()]
    caps = (
        f" Yapabildiğin işler şunlar: {capability_summary(tools)}. "
        "Bunların dışında bir eylem istenirse bunu yapamadığını söyle, yapmış gibi davranma."
    )
    variants = [("0 temel (E)", SHORT_SYSTEM, False, 0.0)]
    variants += [(f"+{k}", SHORT_SYSTEM + v, False, 0.0) for k, v in RULES.items()]
    variants.append(("+f yetenek listesi", SHORT_SYSTEM + caps, False, 0.0))
    variants.append(("+hepsi", SHORT_SYSTEM + "".join(RULES.values()) + caps, False, 0.0))
    variants.append(("temel, ama akışlı 0.3", SHORT_SYSTEM, True, 0.3))

    print("model ısınıyor...", flush=True)
    ollama.chat(model=MODEL, messages=[{"role": "user", "content": "merhaba"}], think=False)

    summary = []
    for label, system, stream, temp in variants:
        ok = 0
        misses = []
        for text, expected in CASES:
            name, _ = first_tool(system, schemas, text, stream, temp)
            if name == expected:
                ok += 1
            else:
                misses.append(f"{text!r}->{name}")
        summary.append((label, ok, len(CASES)))
        print(f"{label:28} {ok}/{len(CASES)}   " + ("; ".join(misses) if misses else ""), flush=True)

    print("\nÖZET")
    for label, ok, total in summary:
        print(f"  {label:28} {ok}/{total}")


if __name__ == "__main__":
    main()
