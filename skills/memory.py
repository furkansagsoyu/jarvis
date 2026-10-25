"""Kalıcı hafıza: kullanıcının söylediği bilgileri saklar ve gerektiğinde hatırlar.

Depo: data/memory.db (SQLite, 0600). Arama SQLite FTS5 ile yapılır (bm25 sıralaması); Türkçe harfler katlanır (ç->c, ı->i...)
ve kelimeler kabaca köklenir (önek araması: "kedimin" ~ "kedi*"). FTS5 yoksa düz LIKE aramasına düşülür.
Geri uyumlu göç: eski data/memory.json ilk açılışta içeri alınır ve memory.json.bak adıyla yedek olarak kalır (silinmez).
Hafıza kişisel veridir: yalnızca yerelde kalır (buluta, Telegram'a gitmez; recall uzaktan kapalı).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import os
import re
import sqlite3
import threading

from . import _store

FILE = "memory.json"      # eski biçim (göç kaynağı)
DB = "memory.db"
MAX_FACTS = 5000
MAX_RECALL = 5
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")
_lock = threading.Lock()
_fts: bool | None = None  # bu sqlite FTS5 destekliyor mu (ilk açılışta belirlenir)


def _norm(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _fold(s: str) -> str:
    """Arama biçimi: küçük harf + Türkçe harfler katlanmış + yalnızca harf/rakam."""
    return " ".join(re.findall(r"\w+", _norm(s).translate(_FOLD)))


def _stem(w: str) -> str:
    return w[:max(3, min(5, len(w) - 1))]  # Türkçe ekleri kabaca yok say: "adım" ~ "adı"


def _terms(query: str) -> list[str]:
    return list(dict.fromkeys(_stem(w) for w in _fold(query or "").split() if len(w) > 2))


def _connect() -> sqlite3.Connection:
    global _fts
    p = _store.path(DB)
    fresh = not p.exists()
    if fresh:
        os.close(os.open(p, os.O_WRONLY | os.O_CREAT, 0o600))   # kişisel veri: yalnızca sahibi okur
    con = sqlite3.connect(p, timeout=5)
    con.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT NOT NULL, norm TEXT NOT NULL UNIQUE, "
                "fold TEXT NOT NULL, date TEXT NOT NULL)")
    if _fts is not False:   # destek bir kez belirlenir; tablo her veritabanında (yoksa) kurulur
        try:
            con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(fold, content='facts', content_rowid='id')")
            _fts = True
        except sqlite3.OperationalError:
            _fts = False
    if _fts:
        con.executescript(
            "CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN "
            "INSERT INTO facts_fts(rowid, fold) VALUES (new.id, new.fold); END;"
            "CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN "
            "INSERT INTO facts_fts(facts_fts, rowid, fold) VALUES ('delete', old.id, old.fold); END;")
    _migrate(con)
    return con


@contextlib.contextmanager
def _db():
    """Kilitli, işlem sonunda commit edilip KAPATILAN bağlantı (sqlite3'ün 'with con' kullanımı bağlantıyı kapatmaz)."""
    with _lock:
        con = _connect()
        try:
            with con:
                yield con
        finally:
            con.close()


def _migrate(con: sqlite3.Connection) -> None:
    """Eski memory.json -> memory.db (bir kez). Kaynak silinmez, memory.json.bak olarak kalır."""
    src = _store.path(FILE)
    if not src.exists():
        return
    facts = _store.load(FILE, [])
    with con:
        for f in facts if isinstance(facts, list) else []:
            text = str(f.get("text", "")).strip() if isinstance(f, dict) else ""
            if text:
                con.execute("INSERT OR IGNORE INTO facts(text, norm, fold, date) VALUES (?,?,?,?)",
                            (text, _norm(text), _fold(text), str(f.get("date") or dt.date.today().isoformat())))
    os.replace(src, src.with_name(FILE + ".bak"))


def _match(con: sqlite3.Connection, terms: list[str], limit: int | None) -> list[tuple[int, str]]:
    """Terimlerden HERHANGİ biriyle eşleşen kayıtlar, en alakalı önce: [(id, text)]."""
    lim = f" LIMIT {int(limit)}" if limit else ""
    if _fts:
        q = " OR ".join(f'"{t}"*' for t in terms)
        return con.execute("SELECT f.id, f.text FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                           f"WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts), f.id DESC{lim}", (q,)).fetchall()
    where = " OR ".join("(' ' || fold) LIKE ?" for _ in terms)   # FTS5 yok: kelime başında önek
    return con.execute(f"SELECT id, text FROM facts WHERE {where} ORDER BY id DESC{lim}", [f"% {t}%" for t in terms]).fetchall()


def remember(fact: str) -> str:
    fact = " ".join((fact or "").split())
    if not fact:
        return "Hata: kaydedilecek bilgi boş."
    with _db() as con:
        if con.execute("SELECT 1 FROM facts WHERE norm = ?", (_norm(fact),)).fetchone():   # (rowcount tetikleyicide -1 döner)
            return "Bunu zaten biliyorum."
        con.execute("INSERT INTO facts(text, norm, fold, date) VALUES (?,?,?,?)", (fact, _norm(fact), _fold(fact), dt.date.today().isoformat()))
        n = con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        if n > MAX_FACTS:  # en eskiler düşer
            for (fid,) in con.execute("SELECT id FROM facts ORDER BY id LIMIT ?", (n - MAX_FACTS,)).fetchall():
                con.execute("DELETE FROM facts WHERE id = ?", (fid,))
    return "Tamam, not aldım."


def recall(query: str = "") -> str:
    terms = _terms(query)
    with _db() as con:
        if not con.execute("SELECT 1 FROM facts LIMIT 1").fetchone():
            return "Henüz kayıtlı bir bilgi yok."
        if terms:
            hits = [t for _, t in _match(con, terms, MAX_RECALL)]
        else:
            hits = [t for (t,) in con.execute("SELECT text FROM facts ORDER BY id DESC LIMIT ?", (MAX_RECALL,)).fetchall()][::-1]
    if not hits:
        return "Bununla ilgili kayıtlı bir bilgi bulamadım."
    return " ".join(h.rstrip(".") + "." for h in hits)


def forget(query: str) -> str:
    terms = _terms(query)
    if not terms:
        return "Hata: neyin unutulacağı belli değil."
    with _db() as con:
        ids = [i for i, _ in _match(con, terms, None)]
        for i in ids:
            con.execute("DELETE FROM facts WHERE id = ?", (i,))
    return f"{len(ids)} kaydı sildim." if ids else "Eşleşen bir kayıt bulamadım."


def stats(last: int = 3) -> dict:
    """Pano için: {"count", "last": [en yeni metinler]}."""
    try:
        with _db() as con:
            n = con.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            rows = con.execute("SELECT text FROM facts ORDER BY id DESC LIMIT ?", (last,)).fetchall()
    except sqlite3.Error:
        return {"count": 0, "last": []}
    return {"count": n, "last": [r[0] for r in rows]}


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
