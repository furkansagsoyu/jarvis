"""Hatırlatıcı ve takvim etkinliklerini telefon uygulamasına da gönderir (telefon kendi alarmını kurar; bilgisayar kapansa da çalar).

Yalnızca uygulama eşleşmişse ve ayar açıksa çalışır; aksi hâlde hiçbir şey yapmaz (eski davranış aynen kalır).
Gizlilik: ayar "detail" = "generic" (varsayılan) iken Firebase'e metin GİTMEZ; telefonda yalnızca "Hatırlatıcı zamanı" yazar.
"full" yapılırsa başlık da gider (Google sunucularından geçer).
"""
from __future__ import annotations

import datetime as dt


def _link():
    from connect import phonelink  # noqa: PLC0415
    return phonelink


def enabled() -> bool:
    try:
        L = _link()
        return L.configured() and bool(L.setting("alerts", True))
    except Exception:  # noqa: BLE001
        return False


def schedule(key: str, at: dt.datetime, title: str, body: str = "") -> tuple[bool | None, str]:
    """(None, '') = kapalı/uygun değil; (True, '') = telefona gitti; (False, neden) = gidemedi."""
    if not enabled():
        return None, ""
    if at <= dt.datetime.now() + dt.timedelta(seconds=3):
        return None, ""
    L = _link()
    if L.setting("detail", "generic") != "full":
        title, body = "Jarvis hatırlatıcı", f"Zamanı geldi ({at.strftime('%H:%M')})"
    ok, msg = L.send("ring", ttl=300, id=key, title=title or "Jarvis", body=body or title or "Hatırlatıcı", at=int(at.timestamp() * 1000))
    return (True, "") if ok else (False, msg)


def cancel(key: str) -> None:
    if not enabled():
        return
    try:
        _link().send("cancel", ttl=300, id=key)
    except Exception:  # noqa: BLE001
        pass
