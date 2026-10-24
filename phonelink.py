"""Telefon uygulamasına (Jarvis Telefon, Firebase Cloud Messaging) imzalı komut gönderir: ara, kapat, alarm çaldır.

Akış: bilgisayar -> FCM (Google) -> telefondaki uygulama. Uygulama komutu HMAC imzası ve zaman damgasıyla doğrular.
Gizlilik: mesajda NUMARA YOKTUR; yalnızca kişi adı gider, numarayı telefon kendi rehberinden bulur.

Dosyalar (data/ içinde, git dışı):
    fcm_service_account.json   Firebase "özel anahtar" (SENİN indirdiğin; sohbete yapıştırma)
    phone_push.json            {"project_id", "token", "secret"}  (python phone_check.py --app-pair üretir)
Gereken paket: pip install google-auth requests
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.error
import urllib.request

from skills import _store

SA_FILE = "fcm_service_account.json"
CFG_FILE = "phone_push.json"
PACKAGE = "com.furkan.jarvisphone"
FIELDS = ("cmd", "name", "title", "body", "at", "id", "ts", "nonce")   # uygulamadaki Verifier.FIELDS ile AYNI sıra
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_token_cache: dict = {"value": "", "exp": 0.0}


def config() -> dict:
    cfg = _store.load(CFG_FILE, {})
    return cfg if isinstance(cfg, dict) else {}


def configured() -> bool:
    c = config()
    return bool(c.get("token") and c.get("secret") and c.get("project_id") and _store.path(SA_FILE).exists())


def sign(secret: str, data: dict) -> str:
    text = "|".join(str(data.get(k, "")) for k in FIELDS)
    return hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def build_data(cmd: str, secret: str, **fields) -> dict:
    """FCM 'data' alanı: yalnızca string değerler. İmza tüm alanları kapsar."""
    data = {"cmd": cmd, "ts": str(int(time.time())), "nonce": secrets.token_hex(8)}
    for k, v in fields.items():
        if k in FIELDS and v not in (None, ""):
            data[k] = str(v)
    data["sig"] = sign(secret, data)
    return data


def _access_token() -> str:
    """Servis hesabı ile kısa ömürlü OAuth belirteci (google-auth gerekir). Testlerde değiştirilir."""
    if _token_cache["value"] and time.time() < _token_cache["exp"]:
        return _token_cache["value"]
    from google.auth.transport.requests import Request  # noqa: PLC0415
    from google.oauth2 import service_account  # noqa: PLC0415
    creds = service_account.Credentials.from_service_account_file(str(_store.path(SA_FILE)), scopes=[SCOPE])
    creds.refresh(Request())
    _token_cache.update(value=creds.token, exp=time.time() + 50 * 60)
    return creds.token


def _post(url: str, headers: dict, body: dict, timeout: int = 10) -> tuple[int, str]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, str(exc)


def send(cmd: str, ttl: int = 60, **fields) -> tuple[bool, str]:
    """(başarılı mı, Türkçe açıklama). Başarı = Google mesajı kabul etti; telefonun yürüttüğünü GARANTİ ETMEZ."""
    if not configured():
        return False, "Telefon uygulaması kurulu değil (python phone_check.py --app-pair)."
    cfg = config()
    try:
        access = _access_token()
    except ImportError:
        return False, "google-auth kurulu değil: pip install google-auth requests"
    except Exception as exc:  # noqa: BLE001
        return False, f"Firebase anahtarı kullanılamadı ({type(exc).__name__}). Servis hesabı dosyasını kontrol et."
    body = {"message": {"token": cfg["token"], "data": build_data(cmd, cfg["secret"], **fields),
                        "android": {"priority": "HIGH", "ttl": f"{int(ttl)}s"}}}
    status, text = _post(f"https://fcm.googleapis.com/v1/projects/{cfg['project_id']}/messages:send",
                         {"Authorization": f"Bearer {access}", "Content-Type": "application/json; charset=utf-8"}, body)
    if status == 200:
        return True, "gönderildi"
    if status == 0:
        return False, "Firebase'e ulaşılamadı (internet?)."
    if status == 404 or "UNREGISTERED" in text:
        return False, "Telefon kaydı geçersiz. Uygulamayı yeniden kurduysan python phone_check.py --app-pair çalıştır."
    if status in (401, 403):
        _token_cache.update(value="", exp=0.0)
        return False, "Firebase izin vermedi (servis hesabı anahtarı ya da proje yanlış)."
    if status == 429:
        return False, "Firebase istek sınırı doldu, biraz sonra dene."
    return False, f"Firebase hata verdi ({status})."


# ------------------------------------------------------------------ eşleştirme (ADB üzerinden, bir kez)
def parse_token(logcat: str) -> str | None:
    found = re.findall(r"JarvisPhone[^\n]*?TOKEN=([\w\-:]+)", logcat)
    return found[-1] if found else None


def pair(adb: str, serial: str, run) -> str:
    """Telefondaki uygulamadan belirteci okur, rastgele gizli anahtarı telefona ADB ile yazar, ikisini kaydeder.
    run(args, timeout) -> (kod, çıktı). Gizli anahtar ağdan geçmez."""
    sa = _store.path(SA_FILE)
    if not sa.exists():
        return f"Servis hesabı anahtarı yok: indirdiğin Firebase .json dosyasını {sa} olarak kaydet."
    try:
        project_id = json.loads(sa.read_text(encoding="utf-8"))["project_id"]
    except Exception:  # noqa: BLE001
        return "fcm_service_account.json geçerli bir Firebase servis hesabı dosyası değil."
    sh = [adb, "-s", serial]
    run(sh + ["logcat", "-c"], 10)
    run(sh + ["shell", "am", "broadcast", "-n", f"{PACKAGE}/.PairReceiver", "-a", f"{PACKAGE}.TOKEN"], 10)
    token = None
    for _ in range(6):
        time.sleep(1.5)
        token = parse_token(run(sh + ["logcat", "-d", "-s", "JarvisPhone:I"], 10)[1])
        if token:
            break
    if not token:
        return "Telefondan belirteç alınamadı. Jarvis Telefon uygulaması yüklü ve en az bir kez açılmış mı? İnternet var mı?"
    key = secrets.token_hex(32)
    run(sh + ["logcat", "-c"], 10)
    run(sh + ["shell", "am", "broadcast", "-n", f"{PACKAGE}/.PairReceiver", "-a", f"{PACKAGE}.PAIR", "--es", "secret", key], 10)
    time.sleep(1.5)
    if "PAIRED_OK" not in run(sh + ["logcat", "-d", "-s", "JarvisPhone:I"], 10)[1]:
        return "Telefon gizli anahtarı kabul etmedi. Uygulama güncel mi?"
    _store.save(CFG_FILE, {"project_id": project_id, "token": token, "secret": key})
    _token_cache.update(value="", exp=0.0)
    return "Eşleşti. Dene: python phone_check.py --app-test"
