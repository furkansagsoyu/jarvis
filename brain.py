#!/usr/bin/env python3
"""Jarvis beyni (Ollama + gemma4:e4b). Faz 2: yetenek sistemi.

Kullanım:
    from brain import Brain
    brain = Brain()
    for parca in brain.reply_stream("Saat kaç?"):
        print(parca, end="")

Elle deneme (klavyeden yaz, ses yok):
    python brain.py

Notlar:
- Cevap akış (stream) halinde gelir; main.py cümle biter bitmez seslendirir.
- Araçlar skills/ klasöründen otomatik yüklenir ({ad: (şema, fonksiyon)}); yeni yetenek için skills/ altına
  yeni bir dosya yazmak yeterli (bkz. skills/__init__.py).
- Konuşma geçmişi son MAX_HISTORY mesajla sınırlı, araç çağrı ayrıntıları geçmişe yazılmaz.
"""
import ast
import re
import time

import ollama

from skills import _confirm as confirm
from skills import capability_summary, load_skills

MODEL = "gemma4:e4b"
MAX_HISTORY = 16
MAX_TOOL_ROUNDS = 3

# Ölçümle (tool_diag.py, tool_diag2.py, tool_check.py) doğrulandı: SADECE bu kısa hal 8/8 araç çağırıyor.
# Kural eklemek (sayıları yazıyla yaz, anlık bilgiyi uydurma, yetenek listesi, cümle sınırı...) tek tek
# zararsız görünse bile birlikte araç çağırmayı bozdu (tool_check 16/24). Bu yüzden prompt'a kural EKLEME;
# önce tool_diag2.py / tool_check.py ile ölç. Yetenek listesi list_abilities aracından gelir.
# Rakamları sese çevirme işi TTS tarafında.
SYSTEM = (
    "Adın Jarvis. Türkçe konuşan bir sesli bilgisayar asistanısın. "
    "Cevapların yüksek sesle okunacak: kısa, düz cümlelerle yaz; "
    "madde işareti, kalın yazı, emoji ve kod bloğu kullanma. "
    "Bir eylem gerekiyorsa uygun aracı çağır, gerekmiyorsa araç çağırma."
)

# Model araç çağırmadan "açıyorum" gibi eylem bildirirse bu bir yalandır; yakalanır.
ACTION_CLAIM = re.compile(
    r"\b(açıyorum|açtım|kısıyorum|kıstım|artırıyorum|azaltıyorum|azalttım|ayarlıyorum|ayarladım|"
    r"arıyorum|aradım|başlatıyorum|kapatıyorum|çalıştırıyorum|yükseltiyorum|düşürüyorum|"
    r"çağırıyorum|kullanıyorum|öğreniyorum|bakıyorum|kontrol ediyorum|kullanmalıyım|çağırmalıyım|"
    r"açıldı|kapatıldı|ayarlandı|yapıldı|kısıldı|kısıldı|artırıldı|azaltıldı|arandı|başlatıldı|çalıştırıldı)\b|"
    r"\baraç|"
    r"\b(open_app|set_volume|change_volume|get_time|get_date|web_search|list_abilities|remember|recall|forget|set_reminder|list_reminders|cancel_reminders|get_weather|find_files|read_file|move_file|trash_file)\b",
    re.IGNORECASE,
)
# Saat/tarih gibi anlık bilgilerde modele karar bırakılmaz (gemma tarihi uydurdu: "25 Mayıs 2024").
# Yalnızca açık SORU kalıpları yakalanır; alarm, hatırlatma, ayar ve başka günler modele gider.
NOT_A_QUERY = re.compile(r"alarm|hatırlat|zamanlayıcı|sayaç|\bkur\b|ayarla|ekle|bekle|yarın|dün\b|geçen|haftaya|önümüzdeki", re.I)
ASKING = re.compile(r"kaç|söyle|nedir|\bne\b|öğren|bak|göster|şu an|şimdi", re.I)
WORD_TIME = re.compile(r"\bsaat(i|e|in|ini|ine)?\b", re.I)
WORD_DATE = re.compile(r"\b(tarih(i)?|günlerden|hangi gün|bugün ne|bugünün (günü|tarihi))", re.I)
WORD_WEATHER = re.compile(r"\bhava\b|yağmur|yağış|yağacak|kaç derece|sıcaklık|şemsiye|kar yağ", re.I)
CITY_NAMED = re.compile(r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]+['’]")  # "İstanbul'da hava nasıl": şehir var, modele bırak
WORD_READ = re.compile(r"\b(oku\w*|özetle\w*|içeri\w*)\b", re.I)
WORD_FILE = re.compile(r"\bdosya\w*|\.(txt|md|pdf|py|csv|json)\b", re.I)
READ_FILLER = re.compile(r"\b(dosya\w*|oku\w*|özetle\w*|içeri\w*|bana|bir|şu|şunu|bu|bunu|onu|söyle\w*|lütfen|ve|de|da)\b", re.I)
FOLLOWUP_TOOLS = {"read_file"}  # sonucu doğrudan okunmaz; model özetleyip cevaplar
TEXT_CALL = re.compile(r"^\s*`*([a-z_]+)\((.*)\)`*\s*$", re.S)
NUDGE = "Bu isteği gerçekten yerine getirmek için uygun aracı çağır. Uygun araç yoksa yapamadığını söyle."
FAIL_TEXT = "Bunu yapamadım."


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class Brain:
    def __init__(self, model: str = MODEL, tools: dict | None = None, system: str = SYSTEM):
        self.model = model
        self.tools = load_skills() if tools is None else tools
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

    def _chat(self, messages, schemas, stream: bool, temperature: float):
        return ollama.chat(
            model=self.model,
            messages=messages,
            tools=schemas or None,
            stream=stream,
            options={"temperature": temperature},
            keep_alive="30m",
            **self._think_kw,
        )

    def _parse_text_call(self, content: str) -> list[dict]:
        """Gemma bazen aracı gerçek çağrı yerine düz metin yazar: web_search(query="x"). Güvenle ayrıştırır."""
        m = TEXT_CALL.match(content or "")
        if not m and content and len(content) < 80:  # "recall() çağrısı yapacağım." gibi cümle içine gömülü çağrı
            m = next((x for x in re.finditer(r"\b([a-z_]+)\(([^()]*)\)", content) if x.group(1) in self.tools), None)
        if not m or m.group(1) not in self.tools:
            return []
        try:
            node = ast.parse(f"f({m.group(2)})", mode="eval").body
            if node.args:
                return []
            args = {kw.arg: ast.literal_eval(kw.value) for kw in node.keywords if kw.arg}
        except (SyntaxError, ValueError):
            return []
        return [{"function": {"name": m.group(1), "arguments": args}}]

    def _decide(self, messages, schemas):
        """İlk tur (akışsız): (metin, araç_çağrıları). Araç çağırmadan eylem iddiası varsa bir kez zorlar."""
        msg = _get(self._chat(messages, schemas, False, 0.3), "message")
        content = (_get(msg, "content", "") or "").strip()
        calls = list(_get(msg, "tool_calls") or [])
        if not calls:
            calls = self._parse_text_call(content)
            if calls:
                print(f"\n[uyarı] araç düz metin olarak yazıldı ({content!r}); gerçek çağrıya çevrildi", flush=True)
                return "", calls
        if not calls and ACTION_CLAIM.search(content):
            print(f"\n[uyarı] araç çağırmadan eylem bildirdi ({content!r}); yeniden deneniyor", flush=True)
            retry = messages + [{"role": "assistant", "content": content}, {"role": "user", "content": NUDGE}]
            msg2 = _get(self._chat(retry, schemas, False, 0.0), "message")
            calls = list(_get(msg2, "tool_calls") or [])
            content = "" if calls else FAIL_TEXT
        return content, calls

    def _fast_route(self, text: str) -> list[tuple[str, dict]]:
        """Kural tabanlı hızlı yol: (araç adı, argümanlar) listesi döndürür (boşsa model karar verir)."""
        calls = []
        if "get_weather" in self.tools and WORD_WEATHER.search(text) and not CITY_NAMED.search(text):
            return [("get_weather", {"day": "yarın"} if "yarın" in text.lower() else {})]
        if "read_file" in self.tools and WORD_READ.search(text) and WORD_FILE.search(text):
            name = re.sub(r"\s+", " ", READ_FILLER.sub(" ", text)).strip(" .,?!")
            name = re.sub(r"(\.\w+)['’]\w+", r"\1", name)  # "rapor.pdf'yi" -> "rapor.pdf"
            if name:
                return [("read_file", {"name": name})]
        if NOT_A_QUERY.search(text):
            return calls
        if WORD_TIME.search(text) and ASKING.search(text) and "get_time" in self.tools:
            calls.append(("get_time", {}))
        if WORD_DATE.search(text) and "get_date" in self.tools:
            calls.append(("get_date", {}))
        return calls

    def _run_calls(self, messages, calls):
        """Araçları çalıştırır, sonuç metinlerini döndürür."""
        results = []
        messages.append({"role": "assistant", "content": "", "tool_calls": calls})
        for call in calls:
            fn = _get(call, "function")
            name = _get(fn, "name")
            args = dict(_get(fn, "arguments", {}) or {})
            result = self._call_tool(name, args)
            print(f"\n[araç] {name}({args}) -> {result}", flush=True)
            messages.append({"role": "tool", "tool_name": name, "content": result})
            results.append("Bunu yapamadım." if result.startswith("Hata:") else result)
        return results

    def reply_stream(self, user_text: str):
        """Kullanıcı cümlesine cevabı parça parça (str) üretir.

        İlk tur akışsız (araç kararı ve güvenlik ağı için); araç çalıştıktan sonraki cevap akışlı.
        """
        # Bekleyen tehlikeli işlem varsa kullanıcının cevabı MODELE GİTMEDEN burada değerlendirilir.
        if confirm.has_pending():
            verdict = confirm.classify(user_text)
            if verdict == "yes":
                yield confirm.approve()
                return
            confirm.cancel()
            if verdict == "no":
                yield "Tamam, vazgeçtim."
                return
        messages = [{"role": "system", "content": self.system}, *self.history,
                    {"role": "user", "content": user_text}]
        schemas = [schema for schema, _ in self.tools.values()]
        spoken: list[str] = []

        fast = self._fast_route(user_text)
        if fast and not any(n in FOLLOWUP_TOOLS for n, _ in fast):
            results = self._run_calls(messages, [{"function": {"name": n, "arguments": a}} for n, a in fast])
            text = " ".join(results)
            spoken.append(text)
            yield text
        else:
            if fast:  # araç kural ile seçildi, ama cevabı model üretecek (ör. dosya özeti)
                content, calls = "", [{"function": {"name": n, "arguments": a}} for n, a in fast]
            else:
                content, calls = self._decide(messages, schemas)
            if not calls:
                if content:
                    spoken.append(content)
                    yield content
            else:
                results: list[str] = []
                for _ in range(MAX_TOOL_ROUNDS):
                    results += self._run_calls(messages, calls)
                    if confirm.has_pending():  # onay sorusu aynen söylenir; model "yaptım" diye yorum katmasın
                        text = " ".join(results)
                        spoken.append(text)
                        yield text
                        break
                    calls = []
                    for chunk in self._chat(messages, schemas, True, 0.3):
                        msg = _get(chunk, "message")
                        piece = _get(msg, "content", "") or ""
                        if piece:
                            spoken.append(piece)
                            yield piece
                        calls.extend(_get(msg, "tool_calls") or [])
                    if not calls:
                        break
                if not "".join(spoken).strip():  # model araçtan sonra sustu: araç sonucunu söyle
                    text = " ".join(results)
                    if "dosyasının içeriği" in text:  # ham dosya içeriği sesli okunmasın
                        text = FAIL_TEXT
                    spoken.append(text)
                    yield text

        # Geçmişe araç çağrıları ve sonuçları da yazılır; yoksa model "araç çağırmadan 'açıldı' demek yeter"
        # kalıbını öğrenir ve sonraki komutlarda aracı atlar.
        turn = messages[1 + len(self.history):]
        turn.append({"role": "assistant", "content": "".join(spoken).strip()})
        self.history.extend(turn)
        self.history = self.history[-MAX_HISTORY:]
        while self.history and self.history[0].get("role") != "user":
            self.history.pop(0)  # kesilen bir araç alışverişinin ortasından başlama


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
