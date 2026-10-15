#!/usr/bin/env python3
"""Jarvis beyni (Ollama + gemma4:e4b). Faz 1.

Kullanım:
    from brain import Brain
    brain = Brain()
    for parca in brain.reply_stream("Saat kaç?"):
        print(parca, end="")

Elle deneme (klavyeden yaz, ses yok):
    python brain.py

Notlar:
- Cevap akış (stream) halinde gelir; main.py cümle biter bitmez seslendirir.
- Araçlar (tools) bir sözlüktür: {ad: (şema, fonksiyon)}. Faz 2'de bu yapı yetenek (skill) sistemine dönüşecek.
  Şimdilik sadece zararsız bir deneme aracı var: saat sorma.
- Konuşma geçmişi son MAX_HISTORY mesajla sınırlı, araç çağrı ayrıntıları geçmişe yazılmaz.
"""
import datetime as dt
import time

import ollama

MODEL = "gemma4:e4b"
MAX_HISTORY = 12
MAX_TOOL_ROUNDS = 3

SYSTEM = (
    "Adın Jarvis. Türkçe konuşan bir sesli bilgisayar asistanısın. "
    "Cevapların yüksek sesle okunacak: en fazla iki üç kısa, düz cümle kur; "
    "madde işareti, kalın yazı, emoji, kod bloğu ve tablo kullanma. "
    "Sayıları rakamla değil yazıyla yaz (örneğin 'yirmi üç', 'yüzde otuz'). "
    "Bir eylem gerekiyorsa uygun aracı çağır, gerekmiyorsa araç çağırma. "
    "Araç sonucunu kullanıcıya kısa bir cümleyle bildir. "
    "Saat, tarih ve bilgisayarın durumu gibi anlık bilgileri asla tahmin etme veya uydurma: "
    "bunlar için mutlaka ilgili aracı çağır. "
    "Bilmediğin bir şeyi uydurma, bilmediğini söyle."
)


# ---------------------------------------------------------------- araçlar
def _get_time() -> str:
    now = dt.datetime.now()
    return f"Şu an saat {now.hour:02d}:{now.minute:02d}."


TOOLS = {
    "get_time": (
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": (
                    "Bilgisayarın saatine bakıp şu anki saati verir. "
                    "Kullanıcı saati sorarsa MUTLAKA bu aracı çağır, saati kendin tahmin etme."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        _get_time,
    ),
}


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class Brain:
    def __init__(self, model: str = MODEL, tools: dict | None = None, system: str = SYSTEM):
        self.model = model
        self.tools = TOOLS if tools is None else tools
        self.system = system
        self.history: list[dict] = []
        self._think_kw = {"think": False}

    # -- ısınma: modeli belleğe al (ilk cevap gecikmesi azalır)
    def warm_up(self):
        t0 = time.perf_counter()
        try:
            ollama.chat(model=self.model, messages=[{"role": "user", "content": "merhaba"}],
                        keep_alive="30m", **self._think_kw)
        except Exception as exc:  # noqa: BLE001
            if "think" in str(exc).lower():
                self._think_kw = {}
                ollama.chat(model=self.model, messages=[{"role": "user", "content": "merhaba"}], keep_alive="30m")
            else:
                raise
        return time.perf_counter() - t0

    def reset(self):
        self.history.clear()

    def _call_tool(self, name: str, args: dict) -> str:
        entry = self.tools.get(name)
        if not entry:
            return f"Hata: '{name}' adında bir araç yok."
        try:
            return str(entry[1](**(args or {})))
        except Exception as exc:  # noqa: BLE001
            return f"Hata: {type(exc).__name__}: {exc}"

    def reply_stream(self, user_text: str):
        """Kullanıcı cümlesine cevabı parça parça (str) üretir."""
        messages = [{"role": "system", "content": self.system}, *self.history,
                    {"role": "user", "content": user_text}]
        schemas = [schema for schema, _ in self.tools.values()]
        spoken: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS + 1):
            content, tool_calls = [], []
            stream = ollama.chat(
                model=self.model,
                messages=messages,
                tools=schemas or None,
                stream=True,
                options={"temperature": 0.3},
                keep_alive="30m",
                **self._think_kw,
            )
            for chunk in stream:
                msg = _get(chunk, "message")
                piece = _get(msg, "content", "") or ""
                if piece:
                    content.append(piece)
                    spoken.append(piece)
                    yield piece
                tool_calls.extend(_get(msg, "tool_calls") or [])

            if not tool_calls:
                break

            messages.append({"role": "assistant", "content": "".join(content), "tool_calls": tool_calls})
            for call in tool_calls:
                fn = _get(call, "function")
                name = _get(fn, "name")
                args = dict(_get(fn, "arguments", {}) or {})
                result = self._call_tool(name, args)
                print(f"\n[araç] {name}({args}) -> {result}", flush=True)
                messages.append({"role": "tool", "tool_name": name, "content": result})

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": "".join(spoken).strip()})
        del self.history[:-MAX_HISTORY]


def main():
    brain = Brain()
    print(f"[brain] {brain.model} ısınıyor...", flush=True)
    print(f"[brain] hazır ({brain.warm_up():.1f} sn). Yaz, Enter; çıkış: q\n")
    while True:
        try:
            text = input("Sen> ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if text.lower() in ("q", "quit", "exit"):
            break
        if not text:
            continue
        t0 = time.perf_counter()
        first = None
        print("Jarvis> ", end="", flush=True)
        for piece in brain.reply_stream(text):
            if first is None:
                first = time.perf_counter() - t0
            print(piece, end="", flush=True)
        print(f"\n  (ilk parça {first or 0:.2f} sn, toplam {time.perf_counter() - t0:.2f} sn)\n")


if __name__ == "__main__":
    main()
