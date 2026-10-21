"""Model yönlendirici: yerel model varsayılan; zor işler için ÜCRETSİZ bulut modelleri (yedek zincirli).

- Yerel (Ollama) her şeyi yapar: sohbet, araçlar, kişisel veri. Bulut YALNIZCA açıkça çağrılan zor işlerde (kod, plan, genel soru) kullanılır.
- Buluta giden her mesaj önce privacy.gate'ten geçer; kişisel veri/parola/anahtar bulunursa HİÇ gönderilmez (Blocked).
- Sağlayıcılar OpenAI uyumlu uçlardır. Anahtarlar ortam değişkeninden ya da data/keys.env (git'e gitmez) dosyasından okunur.
- Sınır/hata yönetimi: 429 -> Retry-After kadar bekletip sıradaki modele; 401/403 -> sağlayıcı kapatılır; 404 -> model kapatılır;
  5xx/zaman aşımı -> kısa bekleme. Hepsi tükenirse Unavailable; çağıran yerel modele döner.
- Ücretsiz katmanlar küçüktür (Groq: dakikada ~8K token): büyük girdi hiç gönderilmeden reddedilir (TooLarge).
- data/models.json ile sağlayıcı/model eklenip çıkarılabilir (örnek: README).
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import privacy
from privacy import Blocked  # noqa: F401  (dışarıya aç)
from skills import _store

CLOUD_TASKS = {"hard", "code", "plan"}
UA = "jarvis-local/2.0"
CHARS_PER_TOKEN = 2.5  # Türkçe için kaba ve temkinli
DEFAULTS = {
    "order": ["groq"],
    "providers": {
        "groq": {
            "label": "Groq",
            "base_url": "https://api.groq.com/openai/v1",
            "key_env": "GROQ_API_KEY",
            "models": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"],
            "max_input_tokens": 5000,
        },
    },
}


class Unavailable(Exception):
    """Hiçbir bulut modeli cevap veremedi (anahtar yok, sınır dolu, ağ yok...). wait: limit dolduysa en erken kaç sn sonra denenebilir."""
    wait: float | None = None


class TooLarge(Exception):
    """Girdi ücretsiz katmanın küçük sınırına sığmıyor; bulut denenmedi."""


@dataclass
class Reply:
    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    ms: int = 0
    truncated: bool = False


# ------------------------------------------------------------------ yardımcılar
def load_env(extra: list[Path] | None = None) -> list[str]:
    """data/keys.env ve proje .env dosyalarını okur (ortamda zaten olan değişkeni ezmez). Okunan dosyaların adını döndürür."""
    paths = [_store.DATA_DIR / "keys.env", Path(__file__).resolve().parent / ".env", *(extra or [])]
    used = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        used.append(str(p))
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().removeprefix("export ").strip(), v.strip().strip("\"'")
            if k and v and k not in os.environ:
                os.environ[k] = v
    return used


ENV_TEMPLATE = """# Ücretsiz bulut modeli anahtarları. Bu dosya data/ klasöründedir: git'e GİTMEZ. Anahtarları sohbete yapıştırma.
# Değeri '=' işaretinden sonra, tırnaksız yaz. Boş bırakılan sağlayıcı kullanılmaz.
GROQ_API_KEY=
# İsteğe bağlı (kart istemeyen başka sağlayıcılar eklersen data/models.json'a da tanımla):
# MISTRAL_API_KEY=
# GEMINI_API_KEY=
"""


def init_env_file() -> Path:
    p = _store.DATA_DIR / "keys.env"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(ENV_TEMPLATE, encoding="utf-8")
    try:
        p.chmod(0o600)  # yalnızca sen okuyabil
    except OSError:
        pass
    return p


def http_post(url: str, headers: dict, body: dict, timeout: float):
    """(durum, başlıklar(küçük harf), json). Ağ hatasında istisna fırlatır."""
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310  (https sağlayıcı adresleri)
            return r.status, {k.lower(): v for k, v in r.headers.items()}, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except ValueError:
            data = {"error": {"message": raw[:200]}}
        return e.code, {k.lower(): v for k, v in e.headers.items()}, data


def _err_text(data) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "")[:160]
    return str(err or "")[:160]


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    if isinstance(extra.get("order"), list):
        out["order"] = [str(x) for x in extra["order"]]
    for pid, p in (extra.get("providers") or {}).items():
        if isinstance(p, dict):
            out["providers"].setdefault(pid, {}).update(p)
            if pid not in out["order"] and not p.get("disabled"):
                out["order"].append(pid)
    return out


THINK = re.compile(r"<think>.*?</think>", re.S)


class Router:
    def __init__(self, cfg: dict | None = None, post=http_post, now=time.time):
        load_env()
        self.cfg = _merge(DEFAULTS, cfg if cfg is not None else _store.load("models.json", {}))
        self.post, self.now = post, now
        self._cool: dict[str, float] = {}
        self._dead_models: dict[str, str] = {}
        self._dead_providers: dict[str, str] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ durum
    @staticmethod
    def enabled() -> bool:
        return bool(_store.load("settings.json", {}).get("cloud", True))

    def _key(self, p: dict) -> str:
        return os.environ.get(p.get("key_env", ""), "").strip()

    def _stats(self) -> dict:
        st = _store.load("router_stats.json", {})
        today = time.strftime("%Y-%m-%d", time.localtime(self.now()))
        if st.get("day") != today:
            st = {"day": today, "models": {}, "blocked": 0, "last_block": st.get("last_block", "")}
        return st

    def _note(self, key: str, ok: bool, tokens: int = 0, err: str = "") -> None:
        with self._lock:
            st = self._stats()
            m = st["models"].setdefault(key, {"calls": 0, "ok": 0, "tokens": 0, "err": ""})
            m["calls"] += 1
            m["ok"] += int(ok)
            m["tokens"] += tokens
            m["last"] = self.now()
            m["err"] = "" if ok else err
            _store.save("router_stats.json", st)

    def _note_block(self, why: str) -> None:
        with self._lock:
            st = self._stats()
            st["blocked"] = st.get("blocked", 0) + 1
            st["last_block"] = why
            _store.save("router_stats.json", st)

    def status(self) -> dict:
        st = self._stats()
        now = self.now()
        provs = []
        for pid in self.cfg["order"]:
            p = self.cfg["providers"].get(pid)
            if not p:
                continue
            if p.get("disabled"):
                state = "devre dışı"
            elif not self._key(p):
                state = "anahtar yok"
            elif pid in self._dead_providers:
                state = "anahtar reddedildi"
            else:
                state = "hazır"
            models = []
            for m in p.get("models", []):
                k = f"{pid}/{m}"
                s = st["models"].get(k, {})
                if k in self._dead_models:
                    ms = "kapalı"
                elif self._cool.get(k, 0) > now:
                    ms = "bekliyor"
                else:
                    ms = "hazır"
                models.append({"name": m, "state": ms, "wait": max(0, int(self._cool.get(k, 0) - now)), "calls": s.get("calls", 0),
                               "tokens": s.get("tokens", 0), "err": s.get("err", "")})
            provs.append({"id": pid, "label": p.get("label", pid), "state": state, "models": models})
        return {"enabled": self.enabled(), "providers": provs, "blocked": st.get("blocked", 0), "last_block": st.get("last_block", ""),
                "calls": sum(m["calls"] for m in st["models"].values()), "tokens": sum(m["tokens"] for m in st["models"].values())}

    def wait_hint(self) -> float | None:
        """Anahtarı olan canlı modeller arasında en erken hazır olacak olana kaç saniye var (0: şimdi hazır). Hiç aday yoksa None."""
        now, best = self.now(), None
        for pid in self.cfg["order"]:
            p = self.cfg["providers"].get(pid)
            if not p or p.get("disabled") or not self._key(p) or pid in self._dead_providers:
                continue
            for m in p.get("models", []):
                k = f"{pid}/{m}"
                if k in self._dead_models:
                    continue
                w = max(0.0, self._cool.get(k, 0) - now)
                best = w if best is None else min(best, w)
        return best

    def ready(self) -> bool:
        return self.enabled() and bool(list(self._candidates()))

    # ------------------------------------------------------------------ çağrı
    def _candidates(self):
        now = self.now()
        for pid in self.cfg["order"]:
            p = self.cfg["providers"].get(pid)
            if not p or p.get("disabled") or not self._key(p) or pid in self._dead_providers:
                continue
            for m in p.get("models", []):
                k = f"{pid}/{m}"
                if k not in self._dead_models and self._cool.get(k, 0) <= now:
                    yield pid, p, m

    def chat(self, messages: list[dict], *, task: str = "hard", max_tokens: int = 1200, temperature: float = 0.2,
             json_mode: bool = False, effort: str = "medium", timeout: float = 60,
             models: list[str] | None = None, extra: dict | None = None) -> Reply:
        """Bulut modeline sorar. Blocked: gizlilik/ayar; TooLarge: girdi büyük; Unavailable: hiçbiri cevap veremedi."""
        if task not in CLOUD_TASKS:
            raise Blocked(f"'{task}' görevi buluta gönderilemez")
        if not self.enabled():
            raise Blocked("bulut modelleri Ayarlar'dan kapalı")
        try:
            clean = privacy.gate(messages)
        except Blocked as b:
            self._note_block(b.text)
            raise
        size = sum(len(m["content"]) for m in clean)
        errors: list[str] = []
        tried = 0
        cands = list(self._candidates())
        if models:  # verilen listedeki sıra geçerli (örn. aramada önce küçük/hızlı model)
            cands = sorted((c for c in cands if c[2] in models), key=lambda c: models.index(c[2]))
        for pid, p, model in cands:
            if pid in self._dead_providers:
                continue
            if size / CHARS_PER_TOKEN > int(p.get("max_input_tokens", 5000)):
                raise TooLarge(f"girdi ~{int(size / CHARS_PER_TOKEN)} token; ücretsiz sınır ~{p.get('max_input_tokens', 5000)}")
            key = f"{pid}/{model}"
            body = {"model": model, "messages": clean, "temperature": temperature, "max_tokens": max_tokens}
            if model.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = effort
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            if extra:
                body.update(extra)
            tried += 1
            t0 = self.now()
            res = self._attempt(pid, p, model, key, body, timeout, errors)
            if res is not None:
                res.ms = int((self.now() - t0) * 1000)
                return res
        hint = self.wait_hint()
        if errors:
            why = "; ".join(errors[-4:])
        elif hint is None:
            why = "anahtar tanımlı değil (data/keys.env)"
        elif hint > 0:
            why = f"tüm bulut modelleri limitte/beklemede (en erken ~{int(hint) + 1} sn sonra)"
        else:
            why = "cevap alınamadı"
        exc = Unavailable(why)
        exc.wait = hint if hint else None
        raise exc

    SEARCH_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]  # Groq'un sunucu tarafı 'browser_search' aracını destekleyenler

    def search(self, query: str) -> str:
        """Groq'un yerleşik web aramasıyla (gpt-oss + browser_search) soruyu arar; yalnızca sorgu buluta gider (gizlilik kapısından geçer)."""
        rep = self.chat([{"role": "system", "content": "Web'de ara ve bulduklarını kısaca, kaynak site adlarıyla özetle. Fiyat ve tarih gibi sayıları aynen ver."},
                         {"role": "user", "content": query}], task="hard", max_tokens=900, effort="low", timeout=45,
                        models=self.SEARCH_MODELS, extra={"tools": [{"type": "browser_search"}], "tool_choice": "required"})
        return rep.text

    def _send(self, p: dict, body: dict, timeout: float):
        headers = {"Authorization": f"Bearer {self._key(p)}", "Content-Type": "application/json", "User-Agent": UA, "Accept": "application/json"}
        return self.post(p["base_url"].rstrip("/") + "/chat/completions", headers, body, timeout)

    def _attempt(self, pid, p, model, key, body, timeout, errors):
        now = self.now
        for second_try in (False, True):
            try:
                status, hdr, data = self._send(p, body, timeout)
            except Exception as exc:  # noqa: BLE001  (ağ yok, zaman aşımı...)
                self._cool[key] = now() + 30
                self._note(key, False, err=type(exc).__name__)
                errors.append(f"{key}: ağ hatası ({type(exc).__name__})")
                return None
            if status == 200:
                try:
                    ch = data["choices"][0]
                    text = THINK.sub("", ch["message"].get("content") or "").strip()
                except (KeyError, IndexError, TypeError, AttributeError):
                    text = ""
                if not text:
                    self._cool[key] = now() + 20
                    self._note(key, False, err="boş cevap")
                    errors.append(f"{key}: boş cevap")
                    return None
                u = data.get("usage") or {}
                tin, tout = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
                self._note(key, True, tokens=tin + tout)
                return Reply(text, pid, model, tin, tout, truncated=ch.get("finish_reason") == "length")
            msg = _err_text(data)
            if status == 400 and not second_try and ("reasoning_effort" in body or "response_format" in body):
                body = {k: v for k, v in body.items() if k not in ("reasoning_effort", "response_format")}  # bu model bilmiyor: onsuz dene
                continue
            break
        self._note(key, False, err=f"{status} {msg}"[:100])
        errors.append(f"{key}: {status} {msg}"[:120])
        if status == 429:
            try:
                wait = float(hdr.get("retry-after", "") or 60)
            except ValueError:
                wait = 60.0
            self._cool[key] = now() + min(max(wait, 5.0), 3600.0)
        elif status in (401, 403):
            self._dead_providers[pid] = f"{status}"
        elif status == 404 or "model_not_found" in msg or "decommissioned" in msg:
            self._dead_models[key] = msg or str(status)
        elif status == 413:
            self._cool[key] = now() + 60
        else:
            self._cool[key] = now() + (30 if status >= 500 else 60)
        return None


_ROUTER: Router | None = None


def get() -> Router:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = Router()
    return _ROUTER
