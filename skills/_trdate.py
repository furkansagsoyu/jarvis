"""Türkçe tarih/saat ayrıştırıcı (kural tabanlı, çevrimdışı). Takvim ve görevler kullanır.

parse_when("yarın saat 14'te toplantı") -> When(date=2026-10-21, time=14:00, duration=None, rest="toplantı")
Anlaşılanlar: bugün, yarın, öbür gün, haftaya, gün adları (cuma, haftaya salı), "15 Kasım", "15.11", "15/11/2026",
"saat 14", "14:30", "saat 3 buçuk", "sabah/öğleden sonra/akşam/gece 8", "öğlen", "2 saat sonra", "yarım saat sonra",
süre: "2 saatlik", "30 dakika sürecek".
"""
import datetime as dt
import re
from dataclasses import dataclass

AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
         "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
GUNLER = {"pazartesi": 0, "salı": 1, "çarşamba": 2, "perşembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}
SAYILAR = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
           "onbir": 11, "oniki": 12, "yarım": 0.5}
_NUM = r"(\d+|yarım|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on)"
_SUFFIX = r"(?:['’]?\w*)"
FILLERS = re.compile(r"\b(takvim\w*|ekle\w*|koy\w*|kaydet\w*|yaz|planla\w*|oluştur\w*|lütfen|bana|şunu|için|etkinliği|olarak)\b", re.I)


def lower(s: str) -> str:
    """Türkçe küçük harf (İ→i, I→ı); uzunluk korunur, böylece indeksler özgün metinle aynı kalır."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def capitalize(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    first = {"i": "İ", "ı": "I"}.get(s[0], s[0].upper())
    return first + s[1:]


@dataclass
class When:
    date: dt.date | None = None
    time: dt.time | None = None
    duration: int | None = None   # dakika
    rest: str = ""                # tarih/saat sözcükleri çıkarılmış metin


def _num(tok: str) -> float:
    return float(tok) if tok.isdigit() else SAYILAR[tok]


def _hour(h: int, part: str | None, explicit_24: bool = False) -> int:
    if part in ("öğleden sonra", "akşam", "gece"):
        if h < 12:
            return h + 12 if not (part == "gece" and h in (12,)) else 0
        return h
    if part == "sabah":
        return 0 if h == 12 else h
    if explicit_24 or h >= 12 or h == 0:
        return h % 24
    return h + 12 if h <= 6 else h  # "saat 3" -> 15:00, "saat 9" -> 09:00


def parse_when(text: str, now: dt.datetime | None = None) -> When:
    now = now or dt.datetime.now()
    today = now.date()
    t = lower(text)
    spans: list[tuple[int, int]] = []
    out = When()

    def take(rx: str, flags=0):
        m = re.search(rx, t, flags)
        if m:
            spans.append(m.span())
        return m

    # ---- göreli: "2 saat sonra", "yarım saat sonra", "3 gün sonra"
    m = take(rf"{_NUM}\s*(dakika|dk|saat|gün|hafta)\s+sonra")
    if m:
        n, unit = _num(m.group(1)), m.group(2)
        if unit in ("dakika", "dk", "saat"):
            target = now + dt.timedelta(minutes=n if unit != "saat" else n * 60)
            out.date, out.time = target.date(), target.time().replace(second=0, microsecond=0)
        else:
            out.date = today + dt.timedelta(days=int(n) * (7 if unit == "hafta" else 1))

    # ---- süre: "2 saatlik", "30 dakika sürecek"
    m = take(rf"{_NUM}\s*(saat|dakika|dk)\s*(?:lik|lık|luk|lük|sürecek|sürer|boyunca)")
    if m:
        n = _num(m.group(1))
        out.duration = int(n * 60) if m.group(2) == "saat" else int(n)

    # ---- gün
    if out.date is None:
        if take(r"yarından sonra|öbür gün|ertesi gün"):
            out.date = today + dt.timedelta(days=2)
        elif take(r"\byarın\w*"):
            out.date = today + dt.timedelta(days=1)
        elif take(r"\bbugün\w*"):
            out.date = today
        else:
            m = take(r"(haftaya\s+)?\b(pazartesi|salı|çarşamba|perşembe|cumartesi|cuma|pazar)\w*(?:\s+günü)?")
            if m:
                idx = GUNLER[m.group(2)]
                if m.group(1):
                    out.date = today - dt.timedelta(days=today.weekday()) + dt.timedelta(days=7 + idx)
                else:
                    delta = (idx - today.weekday()) % 7 or 7
                    out.date = today + dt.timedelta(days=delta)
            elif take(r"\bhaftaya\b"):
                out.date = today + dt.timedelta(days=7)

    # ---- saat (açık "saat X" kalıbı önce: "saat 10.11" tarih sanılmasın)
    def set_time(h: int, mi: int = 0, part: str | None = None, explicit_24: bool = False):
        h2 = _hour(h, part, explicit_24)
        if 0 <= h2 <= 23 and 0 <= mi <= 59:
            out.time = dt.time(h2, mi)

    m = take(rf"(sabah|öğleden sonra|akşam|gece)\s*(?:saat\s*)?(\d{{1,2}})(?:[:.](\d{{2}}))?{_SUFFIX}")
    if m:
        set_time(int(m.group(2)), int(m.group(3) or 0), m.group(1))
    if out.time is None:
        m = take(rf"saat\s*(\d{{1,2}})(?:[:.](\d{{2}}))?(\s*buçuk)?{_SUFFIX}")
        if m:
            set_time(int(m.group(1)), 30 if m.group(3) else int(m.group(2) or 0), None, bool(m.group(2)) and int(m.group(1)) >= 13)
    if out.time is None:
        m = take(rf"saat\s+(onbir|oniki|on iki|on bir|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on){_SUFFIX}")
        if m:
            set_time(int(SAYILAR[m.group(1).replace(" ", "")]))
    if out.time is None and take(r"\böğlen\w*"):
        out.time = dt.time(12, 0)

    # ---- tarih: "15 kasım", "15.11", "15/11/2026"
    m = take(rf"\b(\d{{1,2}})\s*({'|'.join(AYLAR)}){_SUFFIX}(?:\s+(\d{{4}}))?")
    if m:
        day, month = int(m.group(1)), AYLAR[m.group(2)]
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            d = dt.date(year, month, day)
            if not m.group(3) and d < today:
                d = dt.date(year + 1, month, day)
            out.date = d
        except ValueError:
            spans.pop()
    else:
        for mm in re.finditer(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", t):
            day, month = int(mm.group(1)), int(mm.group(2))
            if mm.group(3) is None and out.time is None and month > 12 and day <= 23 and month <= 59:
                out.time = dt.time(day, month)  # "14.30" -> saat
                spans.append(mm.span())
                break
            if 1 <= month <= 12 and 1 <= day <= 31:
                year = int(mm.group(3)) if mm.group(3) else today.year
                year += 2000 if year < 100 else 0
                try:
                    d = dt.date(year, month, day)
                except ValueError:
                    continue
                if not mm.group(3) and d < today:
                    d = dt.date(year + 1, month, day)
                out.date = d
                spans.append(mm.span())
                break
        if out.time is None:
            mm = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
            if mm:
                out.time = dt.time(int(mm.group(1)), int(mm.group(2)))
                spans.append(mm.span())

    # ---- kalan metin
    keep, last = [], 0
    for a, b in sorted(spans):
        if a >= last:
            keep.append(text[last:a])
            last = max(last, b)
    keep.append(text[last:])
    rest = FILLERS.sub(" ", " ".join(keep))
    rest = re.sub(r"\s+", " ", rest).strip(" ,.:;-–'’\"")
    rest = re.sub(r"^(?:ve|de|da|bir)\s+|\s+(?:ve|de|da)$", "", rest).strip(" ,.:;-–'’\"")
    out.rest = rest
    return out
