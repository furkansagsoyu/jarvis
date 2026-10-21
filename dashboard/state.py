"""Pano durumu: her panel bir 'sağlayıcı' (provider) fonksiyonudur. Yeni özellik = yeni sağlayıcı ekle.

    @provider("ornek")
    def _(ctx): return {...}          # app.js içinde de PANELS["ornek"] ile çizilir

Bir sağlayıcı hata verirse yalnızca o panel boş kalır, pano çalışmaya devam eder.
Gerçek veri yoksa sahte değer ÜRETİLMEZ; arayüz 'Yakında' / '—' gösterir.
"""
from __future__ import annotations

import os
import shutil
import socket
import threading
import time
from collections import deque
from pathlib import Path

import ui_state
from skills import _store, agenda, hardware

START = time.time()
PROVIDERS: dict = {}
FEED: deque = deque(maxlen=30)  # {"ts","level","text"}; notify() ve komutlar buraya yazar
_cache: dict = {}
_cache_lock = threading.Lock()


def provider(name: str):
    def deco(fn):
        PROVIDERS[name] = fn
        return fn
    return deco


def feed(level: str, text: str) -> None:
    """Canlı akışa satır ekler. level: BİLGİ | UYARI | GÖREV | KOMUT."""
    if text:
        FEED.appendleft({"ts": time.time(), "level": level, "text": str(text)[:200]})


def cached(key: str, ttl: float, fn):
    """Yavaş kaynakları (ağ, ollama) ttl saniye önbellekler; hata olursa son değeri korur."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        val = fn()
    except Exception:  # noqa: BLE001
        val = hit[1] if hit else None
    with _cache_lock:
        _cache[key] = (now, val)
    return val


_bg_running: set = set()


def cached_bg(key: str, ttl: float, fn, default=None):
    """Ağ gibi yavaş/takılabilen kaynaklar: istek asla beklemez. Bayatsa arka planda yenilenir, o ana dek bilinen değer döner.
    Başarısız (boş) sonuç 60 sn sonra yeniden denenir (internet sonradan gelirse pano toparlansın)."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        last = hit[1] if hit else default
        if key in _bg_running:
            return last
        _bg_running.add(key)

    def work():
        try:
            val = fn()
        except Exception:  # noqa: BLE001
            val = last
        stamp = time.time() if val else time.time() - ttl + min(60.0, ttl)
        with _cache_lock:
            _cache[key] = (stamp, val)
            _bg_running.discard(key)

    threading.Thread(target=work, daemon=True).start()
    return last


# ------------------------------------------------------------ arka plan örnekleyici (istek başına bekleme olmasın)
class Sampler(threading.Thread):
    def __init__(self, every: float = 2.0):
        super().__init__(daemon=True)
        self.every = every
        self.cpu = 0.0
        self.hist: deque = deque(maxlen=40)

    def run(self):
        while True:
            try:
                self.cpu = hardware.cpu_percent(0.5)
                self.hist.append(round(self.cpu))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self.every)


SAMPLER = Sampler()


def _online() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1.5).close()
        return True
    except OSError:
        return False


def _ollama_models() -> list[str]:
    import ollama  # noqa: PLC0415
    res = ollama.list()
    ms = res.get("models") if isinstance(res, dict) else getattr(res, "models", [])
    out = []
    for m in ms or []:
        out.append(m.get("model") if isinstance(m, dict) else getattr(m, "model", ""))
    return [x for x in out if x]


def _temp_text() -> str:
    from skills import weather  # noqa: PLC0415
    t = weather.current_temp()
    return "" if t is None else f"{t}°C"


CATEGORIES = {"agenda": "Takvim ve görevler", "apps": "Uygulamalar", "battery": "Pil", "briefing": "Günün özeti", "brightness": "Parlaklık",
              "browser": "Tarayıcı", "camera": "Kamera", "clock": "Saat ve tarih", "desktop_input": "Fare ve klavye", "files": "Dosyalar",
              "hardware": "Donanım", "help": "Yardım", "memory": "Hafıza", "reminders": "Hatırlatıcılar", "screen": "Ekran",
              "undo": "Geri alma", "volume": "Ses", "weather": "Hava durumu", "web": "Web araması"}


def _tool_modules() -> dict:
    """araç adı -> kategori (skills modüllerinin SKILLS listelerinden)."""
    import sys  # noqa: PLC0415
    out = {}
    for modname, mod in list(sys.modules.items()):
        if modname.startswith("skills.") and not modname.split(".")[1].startswith("_"):
            key = modname.split(".")[1]
            for sk in getattr(mod, "SKILLS", []) or []:
                out[sk.get("name")] = CATEGORIES.get(key, key.replace("_", " ").capitalize())
    return out


# ------------------------------------------------------------ sağlayıcılar
@provider("durum")
def _durum(ctx):
    st = ui_state.read_status()
    try:
        from skills import _confirm  # noqa: PLC0415
        pending = _confirm.has_pending() or getattr(getattr(ctx.brain, "agent", None), "state", "idle") == "plan"
    except Exception:  # noqa: BLE001
        pending = False
    return {"state": st.get("state", "starting"), "label": ui_state.STATES.get(st.get("state"), "—"),
            "muted": ui_state.is_muted(), "focus": ui_state.is_focus(), "chat_voice": ui_state.chat_voice(), "close_to_tray": ui_state.close_to_tray(), "theme": ui_state.theme(), "pending": pending,
            "turns": st.get("turns", []), "uptime": int(time.time() - START)}


@provider("sistem")
def _sistem(ctx):
    used, total = hardware.parse_meminfo(Path("/proc/meminfo").read_text())
    d = shutil.disk_usage(Path.home())
    return {"cpu": round(SAMPLER.cpu), "cpu_hist": list(SAMPLER.hist), "cpu_temp": hardware.cpu_temp(),
            "ram": {"used": round(used, 1), "total": round(total, 1)},
            "disk": {"used": round((d.total - d.free) / 1e9), "total": round(d.total / 1e9)},
            "gpu": cached("gpu", 2.0, hardware.gpu_info)}


@provider("model")
def _model(ctx):
    brain = ctx.brain
    FALLBACKS = getattr(ctx, "fallbacks", None)
    if FALLBACKS is None:
        FALLBACKS = [m.strip() for m in os.environ.get("JARVIS_FALLBACK_MODELS", "qwen3:8b").split(",") if m.strip()]
    installed = cached("ollama", 30.0, _ollama_models)
    names = [(brain.model, "Birincil")] + [(m, "Yedek") for m in FALLBACKS if m != brain.model]
    llm = [{"name": n, "role": r, "active": n == getattr(brain, "active_model", brain.model),
            "installed": (n in installed) if installed is not None else None} for n, r in names]
    return {"llm": llm,
            "stt": "Whisper large-v3-turbo", "tts": "EMA Lightning (CPU)", "wake": "hey_jarvis",
            "tools": len(brain.tools), "tool_calls": getattr(brain, "tool_count", 0)}


@provider("hafiza")
def _hafiza(ctx):
    facts = _store.load("memory.json", [])
    return {"count": len(facts), "last": [f["text"] for f in facts[-3:]][::-1],
            "turns": len(getattr(ctx.brain, "history", [])) // 2,
            "summary": bool(getattr(ctx.brain, "summary", ""))}


@provider("ajanda")
def _ajanda(ctx):
    return agenda.snapshot()


@provider("ajanlar")
def _ajanlar(ctx):
    brain = ctx.brain
    ag = getattr(brain, "agent", None)
    ast = getattr(ag, "state", "idle")
    ag_status = {"running": "Çalışıyor", "confirm": "Onay bekliyor", "plan": "Plan onayı bekliyor"}.get(ast, "Hazır")
    has = lambda n: n in brain.tools  # noqa: E731
    return [
        {"name": "Ajan Modu", "status": ag_status, "detail": (getattr(ag, "goal", "") or "Çok adımlı görevler (plan + onay)")[:60] if ast != "idle" else "Çok adımlı görevler (plan + onay)"},
        {"name": "Tarayıcı", "status": "Hazır" if has("browser_open") else "Kapalı", "detail": "İzinli sitelerde gezinme"},
        {"name": "Takvim ve Görev", "status": "Hazır" if has("agenda_add") else "Kapalı", "detail": "Yerel takvim, 10 dk uyarı"},
        {"name": "Bilgisayar Kontrolü", "status": "Hazır" if has("mouse_click") else "Kapalı", "detail": "Fare ve klavye (onaylı)"},
        {"name": "Araştırma Ajanı", "status": "Yakında", "detail": "Çoklu ajan aşamasında"},
        {"name": "Kodlama Ajanı", "status": "Yakında", "detail": "Çoklu ajan aşamasında"},
    ]


@provider("akis")
def _akis(ctx):
    items = list(FEED)
    snap = agenda.snapshot()
    now = time.time()
    if snap["overdue"]:
        items.append({"ts": now, "level": "UYARI", "text": f"{snap['overdue']} geciken görev var"})
    if snap["next_event"]:
        items.append({"ts": now - 1, "level": "BİLGİ", "text": f"Sıradaki: {snap['next_event']['title']} ({snap['next_event']['when']})"})
    items.sort(key=lambda x: -x["ts"])
    return [{"time": time.strftime("%H:%M:%S", time.localtime(i["ts"])), "level": i["level"], "text": i["text"]} for i in items[:8]]


@provider("araclar")
def _araclar(ctx):
    brain = ctx.brain
    cats = cached("toolmods", 60.0, _tool_modules) or {}
    stats = getattr(brain, "tool_stats", {})
    out = []
    for name, entry in brain.tools.items():
        try:
            desc = entry[0]["function"]["description"]
        except (TypeError, KeyError, IndexError):
            desc = ""
        out.append({"name": name, "category": cats.get(name, "Diğer"), "desc": desc.strip(), "uses": stats.get(name, 0)})
    out.sort(key=lambda x: (x["category"], x["name"]))
    return out


@provider("konusma")
def _konusma(ctx):
    import convlog  # noqa: PLC0415
    return {"rev": convlog.revision(), "retention": convlog.retention_days(),
            "recent": [{"id": i["id"], "who": i["who"], "text": i["text"], "time": time.strftime("%H:%M", time.localtime(i["ts"]))}
                       for i in convlog.recent(30)]}


@provider("alt")
def _alt(ctx):
    return {"temp": cached_bg("temp", 900.0, _temp_text, "") or "",
            "online": bool(cached_bg("online", 20.0, _online, False)),
            "city": os.environ.get("JARVIS_CITY", "Tokat")}


def build_state(ctx) -> dict:
    out = {"ts": time.time(), "now": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for name, fn in PROVIDERS.items():
        try:
            out[name] = fn(ctx)
        except Exception as exc:  # noqa: BLE001
            out[name] = None
            out.setdefault("hatalar", {})[name] = f"{type(exc).__name__}: {exc}"[:120]
    return out
