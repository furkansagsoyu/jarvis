"""Buluta giden metin için gizlilik kapısı.

Kural: kişisel veri (parola, anahtar, adres, telefon, e-posta, kimlik/kart/IBAN numarası), hafıza, konuşma kaydı, ekran/kamera
görüntüsü ve "private" işaretli içerik ASLA ücretsiz bulut modellerine gitmez (ücretsiz katmanlar veriyi eğitimde kullanabilir /
insan gözüyle inceleyebilir). Şüpheli bir şey bulunursa mesaj buluta HİÇ gönderilmez; çağıran yerel modele döner.
Yalnızca ev dizini yolları (/home/kullanıcı) sessizce maskelenir.
"""
from __future__ import annotations

import re


class Blocked(Exception):
    """Bulut çağrısı gizlilik nedeniyle (ya da ayardan kapalı olduğu için) yapılmadı."""

    def __init__(self, reasons):
        self.reasons = [reasons] if isinstance(reasons, str) else list(reasons)
        super().__init__("; ".join(self.reasons))

    @property
    def text(self) -> str:
        return ", ".join(self.reasons)


_KEYS = re.compile(r"(?:\bsk-[A-Za-z0-9_\-]{16,}|\bgsk_[A-Za-z0-9]{16,}|\bghp_[A-Za-z0-9]{20,}|\bgithub_pat_\w{20,}|\bAKIA[0-9A-Z]{16}\b|"
                   r"\bAIza[0-9A-Za-z_\-]{30,}|\bxox[baprs]-[\w-]{10,}|\bhf_[A-Za-z0-9]{20,}|\bcsk-[A-Za-z0-9]{16,}|\bBearer\s+[A-Za-z0-9._\-]{20,})")
_PRIVKEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_SECRET_ASSIGN = re.compile(r"(?i)\b(?:password|passwd|pwd|parola\w*|şifre\w*|token|secret|api[_ -]?key|anahtar\w*)\b\s*[:=]\s*[\"']?[^\s\"',;]{4,}")
_SECRET_SPOKEN = re.compile(r"(?i)\b(?:şifre\w*|parola\w*|password)\s+\S*\d\S*")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
_PHONE = re.compile(r"(?<![\d.])(?:\+?90[\s-]?)?0?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")
_IBAN = re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.I)
_DIGITS = re.compile(r"(?<![\d.])(?:\d[ -]?){12,18}\d(?!\d)")
_TC = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
_ADDRESS = re.compile(r"(?i)\b\w+\s+(?:mahallesi|mah\.|sokak|sokağı|caddesi|bulvarı)\b")
_HOME = re.compile(r"(/home/|/Users/)[^/\s\"']+|(?i:[A-Z]:\\Users\\)[^\\\s\"']+")


def _luhn(num: str) -> bool:
    d = [int(c) for c in num][::-1]
    return len(d) >= 13 and (sum(d[0::2]) + sum(sum(divmod(x * 2, 10)) for x in d[1::2])) % 10 == 0


def _tc_ok(s: str) -> bool:
    d = [int(c) for c in s]
    if len(d) != 11 or d[0] == 0:
        return False
    return (sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10 == d[9] and sum(d[:10]) % 10 == d[10]


def inspect(text: str) -> list[str]:
    """Metinde buluta gitmemesi gereken şeyleri bulur; her biri için kısa Türkçe neden döner (içeriği göstermez)."""
    found: list[str] = []
    if _KEYS.search(text) or _PRIVKEY.search(text):
        found.append("API anahtarı/özel anahtar")
    if _SECRET_ASSIGN.search(text) or _SECRET_SPOKEN.search(text):
        found.append("parola benzeri bir değer")
    if _EMAIL.search(text):
        found.append("e-posta adresi")
    if _PHONE.search(text):
        found.append("telefon numarası")
    if _IBAN.search(text):
        found.append("IBAN")
    if any(_luhn(re.sub(r"\D", "", m.group())) for m in _DIGITS.finditer(text)):
        found.append("kart numarası")
    if any(_tc_ok(m.group()) for m in _TC.finditer(text)):
        found.append("T.C. kimlik numarası")
    if _ADDRESS.search(text):
        found.append("adres")
    return found


def redact(text: str) -> str:
    """Ev dizini yollarındaki kullanıcı adını maskeler (kod/hata iletilerinde sık geçer)."""
    return _HOME.sub(lambda m: (m.group(1) if m.group(1) else "C:\\Users\\") + "kullanici", text)


def gate(messages: list[dict]) -> list[dict]:
    """Bulut için hazırlanan mesajları denetler. Temizse (ev yolları maskelenmiş) kopyasını döndürür; değilse Blocked fırlatır."""
    reasons: list[str] = []
    out = []
    for m in messages:
        if m.get("private"):
            reasons.append("özel (hafıza/kayıt/ekran) içerik işaretli")
            continue
        content = m.get("content")
        if not isinstance(content, str):
            reasons.append("metin olmayan içerik")
            continue
        for r in inspect(content):
            if r not in reasons:
                reasons.append(r)
        out.append({"role": m.get("role", "user"), "content": redact(content)})
    if reasons:
        raise Blocked(reasons)
    return out
