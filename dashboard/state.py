"""Pano durumu: her panel bir 'sağlayıcı' (provider) fonksiyonudur. Yeni özellik = yeni sağlayıcı ekle.

    @provider("ornek")
    def _(ctx): return {...}          # app.js içinde de PANELS["ornek"] ile çizilir

Bir sağlayıcı hata verirse yalnızca o panel boş kalır, pano çalışmaya devam eder.
Gerçek veri yoksa sahte değer ÜRETİLMEZ; arayüz 'Yakında' / '—' gösterir.
"""
from __future__ import annotations

import os
import re
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
              "browser": "Tarayıcı", "camera": "Kamera", "codeagent": "Kod ajanı", "clock": "Saat ve tarih", "desktop_input": "Fare ve klavye", "files": "Dosyalar",
              "hardware": "Donanım", "help": "Yardım", "memory": "Hafıza", "phone": "Telefon (ADB)", "reminders": "Hatırlatıcılar", "screen": "Ekran",
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
        pending = _confirm.has_pending() or any(getattr(getattr(ctx.brain, k, None), "state", "idle") == "plan" for k in ("agent", "team"))
    except Exception:  # noqa: BLE001
        pending = False
    return {"state": st.get("state", "starting"), "label": ui_state.STATES.get(st.get("state"), "—"),
            "muted": ui_state.is_muted(), "focus": ui_state.is_focus(), "chat_voice": ui_state.chat_voice(), "close_to_tray": ui_state.close_to_tray(), "cloud": ui_state.cloud_enabled(), "theme": ui_state.theme(), "pending": pending,
            "turns": st.get("turns", []), "uptime": int(time.time() - START),
            "mascot": ui_state.mascot_state("muted" if ui_state.is_muted() else st.get("state", "starting"), pending, st.get("error_ts") or 0),
            "island": ui_state.island_settings()}


def island_snapshot(ctx) -> dict:
    """Üst kenardaki "ada" için hafif durum: {state, label, kind, question, id, left}.
    kind: "" | "confirm" (riskli işlem onayı, _confirm) | "plan" (ajan/ekip planı "Başlayayım mı?").
    id değişince ada eski cevabı geçersiz sayar (sunucu da denetler). Onay VERMEZ; yalnızca görüntü bilgisidir."""
    st = ui_state.read_status()
    state = "muted" if ui_state.is_muted() else st.get("state", "starting")
    out = {"state": state, "label": ui_state.STATES.get(state, "—"), "kind": "", "question": "", "id": "", "left": 0,
           "mascot": ui_state.mascot_state(state, False, st.get("error_ts") or 0),
           "cfg": {**ui_state.island_settings(), "theme": ui_state.island_theme()}}   # ada ayarları her yoklamada uygulanır
    try:
        from skills import _confirm  # noqa: PLC0415
        info = _confirm.pending_info()
    except Exception:  # noqa: BLE001
        info = None
    if info:
        out["mascot"] = ui_state.mascot_state(state, True, st.get("error_ts") or 0)
        return {**out, "kind": "confirm", "question": info["text"][:240], "id": f"c{info['id']}", "left": info["left"]}
    for key in ("team", "agent"):
        obj = getattr(ctx.brain, key, None)
        if getattr(obj, "state", "idle") == "plan":
            exp = float(getattr(obj, "plan_expires", 0) or 0)
            if exp and exp < time.time():
                continue
            last = next((t["text"] for t in reversed(st.get("turns") or []) if t.get("who") == "jarvis"), "")
            out["mascot"] = ui_state.mascot_state(state, True, st.get("error_ts") or 0)
            return {**out, "kind": "plan", "question": (last or "Plan onayını bekliyorum.")[:240],
                    "id": f"p{key}{int(exp * 1000)}", "left": max(0, int(exp - time.time()))}
    return out


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
    try:
        import router  # noqa: PLC0415
        cloud = (getattr(brain, "router", None) or router.get()).status()
    except Exception:  # noqa: BLE001
        cloud = None
    return {"llm": llm, "cloud": cloud,
            "stt": "Whisper large-v3-turbo", "tts": "EMA Lightning (CPU)", "wake": "hey_jarvis",
            "tools": len(brain.tools), "tool_calls": getattr(brain, "tool_count", 0)}


@provider("hafiza")
def _hafiza(ctx):
    from skills import memory  # noqa: PLC0415
    mem = memory.stats()
    return {"count": mem["count"], "last": mem["last"],
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
    team = getattr(brain, "team", None)
    snap = team.snapshot() if team else {"state": "idle", "goal": "", "active_role": "", "active_do": "", "done": 0, "total": 0, "tasks": []}
    tst = {"running": "Çalışıyor", "confirm": "Onay bekliyor", "plan": "Plan onayı bekliyor"}.get(snap["state"], "Hazır")
    rows = [
        {"name": "Ajan Modu", "status": ag_status, "detail": (getattr(ag, "goal", "") or "Çok adımlı görevler (plan + onay)")[:60] if ast != "idle" else "Çok adımlı görevler (plan + onay)"},
        {"name": "Ekip Modu", "status": tst, "detail": (f"{snap['goal'][:40]} — {snap['done']}/{snap['total']} görev" if snap["state"] != "idle"
                                                       else "Çoklu ajan: “ekip: …” ya da “araştır: …”")},
    ]
    try:
        import team as _team  # noqa: PLC0415
        for key, role in _team.ROLES.items():
            ready = all(t in brain.tools for t in role.tools[:1])
            busy = snap["state"] in ("running", "confirm") and snap["active_role"] == key
            where = "yalnızca yerel" if role.private else "bulut destekli (temiz veride), yoksa yerel"
            about = role.about[:1].upper() + role.about[1:]
            detail = about if where in about else f"{about}; {where}"   # "yalnızca yerel" iki kez yazılmasın
            rows.append({"name": role.title, "status": ("Çalışıyor" if busy else "Hazır") if ready else "Kapalı",
                         "detail": (snap["active_do"][:50] if busy else detail)})
    except Exception:  # noqa: BLE001
        pass
    rows += [
        {"name": "Tarayıcı", "status": "Hazır" if has("browser_open") else "Kapalı", "detail": "İzinli sitelerde gezinme"},
        {"name": "Takvim ve Görev", "status": "Hazır" if has("agenda_add") else "Kapalı", "detail": "Yerel takvim, 10 dk uyarı"},
        {"name": "Telefon (ADB)", "status": "Hazır" if has("phone_call") else "Kapalı", "detail": "Arama, rehber (her arama onaylı)"},
        {"name": "Bilgisayar Kontrolü", "status": "Hazır" if has("mouse_click") else "Kapalı", "detail": "Fare ve klavye (onaylı)"},
    ]
    return rows


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


TOOL_LABELS = {  # pano 'Araçlar ve Beceriler': iç araç adı -> kullanıcıya gösterilen Türkçe ad
    "agenda_add": "Takvime etkinlik ekle", "agenda_cancel": "Etkinliği iptal et", "agenda_list": "Takvimi göster",
    "browser_back": "Tarayıcıda geri git", "browser_click": "Sayfada tıkla", "browser_close": "Tarayıcıyı kapat",
    "browser_open": "Siteyi aç", "browser_play": "Şarkı/video oynat", "browser_read": "Sayfayı oku",
    "browser_type": "Sayfaya yaz", "cancel_reminders": "Hatırlatıcıları iptal et", "change_brightness": "Parlaklığı değiştir",
    "change_volume": "Sesi değiştir", "code_list": "Kod dosyalarını listele", "code_read": "Kod dosyasını oku",
    "code_run": "Kodu çalıştır", "code_write": "Kod dosyası yaz", "contact_add": "Rehbere kişi ekle",
    "contacts_sync": "Rehberi telefondan al", "find_files": "Dosya bul", "forget": "Bilgiyi unut",
    "get_battery": "Pil durumu", "get_date": "Bugünün tarihi", "get_system_status": "Sistem durumu",
    "get_time": "Saat", "get_volume": "Ses düzeyi", "get_weather": "Hava durumu",
    "keyboard_type": "Klavyeyle yaz", "list_abilities": "Yeteneklerimi say", "list_reminders": "Hatırlatıcıları listele",
    "look_at_camera": "Kameraya bak", "look_at_screen": "Ekrana bak", "mcp_call": "MCP aracını çalıştır",
    "mcp_list": "MCP araçlarını listele", "morning_brief": "Günaydın özeti", "mouse_click": "Fareyle tıkla",
    "mouse_move": "Fareyi hareket ettir", "move_file": "Dosyayı taşı", "open_app": "Uygulama aç",
    "phone_answer": "Aramayı cevapla", "phone_call": "Telefonla ara", "phone_hangup": "Aramayı kapat",
    "phone_ring": "Telefonu çaldır", "phone_status": "Telefon durumu", "press_key": "Tuşa bas",
    "read_file": "Dosyayı oku", "recall": "Hatırla (hafızadan getir)", "remember": "Not al (hafızaya kaydet)",
    "scroll": "Sayfayı kaydır", "set_brightness": "Parlaklığı ayarla", "set_reminder": "Hatırlatıcı kur",
    "set_volume": "Sesi ayarla", "system_health": "Sistem bakım raporu", "task_add": "Görev ekle",
    "task_delete": "Görevi sil", "task_done": "Görevi bitir", "task_list": "Görevleri listele",
    "trash_file": "Dosyayı çöpe at", "undo_last_action": "Son işlemi geri al", "web_search": "İnternette ara",
}


def first_sentence(text: str) -> str:
    """Model için yazılmış açıklamanın yalnızca ilk cümlesi ('... denince kullanılır' gibi model yönergeleri gösterilmez)."""
    t = " ".join((text or "").split())
    m = re.match(r"(.+?[.!?])(?:\s|$)", t)
    return (m.group(1) if m else t)[:160]


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
        out.append({"name": name, "label": TOOL_LABELS.get(name) or name.replace("_", " ").capitalize(), "category": cats.get(name, "Diğer"),
                    "desc": first_sentence(desc), "uses": stats.get(name, 0)})
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
