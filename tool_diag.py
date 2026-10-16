#!/usr/bin/env python3
"""Araç çağırma tanısı: gemma hangi ayarda aracı gerçekten çağırıyor?

Araçları ÇALIŞTIRMAZ; sadece modelin hangi aracı seçtiğine bakar (ses değişmez, uygulama açılmaz).

    conda activate freya
    python tool_diag.py
    python tool_diag.py --repeat 3      # her cümleyi 3 kez dene (sıcaklık 0.3 olan varyantlar rastgele)
"""
import argparse

import ollama

from brain import MODEL, SYSTEM
from skills import capability_summary, load_skills

CASES = [
    ("Sesi yüzde elliye ayarla", "set_volume"),
    ("Sesi kıs", "change_volume"),
    ("Sesi biraz aç", "change_volume"),
    ("Terminali aç", "open_app"),
    ("Hesap makinesini aç", "open_app"),
    ("İstanbul'un nüfusunu internette ara", "web_search"),
    ("Saat kaç?", "get_time"),
    ("Parlaklığı yüzde elliye ayarla", "set_brightness"),
    ("Ekranı biraz karart", "change_brightness"),
    ("Parlaklığı artır", "change_brightness"),
    ("Yirmi dakika sonra beni uyar", "set_reminder"),
    ("Saat beşte bana ekmeği hatırlat", "set_reminder"),
    ("Zamanlayıcıyı iki dakikaya kur", "set_reminder"),
    ("Kurulu hatırlatıcılar neler", "list_reminders"),
    ("Hatırlatıcıları iptal et", "cancel_reminders"),
    ("Benim adım Furkan, bunu hatırla", "remember"),
    ("Kedimin adı Pamuk, not al", "remember"),
    ("Adımı hatırlıyor musun", "recall"),
    ("Kedimin adı neydi", "recall"),
    ("Kedimle ilgili kaydı unut", "forget"),
    ("Hava nasıl", "get_weather"),
    ("Yarın yağmur yağacak mı", "get_weather"),
    ("İstanbul'da hava kaç derece", "get_weather"),
    ("Bana kısa bir fıkra anlat", None),
]

SHORT_SYSTEM = (
    "Adın Jarvis. Türkçe konuşan bir sesli bilgisayar asistanısın. "
    "Cevapların yüksek sesle okunacak: kısa, düz cümlelerle yaz; "
    "madde işareti, kalın yazı, emoji ve kod bloğu kullanma. "
    "Bir eylem gerekiyorsa uygun aracı çağır, gerekmiyorsa araç çağırma."
)


def get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def first_tool(system, schemas, text, stream, temperature):
    messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
    kw = dict(model=MODEL, messages=messages, tools=schemas, options={"temperature": temperature}, think=False)
    calls, content = [], []
    if stream:
        for chunk in ollama.chat(stream=True, **kw):
            msg = get(chunk, "message")
            content.append(get(msg, "content", "") or "")
            calls.extend(get(msg, "tool_calls") or [])
    else:
        msg = get(ollama.chat(**kw), "message")
        content.append(get(msg, "content", "") or "")
        calls = get(msg, "tool_calls") or []
    name = get(get(calls[0], "function"), "name") if calls else None
    return name, "".join(content).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repeat", type=int, default=1)
    args = p.parse_args()

    tools = load_skills()
    schemas = [s for s, _ in tools.values()]
    caps = SYSTEM + (
        f" Yapabildiğin işler şunlar: {capability_summary(tools)}. "
        "Bunların dışında bir eylem istenirse bunu yapamadığını söyle, yapmış gibi davranma."
    )

    variants = [
        ("A  şimdiki hal: akışlı, sıcaklık 0.3, uzun prompt + yetenek listesi", caps, True, 0.3),
        ("B  akışlı, sıcaklık 0.3, uzun prompt (yetenek listesi YOK)", SYSTEM, True, 0.3),
        ("C  akışsız, sıcaklık 0, uzun prompt + yetenek listesi", caps, False, 0.0),
        ("D  akışsız, sıcaklık 0, uzun prompt (yetenek listesi YOK)", SYSTEM, False, 0.0),
        ("E  akışsız, sıcaklık 0, kısa prompt (Faz 0 testindeki)", SHORT_SYSTEM, False, 0.0),
    ]

    print("model ısınıyor...", flush=True)
    ollama.chat(model=MODEL, messages=[{"role": "user", "content": "merhaba"}], think=False)

    summary = []
    for label, system, stream, temp in variants:
        print(f"\n=== {label}", flush=True)
        ok = total = 0
        for text, expected in CASES:
            for _ in range(args.repeat):
                name, content = first_tool(system, schemas, text, stream, temp)
                good = name == expected
                ok += good
                total += 1
                shown = name or f"(araç yok) {content[:50]!r}"
                print(f"  {'OK  ' if good else 'HATA'} {text!r:42} -> {shown}", flush=True)
        summary.append((label[:2].strip(), ok, total))

    print("\nÖZET (doğru araç / toplam)")
    for key, ok, total in summary:
        print(f"  {key}: {ok}/{total}")


if __name__ == "__main__":
    main()
