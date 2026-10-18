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
import itertools
import os
import re
import threading
import time

import ollama

from skills import _confirm as confirm
from skills import _store
from skills import browser as _browser
from skills import files as _files
from skills import HIDDEN, capability_summary, load_skills

MODEL = "gemma4:e4b"
MAX_HISTORY = 16
MAX_TOOL_ROUNDS = 3
# Birincil model hata verirse (Ollama kapalı, model yok, bellek yetmedi) sırayla denenecek yedekler.
FALLBACKS = [m.strip() for m in os.environ.get("JARVIS_FALLBACK_MODELS", "qwen3:8b").split(",") if m.strip()]
PRIMARY_RETRY_S = 300  # yedeğe düştükten sonra birincil model bu kadar saniye denenmez
SESSION_FILE = "session.json"
SESSION_TTL = 12 * 3600  # bundan eski konuşma geçmişi yüklenmez
# Uzaktan (Telegram) gelen komutlarda çalıştırılmayan araçlar: içerik makine dışına, üçüncü taraf sunucuya çıkar.
REMOTE_BLOCKED = {"read_file", "recall", "look_at_screen", "browser_open", "browser_read", "browser_click",
                  "browser_type", "browser_back", "browser_close"}

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
    r"\b(open_app|set_volume|change_volume|get_time|get_date|web_search|list_abilities|remember|recall|forget|set_reminder|list_reminders|cancel_reminders|get_weather|get_battery|morning_brief|look_at_screen|browser_open|browser_read|browser_click|browser_type|browser_back|browser_close|get_system_status|find_files|read_file|move_file|trash_file|undo_last_action)\b",
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
WORD_BATTERY = re.compile(r"(\bpil\w*|batarya\w*|şarj\w*)\b.*\b(kaç|yüzde|durum\w*|ne kadar|seviye\w*|nasıl|kaldı)\b", re.I)
WORD_SCREEN = re.compile(r"\bekran\w*\b.*\b(ne var|bak\w*|oku\w*|anlat\w*|özetle\w*|göster\w*|yazıyor|görüyor\w*)\b", re.I)
WORD_SCREEN_NOT = re.compile(r"karart|aydınlat|parlak|kapat|kilitle|görüntüsü al|ekran görüntüsü|kaydet", re.I)
WORD_HW = re.compile(r"\b(cpu|işlemci\w*|ram|vram|gpu|ekran kart\w*|disk\w*|depolama\w*|sistem durumu\w*|bilgisayar\w*\s+(nasıl|durumu|ne durumda|sıcaklığ\w*)|donanım\w*)\b", re.I)
WORD_RESET = re.compile(r"konuşmayı\s+(sıfırla|unut|temizle)|yeni konuşma|baştan başla|geçmişi\s+(sil|temizle|unut)", re.I)
WORD_BRIEF = re.compile(r"günaydın|günün özeti|sabah özeti|bugün neler var|bugünün özeti|özet ver", re.I)
WORD_CONTEXT_REF = re.compile(r"\b(onu|bunu|şunu|ilk\w*|birinci\w*|ikinci\w*|üçüncü\w*|dördüncü\w*|beşinci\w*)\b", re.I)
FOLLOWUP_TOOLS = {"read_file", "web_search", "browser_read"}  # sonucu doğrudan okunmaz; model özetleyip cevaplar
# Dışarıdan gelen metin döndüren araçlar: sonrasındaki model turunda ARAÇ KAPALI (prompt injection araç çağıramasın).
UNTRUSTED_TOOLS = {"read_file", "web_search", "browser_read", "look_at_screen"}
WORD_UNDO = re.compile(r"geri al|eski haline|eskisi gibi|önceki haline|eski seviyesine|az önceki(ni)? (iptal|geri)", re.I)
_TLD = r"(?:com|org|net|io|dev|edu|gov|tr|co|info|app|ai|me)"
BR_SITE = re.compile(r"\b((?:[a-z0-9\-]+\.)+" + _TLD + r"(?:/[^\s]*)?)", re.I)
BR_ALIAS = re.compile(r"\b(youtube|github|vikipedi|wikipedia|stack\s?overflow|google|duckduckgo)\w*", re.I)
BR_OPEN = re.compile(r"\b(git|gir|aç|açar mısın|aralım|bak)\b", re.I)
BR_BROWSERWORD = re.compile(r"tarayıcı|site\w*|sayfa\w*", re.I)
BR_READ = re.compile(r"sayfa\w*\s+(oku|özetle|anlat)\w*|sayfada ne|sayfa ne diyor|sayfanın özeti|ne yazıyor", re.I)
BR_BACK = re.compile(r"geri (git|dön)|önceki sayfa", re.I)
BR_CLOSE = re.compile(r"tarayıcı\w*\s+kapat", re.I)
BR_CLICK = re.compile(r"^(?:şu\s+)?(?P<t>.+?)(?:['’]\w+)?\s+(?:(?:butonuna|düğmesine|linkine|bağlantısına|sekmesine)\s+)?(?:tıkla\w*|bas\w*)\s*$", re.I)
BR_TYPE = re.compile(r"^(?:(?P<f>.+?)\s+(?:kutusuna|alanına|kısmına|satırına)\s+)?(?P<t>.+?)\s+yaz\w*(?P<s>\s+ve\s+(?:ara\w*|gönder\w*|enter\w*))?\s*$", re.I)
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
        self.persist = False           # True: konuşma geçmişi data/session.json'a yazılır (main.py açar)
        self._skip_primary_until = 0.0
        self.lock = threading.RLock()  # ses döngüsü ve Telegram aynı beyni sırayla kullanır
        self.remote = False            # True iken (Telegram) REMOTE_BLOCKED araçlar reddedilir

    # -- ısınma: modeli belleğe al (ilk cevap gecikmesi azalır)
    def warm_up(self):
        """Modeli belleğe alır; birincil model açılmazsa yedeklere düşer (bkz. _chat)."""
        t0 = time.perf_counter()
        self._chat([{"role": "user", "content": "merhaba"}], None, False, 0.3)
        return time.perf_counter() - t0

    def _call_tool(self, name: str, args: dict) -> str:
        entry = self.tools.get(name)
        if not entry:
            return f"Hata: '{name}' adında bir araç yok."
        if self.remote and name in REMOTE_BLOCKED:
            return "Bunu güvenlik nedeniyle uzaktan yapmıyorum, bilgisayarın başındayken sor."
        try:
            return str(entry[1](**(args or {})))
        except Exception as exc:  # noqa: BLE001
            return f"Hata: {type(exc).__name__}: {exc}"

    def _candidates(self) -> list[str]:
        models = [self.model] + [m for m in FALLBACKS if m != self.model]
        if len(models) > 1 and time.time() < self._skip_primary_until:
            models = models[1:] + models[:1]  # yedekte kalınan süre: birincil en sona
        return models

    def _chat(self, messages, schemas, stream: bool, temperature: float):
        """Model çağrısı; birincil model hata verirse yedek modellere düşer (akışta hata ilk parçada belli olur)."""
        last_exc: Exception | None = None
        for model in self._candidates():
            kw = dict(model=model, messages=messages, tools=schemas or None, stream=stream,
                      options={"temperature": temperature}, keep_alive="30m", **self._think_kw)
            try:
                try:
                    result = ollama.chat(**kw)
                    if stream:
                        it = iter(result)
                        first = next(it, None)
                        result = itertools.chain([first], it) if first is not None else iter(())
                except Exception as exc:  # noqa: BLE001
                    if "think" not in str(exc).lower() or "think" not in kw:
                        raise
                    kw.pop("think")  # bu model 'think' bilmiyor: onsuz dene
                    result = ollama.chat(**kw)
                    if stream:
                        it = iter(result)
                        first = next(it, None)
                        result = itertools.chain([first], it) if first is not None else iter(())
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                print(f"\n[uyarı] {model} hata verdi ({type(exc).__name__}: {str(exc)[:80]}); sıradaki model deneniyor", flush=True)
                continue
            if model != self.model:
                if time.time() >= self._skip_primary_until:
                    print(f"\n[uyarı] yedek model kullanılıyor: {model}", flush=True)
                self._skip_primary_until = time.time() + PRIMARY_RETRY_S
            else:
                self._skip_primary_until = 0.0
            return result
        raise last_exc  # type: ignore[misc]

    # -- oturum devamlılığı: konuşma geçmişi yeniden başlatmada kaybolmasın
    @staticmethod
    def _plain_msg(m: dict) -> dict:
        out = {"role": m.get("role"), "content": (m.get("content") or "")[:600] if m.get("role") == "tool" else (m.get("content") or "")}
        if m.get("tool_name"):
            out["tool_name"] = m["tool_name"]
        if m.get("tool_calls"):
            out["tool_calls"] = [{"function": {"name": _get(_get(c, "function"), "name"),
                                               "arguments": dict(_get(_get(c, "function"), "arguments", {}) or {})}}
                                 for c in m["tool_calls"]]
        return out

    def save_session(self) -> None:
        if self.persist:
            try:
                _store.save(SESSION_FILE, {"ts": time.time(), "history": [self._plain_msg(m) for m in self.history]})
            except Exception as exc:  # noqa: BLE001  (kayıt hatası konuşmayı bozmasın)
                print(f"[uyarı] oturum kaydedilemedi: {type(exc).__name__}", flush=True)

    def enable_persistence(self) -> int:
        """Kayıtlı geçmişi (12 saatten yeniyse) yükler ve her turdan sonra kaydetmeyi açar. Yüklenen mesaj sayısını döndürür."""
        self.persist = True
        data = _store.load(SESSION_FILE, {})
        if time.time() - data.get("ts", 0) > SESSION_TTL:
            return 0
        hist = [m for m in data.get("history", []) if isinstance(m, dict) and m.get("role")]
        while hist and hist[0].get("role") != "user":
            hist.pop(0)
        self.history = hist[-MAX_HISTORY:]
        return len(self.history)

    def reset(self):
        self.history.clear()
        if self.persist:
            _store.save(SESSION_FILE, {"ts": time.time(), "history": []})

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

    def _browser_route(self, text: str) -> list[tuple[str, dict]]:
        if "browser_open" not in self.tools:
            return []
        active = _browser.is_active()
        t = text.strip().strip(".!?")
        if active and BR_CLOSE.search(t):
            return [("browser_close", {})]
        if active and BR_BACK.search(t):
            return [("browser_back", {})]
        if active and BR_READ.search(t):
            return [("browser_read", {})]
        site = BR_SITE.search(t)
        alias = BR_ALIAS.search(t)
        if BR_OPEN.search(t) and not WORD_FILE.search(t) and (site or (alias and (active or BR_BROWSERWORD.search(t)))):
            return [("browser_open", {"url": site.group(1) if site else alias.group(1)})]
        if active:
            m = BR_TYPE.match(t)
            if m:
                return [("browser_type", {"field": (m.group("f") or "").strip(), "text": m.group("t").strip(" '\"“”"),
                                          "submit": bool(m.group("s"))})]
            m = BR_CLICK.match(t)
            if m:
                return [("browser_click", {"text": m.group("t").strip(" '\"“”")})]
        return []

    def _fast_route(self, text: str) -> list[tuple[str, dict]]:
        """Kural tabanlı hızlı yol: (araç adı, argümanlar) listesi döndürür (boşsa model karar verir)."""
        calls = []
        if "get_system_status" in self.tools and WORD_HW.search(text) and not NOT_A_QUERY.search(text):
            m = WORD_HW.search(text).group(1).lower()
            part = ("cpu" if m in ("cpu",) or m.startswith("işlemci") else "ram" if m in ("ram",) else
                    "gpu" if m in ("gpu", "vram") or m.startswith("ekran kart") else
                    "disk" if m.startswith(("disk", "depolama")) else "")
            return [("get_system_status", {"part": part})]
        if "get_weather" in self.tools and WORD_WEATHER.search(text) and not CITY_NAMED.search(text):
            return [("get_weather", {"day": "yarın"} if "yarın" in text.lower() else {})]
        if "undo_last_action" in self.tools and WORD_UNDO.search(text):
            return [("undo_last_action", {})]
        br = self._browser_route(text)
        if br:
            return br
        if "get_battery" in self.tools and WORD_BATTERY.search(text) and not NOT_A_QUERY.search(text):
            return [("get_battery", {})]
        if "look_at_screen" in self.tools and WORD_SCREEN.search(text) and not WORD_SCREEN_NOT.search(text):
            return [("look_at_screen", {"question": text})]
        if "morning_brief" in self.tools and WORD_BRIEF.search(text):
            return [("morning_brief", {})]
        if "read_file" in self.tools and WORD_READ.search(text) and not WORD_FILE.search(text) and WORD_CONTEXT_REF.search(text):
            ref = WORD_CONTEXT_REF.search(text).group(1)  # "onu oku", "ikincisini özetle": son 'dosya bul' sonucuna gönderme
            if _files.has_context():
                return [("read_file", {"name": ref})]
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
        if WORD_RESET.search(user_text):
            confirm.cancel()
            self.reset()
            yield "Tamam, konuşmayı sıfırladım."
            return
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
        schemas = [schema for name, (schema, _) in self.tools.items() if name not in HIDDEN]
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
                follow_schemas = schemas
                for _ in range(MAX_TOOL_ROUNDS):
                    if any(_get(_get(c, "function"), "name") in UNTRUSTED_TOOLS for c in calls):
                        follow_schemas = []  # dış içerik okundu: bu turdan sonra model araç çağıramaz
                    results += self._run_calls(messages, calls)
                    if confirm.has_pending():  # onay sorusu aynen söylenir; model "yaptım" diye yorum katmasın
                        text = " ".join(results)
                        spoken.append(text)
                        yield text
                        break
                    calls = []
                    for chunk in self._chat(messages, follow_schemas, True, 0.3):
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
                    if "yalnızca veri" in text:  # ham dosya içeriği / arama sonucu sesli okunmasın
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
        self.save_session()


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
