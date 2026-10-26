"""Mobil (uzaktan) erişim: telefondan Jarvis'e Tailscale üzerinden bağlanma ayarları.

Güvenlik modeli (kısaca):
  * Pano hâlâ yalnızca 127.0.0.1'de dinler. Telefon, `tailscale serve` ile açılan HTTPS adresinden gelir;
    Tailscale yalnızca senin cihazlarının olduğu özel ağda (tailnet) yayınlar. İnternete (Funnel) ASLA açılmaz.
  * Telefonun anahtarı, bilgisayardaki pano anahtarından AYRIDIR (kalıcı, data/remote.json) ve yalnızca
    /m sayfası ile /api/m/* uçlarında geçerlidir: yazışma, ses, görev/takvim, durum, kısıtlı hızlı komutlar.
    Kapatma, tema, bulut ayarı gibi pano uçları uzaktan hiç açılmaz.
  * Uzaktan yazışma Telegram ile aynı kısıtlı kiptedir (telefon aramaları, kod ajanı, dosya okuma kapalı).
  * Yanlış anahtar denemeleri geçici kilitler; istek sayısı sınırlıdır.
Ayar: python connect/remote_setup.py
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time

from skills import _store

FILE = "remote.json"
DEFAULT_PORT = 8765

# Telefondan çalıştırılabilen hızlı komutlar (pano COMMANDS tablosunun güvenli alt kümesi)
REMOTE_SAY = {
    "brief": "günün özeti",
    "tasks": "görevlerim neler",
    "today": "bugün ne yapıyorum",
    "system": "sistem durumu",
    "battery": "pil kaç",
    "weather": "hava nasıl",
    "yes": "evet",
    "no": "vazgeç",
}
REMOTE_ACT = ("stop", "mute", "focus")
REMOTE_AGENDA_OPS = ("add_task", "add_event", "done_task", "delete_task", "cancel_event")


def load() -> dict:
    d = _store.load(FILE, {})
    return d if isinstance(d, dict) else {}


def save(d: dict) -> None:
    _store.save(FILE, d)
    try:
        os.chmod(_store.path(FILE), 0o600)  # anahtar yalnızca bu kullanıcıya açık
    except OSError:
        pass


def enabled() -> bool:
    d = load()
    return bool(d.get("enabled") and d.get("token"))


def new_token() -> str:
    """Yeni telefon anahtarı üretir ve kaydeder (eskisi anında geçersiz olur)."""
    d = load()
    d["token"] = secrets.token_urlsafe(24)
    d["enabled"] = True
    save(d)
    return d["token"]


def revoke() -> None:
    d = load()
    d["enabled"] = False
    d.pop("token", None)
    save(d)


def token() -> str:
    return str(load().get("token", ""))


def check_token(given: str) -> bool:
    want = token()
    if not want or not given or not enabled():
        return False
    return hmac.compare_digest(given.encode("utf-8", "replace"), want.encode("utf-8"))


def hosts() -> set[str]:
    """Uzaktan kabul edilen Host başlıkları (tailnet adı; 443 için port yazılmaz)."""
    out = set()
    for h in load().get("hosts", []):
        h = str(h).strip().lower().rstrip(".")
        if h:
            out.update({h, f"{h}:443"})
    return out


def host_ok(host: str) -> bool:
    return enabled() and (host or "").strip().lower() in hosts()


def set_hosts(names: list[str]) -> None:
    d = load()
    d["hosts"] = sorted({n.strip().lower().rstrip(".") for n in names if n.strip()})
    save(d)


# ------------------------------------------------------------------ hız sınırı / kilitleme
class Limiter:
    """Yanlış anahtar denemesinde geçici kilit + dakikada en çok `per_min` istek."""

    def __init__(self, fails: int = 5, window: float = 60.0, lock: float = 60.0, per_min: int = 60, clock=time.monotonic):
        self.fails, self.window, self.lock_for, self.per_min, self.clock = fails, window, lock, per_min, clock
        self._bad: list[float] = []
        self._hits: list[float] = []
        self._until = 0.0
        self._lock = threading.Lock()

    def locked(self) -> bool:
        with self._lock:
            return self.clock() < self._until

    def fail(self) -> None:
        with self._lock:
            now = self.clock()
            self._bad = [t for t in self._bad if now - t < self.window] + [now]
            if len(self._bad) >= self.fails:
                self._until = now + self.lock_for
                self._bad = []

    def good(self) -> None:
        with self._lock:
            self._bad = []

    def hit(self) -> bool:
        """True: istek kabul. False: dakikalık sınır aşıldı."""
        with self._lock:
            now = self.clock()
            self._hits = [t for t in self._hits if now - t < 60.0]
            if len(self._hits) >= self.per_min:
                return False
            self._hits.append(now)
            return True


# ------------------------------------------------------------------ Tailscale
def tailscale_bin() -> str | None:
    return shutil.which("tailscale")


def _ts(*args: str, timeout: int = 15) -> tuple[int, str]:
    exe = tailscale_bin()
    if not exe:
        return 127, "tailscale kurulu değil"
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def tailnet_name() -> tuple[str | None, str]:
    """(tam alan adı, açıklama). Örn. ('msi.tail1234.ts.net', 'ok')."""
    code, out = _ts("status", "--json")
    if code != 0:
        return None, out[:300] or "tailscale status çalışmadı"
    try:
        data = json.loads(out)
    except ValueError:
        return None, "tailscale çıktısı okunamadı"
    if data.get("BackendState") not in (None, "Running"):
        return None, f"Tailscale çalışmıyor ({data.get('BackendState')}). `sudo tailscale up` ile giriş yap."
    dns = str((data.get("Self") or {}).get("DNSName", "")).rstrip(".").lower()
    if not dns:
        return None, "Tailscale'de MagicDNS/HTTPS kapalı görünüyor (yönetim panelinde DNS → MagicDNS ve HTTPS Certificates aç)."
    return dns, "ok"


def funnel_on() -> bool:
    """Herhangi bir yayın İnternete (Funnel) açık mı? Açıksa uzaktan erişimi kabul etmeyiz."""
    code, out = _ts("serve", "status")
    return code == 0 and bool(re.search(r"funnel\s+on", out, re.I))


def apply_serve(port: int) -> tuple[bool, str]:
    """tailnet'e HTTPS yayını: https://<ad>/ -> http://127.0.0.1:<port> (yalnızca tailnet, Funnel değil)."""
    if funnel_on():
        return False, "Funnel (İnternete açık yayın) açık görünüyor; güvenlik için kapat: tailscale funnel reset"
    code, out = _ts("serve", "--bg", "--https=443", f"http://127.0.0.1:{port}", timeout=30)
    return code == 0, out[:300]


def public_url(host: str) -> str:
    return f"https://{host}/m"


def pair_url(host: str, tok: str) -> str:
    """Anahtar # parçasında: sunucuya, günlüklere ve Referer'e gitmez; sayfa onu telefonda saklar."""
    return f"{public_url(host)}#t={tok}"


def sync(port: int) -> str:
    """Açılışta: erişim açıksa adresi bildirir; pano portu değiştiyse yayını yeni porta çevirir."""
    if not enabled():
        return ""
    d = load()
    host = (d.get("hosts") or [""])[0]
    msg = f"Telefon erişimi açık: {public_url(host)}" if host else "Telefon erişimi açık ama adres ayarlı değil (python connect/remote_setup.py)"
    if host and int(d.get("port", DEFAULT_PORT)) != port:
        ok, out = apply_serve(port)
        if ok:
            d["port"] = port
            save(d)
        else:
            msg += f" — UYARI: pano {port} portunda, yayın {d.get('port')} portuna bakıyor ({out})"
    return msg
