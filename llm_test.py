#!/usr/bin/env python3
"""Aşama 0 - Test 2: Yerel LLM (Ollama) - Türkçe sohbet + araç çağırma.

Birden fazla modeli aynı sorularla dener ve karşılaştırma tablosu basar.

Kullanım:
    ollama pull qwen3:8b
    python llm_test.py --models granite4.1:8b qwen3:8b
    python llm_test.py --models modelA:8b modelB:4b     # karşılaştır

Model etiketlerini https://ollama.com/search?c=tools sayfasından seç
(8 GB VRAM için kabaca 9B ve altı, 4-bit sürümler). Önerilen adaylar:
granite4.1:8b, qwen3:8b, qwen3.5:9b, gemma4:e4b (etiketleri sayfada kontrol et).

Düşünme (thinking) destekli modellerde düşünme kapatılır, çünkü sesli asistanda
gecikme önemli. Desteklemeyen modellerde bu ayar otomatik atlanır.
"""
import argparse
import time

import ollama

SYSTEM = (
    "Adın Jarvis. Türkçe konuşan bir sesli bilgisayar asistanısın. "
    "Cevapların yüksek sesle okunacak: kısa, düz cümlelerle yaz; "
    "madde işareti, kalın yazı, emoji ve kod bloğu kullanma. "
    "Bir eylem gerekiyorsa uygun aracı çağır, gerekmiyorsa araç çağırma."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Bilgisayarda bir uygulamayı açar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Uygulama adı, ör. firefox, terminal"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Sistem ses seviyesini belirli bir yüzdeye ayarlar (mutlak değer).",
            "parameters": {
                "type": "object",
                "properties": {
                    "percent": {"type": "integer", "description": "0 ile 100 arası ses seviyesi"}
                },
                "required": ["percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "change_volume",
            "description": (
                "Sesi mevcut seviyesine göre artırır veya azaltır. "
                "Kullanıcı yüzde vermeden 'biraz kıs' veya 'biraz aç' derse bunu kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "delta_percent": {
                        "type": "integer",
                        "description": "Değişim miktarı. Negatif değer kısar, pozitif değer açar.",
                    }
                },
                "required": ["delta_percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "İnternette arama yapar.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Arama sorgusu"}},
                "required": ["query"],
            },
        },
    },
]


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# (kullanıcı cümlesi, beklenen araç adı ya da None, beklenen argümanlar / kontrol fonksiyonu ya da None)
CASES = [
    ("Firefox'u aç", "open_app", {"name": "firefox"}),
    ("Terminali aç", "open_app", {"name": "terminal"}),
    ("İstanbul'un nüfusunu internette ara", "web_search", None),
    ("Sesi yüzde otuza ayarla", "set_volume", {"percent": 30}),
    ("Ses seviyesini yüzde yetmiş beşe getir", "set_volume", {"percent": 75}),
    ("Sesi yüzde 40 yap", "set_volume", {"percent": 40}),
    ("Sesi biraz kıs", "change_volume", lambda a: _int(a.get("delta_percent")) < 0),
    ("Sesi biraz aç", "change_volume", lambda a: _int(a.get("delta_percent")) > 0),
    ("Bana kısa bir fıkra anlat", None, None),  # araç ÇAĞIRMAMALI
]

CHAT_PROMPTS = [
    "Kendini iki cümleyle tanıt.",
    "Python'da liste ile demet (tuple) arasındaki fark nedir? Kısaca anlat.",
]

# Düşünme (thinking) kapatma ayarı; model destekliyorsa warm_up içinde doldurulur.
THINK_KW = {}


def warm_up(model):
    """Modeli belleğe alır. Düşünme kapatma ayarını destekleyip desteklemediğini de yoklar."""
    global THINK_KW
    messages = [{"role": "user", "content": "merhaba"}]
    try:
        ollama.chat(model=model, messages=messages, think=False)
        THINK_KW = {"think": False}
    except Exception as exc:  # noqa: BLE001
        if "think" in str(exc).lower():
            ollama.chat(model=model, messages=messages)
            THINK_KW = {}
            print("[bilgi] bu model 'think' ayarını desteklemiyor, ayar atlandı")
        else:
            raise


def get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def args_ok(expected, got) -> bool:
    if expected is None:
        return True
    got = got or {}
    if callable(expected):
        try:
            return bool(expected(got))
        except Exception:  # noqa: BLE001
            return False
    for key, value in expected.items():
        actual = got.get(key, "")
        if isinstance(value, str):
            if value.lower() not in str(actual).lower():
                return False
        elif str(actual).strip() != str(value):
            return False
    return True


def chat_stream(model, prompt):
    """Akışlı sohbet: ilk token süresi ve token/sn ölçer."""
    t0 = time.perf_counter()
    first = None
    text = []
    last = None
    for chunk in ollama.chat(
        model=model,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        stream=True,
        options={"temperature": 0.3},
        **THINK_KW,
    ):
        piece = get(get(chunk, "message"), "content", "") or ""
        if piece and first is None:
            first = time.perf_counter() - t0
        text.append(piece)
        last = chunk
    eval_count = get(last, "eval_count", 0) or 0
    eval_ns = get(last, "eval_duration", 0) or 0
    tps = eval_count / (eval_ns / 1e9) if eval_ns else float("nan")
    return "".join(text).strip(), first, tps


def tool_case(model, utterance):
    t0 = time.perf_counter()
    resp = ollama.chat(
        model=model,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": utterance}],
        tools=TOOLS,
        options={"temperature": 0},
        **THINK_KW,
    )
    elapsed = time.perf_counter() - t0
    calls = get(get(resp, "message"), "tool_calls") or []
    if not calls:
        return None, None, elapsed
    fn = get(calls[0], "function")
    return get(fn, "name"), dict(get(fn, "arguments", {}) or {}), elapsed


def show_placement(model):
    """Modelin ne kadarının GPU'da (VRAM) olduğunu yazar. Kalan kısım CPU'da çalışır ve yavaşlatır."""
    try:
        for m in get(ollama.ps(), "models", []) or []:
            if get(m, "model") == model or get(m, "name") == model:
                size = get(m, "size", 0) or 0
                vram = get(m, "size_vram", 0) or 0
                pct = 100 * vram / size if size else float("nan")
                print(f"[bellek] toplam {size / 1e9:.1f} GB, VRAM'de {vram / 1e9:.1f} GB (%{pct:.0f} GPU)")
                return
        print("[bellek] model 'ollama ps' listesinde görünmüyor")
    except Exception as exc:  # noqa: BLE001
        print(f"[bellek] okunamadı: {exc}")


def unload(model):
    """Modeli bellekten atar, böylece sıradaki model temiz bir VRAM ile başlar."""
    try:
        ollama.generate(model=model, prompt="", keep_alive=0)
    except Exception:  # noqa: BLE001
        pass


def run_model(model):
    print(f"\n{'=' * 70}\nMODEL: {model}\n{'=' * 70}")
    try:
        # Isınma: modeli belleğe al, yükleme süresini ayır.
        t0 = time.perf_counter()
        warm_up(model)
        print(f"[yükleme + ilk cevap] {time.perf_counter() - t0:.1f} sn")
    except Exception as exc:  # noqa: BLE001
        print(f"[HATA] {exc}\nModel indirilmemiş olabilir: ollama pull {model}")
        return None

    print("\n-- Türkçe sohbet --")
    ttfts, speeds = [], []
    for prompt in CHAT_PROMPTS:
        text, ttft, tps = chat_stream(model, prompt)
        print(f"\nSoru : {prompt}\nCevap: {text}")
        print(f"(ilk token {ttft:.2f} sn, {tps:.1f} token/sn)" if ttft is not None else "(cevap boş)")
        if ttft is not None:
            ttfts.append(ttft)
            speeds.append(tps)

    show_placement(model)

    print("\n-- Araç çağırma --")
    correct, times = 0, []
    for utterance, exp_name, exp_args in CASES:
        name, got_args, elapsed = tool_case(model, utterance)
        ok = (name == exp_name) and (exp_name is None or args_ok(exp_args, got_args))
        correct += ok
        times.append(elapsed)
        shown = f"{name}({got_args})" if name else "araç çağırmadı"
        want = exp_name or "araç çağırmamalı"
        print(f"{'OK  ' if ok else 'HATA'} | {utterance!r:42} -> {shown}  [beklenen: {want}] {elapsed:.1f} sn")

    result = {
        "model": model,
        "tool": f"{correct}/{len(CASES)}",
        "ttft": sum(ttfts) / len(ttfts) if ttfts else float("nan"),
        "tps": sum(speeds) / len(speeds) if speeds else float("nan"),
        "tool_time": sum(times) / len(times) if times else float("nan"),
    }
    unload(model)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--models", nargs="+", default=["granite4.1:8b"], help="Ollama model etiketleri")
    args = p.parse_args()

    results = [r for r in (run_model(m) for m in args.models) if r]
    if results:
        print(f"\n{'=' * 70}\nÖZET\n{'=' * 70}")
        print(f"{'model':28} {'araç doğru':11} {'ilk token':10} {'token/sn':9} {'araç çağrısı sn':15}")
        for r in results:
            print(f"{r['model']:28} {r['tool']:11} {r['ttft']:<10.2f} {r['tps']:<9.1f} {r['tool_time']:<15.1f}")
        print("\nİpucu: testi çalıştırırken başka bir terminalde 'nvidia-smi' ile VRAM kullanımına bak.")


if __name__ == "__main__":
    main()
