"""Kalıcı hafıza: kullanıcının söylediği bilgileri saklar ve gerektiğinde hatırlar."""
import datetime as dt

from . import _store

FILE = "memory.json"
MAX_FACTS = 500


def _norm(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _stem(w: str) -> str:
    return w[:max(3, min(5, len(w) - 1))]  # Türkçe ekleri kabaca yok say: "adım" ~ "adı"


def remember(fact: str) -> str:
    fact = (fact or "").strip()
    if not fact:
        return "Hata: kaydedilecek bilgi boş."
    facts = _store.load(FILE, [])
    if any(_norm(f["text"]) == _norm(fact) for f in facts):
        return "Bunu zaten biliyorum."
    facts.append({"text": fact, "date": dt.date.today().isoformat()})
    _store.save(FILE, facts[-MAX_FACTS:])
    return "Tamam, not aldım."


def recall(query: str = "") -> str:
    facts = _store.load(FILE, [])
    if not facts:
        return "Henüz kayıtlı bir bilgi yok."
    words = [_stem(w) for w in _norm(query or "").split() if len(w) > 2]
    hits = [f for f in facts if not words or any(w in _norm(f["text"]) for w in words)]
    if not hits:
        return "Bununla ilgili kayıtlı bir bilgi bulamadım."
    return " ".join(f["text"].rstrip(".") + "." for f in hits[-5:])


def forget(query: str) -> str:
    words = [_stem(w) for w in _norm(query or "").split() if len(w) > 2]
    if not words:
        return "Hata: neyin unutulacağı belli değil."
    facts = _store.load(FILE, [])
    keep = [f for f in facts if not any(w in _norm(f["text"]) for w in words)]
    n = len(facts) - len(keep)
    if n == 0:
        return "Eşleşen bir kayıt bulamadım."
    _store.save(FILE, keep)
    return f"{n} kaydı sildim."


SKILLS = [
    {
        "name": "remember",
        "description": "Kullanıcının hatırlamamı istediği bir bilgiyi kalıcı olarak kaydeder. 'Şunu hatırla', 'not al' denince kullanılır.",
        "parameters": {"type": "object", "properties": {
            "fact": {"type": "string", "description": "Kaydedilecek bilgi, tam cümle (ör. 'Kullanıcının adı Furkan')"}},
            "required": ["fact"]},
        "run": remember,
    },
    {
        "name": "recall",
        "description": "Daha önce kaydedilen bilgileri getirir. Kullanıcı kendisiyle ilgili bir şey sorarsa kullanılır: 'adım ne', 'adımı hatırlıyor musun', 'kedimin adı neydi', 'ne hatırlıyorsun'.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Aranan konu, anahtar kelimeler (boşsa son kayıtlar)"}}},
        "run": recall,
    },
    {
        "name": "forget",
        "description": "Kaydedilmiş bir bilgiyi siler. 'Şunu unut' denince kullanılır.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Silinecek kaydı bulduran anahtar kelimeler"}},
            "required": ["query"]},
        "run": forget,
    },
]
