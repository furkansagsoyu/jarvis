"""Fare ve klavye kontrolü (X11, xdotool). Hepsi "hidden": yalnızca kural tabanlı hızlı yoldan çağrılır.

Güvenlik:
- Fareyi hareket ettirmek ve kaydırmak serbest; TIKLAMA, YAZMA ve (gezinti dışı) TUŞ BASMA sesli onay ister.
  Onayı kod verir, model veremez (skills/_confirm).
- Etkin pencere terminal, parola yöneticisi, banka/ödeme/giriş ya da kimlik doğrulama (polkit/sudo) penceresiyse
  yazma, tıklama ve tuş basma REDDEDİLİR. Sesle terminale komut yazdırmak en tehlikeli yoldur; bu yüzden kapalı.
- Onay verildikten sonra (60 sn içinde) pencere değişmişse eylem yeniden denetlenir.
- Tehlikeli kısayollar (ctrl+alt+t, alt+f2, ctrl+alt+del, ctrl+alt+f1-f7 ...) kapalı. Telegram'dan tamamı kapalı.
Kurulum: sudo apt install xdotool
"""
import re
import shutil
import subprocess

from . import _confirm

TERMINAL_CLASSES = ("terminal", "xterm", "konsole", "tilix", "alacritty", "kitty", "terminator", "urxvt", "wezterm",
                    "guake", "tmux", "foot", "hyper", "tabby", "warp")
SECRET_CLASSES = ("keepass", "bitwarden", "1password", "enpass", "polkit", "pkexec", "seahorse", "gnome-keyring",
                  "kwalletmanager", "lastpass")
SECRET_TITLE = re.compile(r"password|parola|şifre|sifre|passphrase|sudo|authenticat|kimlik doğrula|oturum aç|giriş|login|sign.?in|"
                          r"banka|bank|paypal|ödeme|odeme|payment|checkout|keepass|bitwarden|cvv|iban", re.I)
BLOCKED_COMBOS = {"ctrl+alt+t", "alt+f2", "ctrl+alt+delete", "ctrl+alt+del", "ctrl+alt+backspace", "super+r", "super+t",
                  "ctrl+alt+l", "alt+sysrq"} | {f"ctrl+alt+f{i}" for i in range(1, 8)}
# Onaysız basılabilen gezinti tuşları (hiçbir şey çalıştırmaz, yalnızca imleci/sayfayı oynatır)
FREE_KEYS = {"up", "down", "left", "right", "page_up", "page_down", "home", "end", "alt+tab"}
MAX_TEXT = 300

KEYS = {  # sesle söylenen ad -> xdotool tuşu
    "enter": "Return", "entır": "Return", "escape": "Escape", "esc": "Escape", "tab": "Tab", "boşluk": "space",
    "silme": "BackSpace", "backspace": "BackSpace", "delete": "Delete", "yukarı ok": "Up", "aşağı ok": "Down",
    "sol ok": "Left", "sağ ok": "Right", "page up": "Prior", "page down": "Next", "home": "Home", "end": "End",
    "f5": "F5", "f11": "F11",
}
SHORTCUTS = {  # sesle söylenen ad -> kısayol
    "kopyala": "ctrl+c", "yapıştır": "ctrl+v", "kes": "ctrl+x", "tümünü seç": "ctrl+a", "kaydet": "ctrl+s",
    "yeni sekme": "ctrl+t", "sekmeyi kapat": "ctrl+w", "sayfayı yenile": "F5", "pencere değiştir": "alt+Tab",
    "tam ekran": "F11", "ara": "ctrl+f", "yazdır": "ctrl+p", "tekrarla": "ctrl+y",
}
DIRS = {"yukarı": (0, -1), "aşağı": (0, 1), "sağa": (1, 0), "sola": (-1, 0)}
AMOUNTS = {"biraz": 80, "az": 80, "çok": 500, "epey": 400}
STEP = 200
SPOTS = {"ortaya": (0.5, 0.5), "orta": (0.5, 0.5), "sol üst": (0.05, 0.08), "sağ üst": (0.95, 0.08),
         "sol alt": (0.05, 0.92), "sağ alt": (0.95, 0.92)}


class InputError(Exception):
    pass


def _xdo(*args: str) -> str:
    """xdotool çağrısı (testlerde değiştirilir)."""
    if not shutil.which("xdotool"):
        raise InputError("xdotool kurulu değil: sudo apt install xdotool")
    r = subprocess.run(["xdotool", *args], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise InputError((r.stderr or "xdotool hata verdi").strip()[:120])
    return r.stdout.strip()


def active_window() -> tuple[str, str]:
    """(sınıf adı, başlık) — küçük harfli sınıf, başlık olduğu gibi."""
    try:
        cls = _xdo("getactivewindow", "getwindowclassname").lower()
    except InputError:
        cls = ""
    try:
        title = _xdo("getactivewindow", "getwindowname")
    except InputError:
        title = ""
    return cls, title


def window_block_reason() -> str:
    """Etkin pencere güvenli değilse nedenini, değilse '' döndürür."""
    cls, title = active_window()
    if any(t in cls for t in TERMINAL_CLASSES):
        return "terminal penceresi"
    if any(t in cls for t in SECRET_CLASSES):
        return "parola ya da kimlik doğrulama penceresi"
    if SECRET_TITLE.search(title):
        return "parola, giriş ya da ödeme penceresi"
    return ""


def _window_name() -> str:
    cls, title = active_window()
    return (title or cls or "etkin pencere")[:40]


def _screen() -> tuple[int, int]:
    w, h = _xdo("getdisplaygeometry").split()
    return int(w), int(h)


def _mouse() -> tuple[int, int]:
    out = _xdo("getmouselocation", "--shell")
    vals = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return int(vals["X"]), int(vals["Y"])


def _safe(fn):
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except InputError as exc:
            return f"Yapamadım: {exc}"
    return wrapper


# ------------------------------------------------------------------ araçlar
@_safe
def mouse_move(where: str = "", amount: str = "") -> str:
    where = (where or "").strip().lower()
    if where in SPOTS:
        w, h = _screen()
        fx, fy = SPOTS[where]
        _xdo("mousemove", str(int(w * fx)), str(int(h * fy)))
        return "Fareyi oraya götürdüm."
    if where in DIRS:
        step = AMOUNTS.get((amount or "").strip().lower(), STEP)
        w, h = _screen()
        x, y = _mouse()
        dx, dy = DIRS[where]
        nx, ny = min(max(x + dx * step, 0), w - 1), min(max(y + dy * step, 0), h - 1)
        _xdo("mousemove", str(nx), str(ny))
        return "Fareyi kaydırdım."
    return "Fareyi nereye götüreceğimi anlamadım."


@_safe
def mouse_click(button: str = "sol", double: bool = False) -> str:
    why = window_block_reason()
    if why:
        return f"Güvenlik nedeniyle {why} üzerinde tıklamıyorum."
    b = {"sağ": "3", "orta": "2"}.get((button or "sol").lower(), "1")
    name = {"3": "sağ tuşla ", "2": "orta tuşla "}.get(b, "") + ("çift " if double else "")

    def run():
        why2 = window_block_reason()
        if why2:
            return f"Pencere değişmiş ({why2}), tıklamadım."
        _xdo("click", "--repeat", "2" if double else "1", "--delay", "80", b)
        return "Tıkladım."
    return _confirm.request(f"'{_window_name()}' penceresinde fare imlecinin olduğu yere {name}tıklayacağım.", run)


@_safe
def scroll(direction: str = "aşağı", amount: str = "") -> str:
    n = {"biraz": 3, "az": 3, "çok": 20}.get((amount or "").lower(), 8)
    _xdo("click", "--repeat", str(n), "--delay", "30", "5" if direction.startswith("aşağı") else "4")
    return "Kaydırdım."


@_safe
def keyboard_type(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "Ne yazacağımı anlamadım."
    text = text[:MAX_TEXT]
    why = window_block_reason()
    if why:
        return f"Güvenlik nedeniyle {why} içine yazmıyorum."

    def run():
        why2 = window_block_reason()
        if why2:
            return f"Pencere değişmiş ({why2}), yazmadım."
        _xdo("type", "--delay", "25", "--", text)
        return "Yazdım."
    return _confirm.request(f"'{_window_name()}' penceresine '{text}' yazacağım.", run)


def _norm_combo(name: str) -> str:
    return "+".join(p.strip().lower() for p in re.split(r"[+\s]+", name.strip()) if p.strip())


@_safe
def press_key(name: str) -> str:
    raw = (name or "").strip().lower()
    combo = SHORTCUTS.get(raw) or KEYS.get(raw) or raw
    canon = _norm_combo(combo)
    if canon in BLOCKED_COMBOS or canon.replace("return", "enter") in BLOCKED_COMBOS:
        return "Bu kısayolu güvenlik nedeniyle kullanmıyorum."
    why = window_block_reason()
    if why:
        return f"Güvenlik nedeniyle {why} üzerinde tuşa basmıyorum."
    free = canon in FREE_KEYS or combo.lower() in {k.lower() for k in ("Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End")}

    def send():
        _xdo("key", combo)
        return "Bastım."
    if free:
        return send()

    def run():
        why2 = window_block_reason()
        return f"Pencere değişmiş ({why2}), basmadım." if why2 else send()
    return _confirm.request(f"'{_window_name()}' penceresinde {raw or combo} tuşuna basacağım.", run)


SKILLS = [
    {"name": "mouse_move", "hidden": True, "run": mouse_move,
     "description": "Fare imlecini yönlendirir (sağa, sola, yukarı, aşağı, ortaya, köşelere).",
     "parameters": {"type": "object", "properties": {"where": {"type": "string"}, "amount": {"type": "string"}}, "required": ["where"]}},
    {"name": "mouse_click", "hidden": True, "run": mouse_click,
     "description": "Fare imlecinin olduğu yere tıklar (onay ister).",
     "parameters": {"type": "object", "properties": {"button": {"type": "string"}, "double": {"type": "boolean"}}}},
    {"name": "scroll", "hidden": True, "run": scroll,
     "description": "Etkin pencereyi yukarı veya aşağı kaydırır.",
     "parameters": {"type": "object", "properties": {"direction": {"type": "string"}, "amount": {"type": "string"}}, "required": ["direction"]}},
    {"name": "keyboard_type", "hidden": True, "run": keyboard_type,
     "description": "Etkin pencereye klavyeden metin yazar (onay ister).",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "press_key", "hidden": True, "run": press_key,
     "description": "Bir tuşa veya kısayola basar (onay ister).",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
]
