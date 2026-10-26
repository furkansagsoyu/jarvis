#!/usr/bin/env python3
"""Üst kenar "adası": ekranın üst ortasında küçük, her zaman üstte duran durum/onay çubuğu (Qt).

Jarvis tarafından başlatılır (main.py --island), pano sunucusunun yerel uçlarıyla konuşur:
  GET  /api/island          -> {state, label, kind, question, id, left}
  POST /api/island/answer   -> {"answer": "yes"|"no", "id"}

- Boştayken yalnızca durum (Dinliyor / Düşünüyor / Konuşuyor / Sessizde) gösteren küçük bir hap.
- Bekleyen bir onay ya da plan varsa genişler: soru + kalan süre + Evet / Hayır.
- Güvenlik: düğmeler sesli "evet/hayır" ile AYNI yoldan geçer (onay kapısı değişmez); sunucu yalnızca ekrandaki soru
  hâlâ bekliyorsa (aynı id) iletir. Pencere odak almaz (klavyeyle tetiklenemez) ve başlığı "JARVIS Ada"dır: fare/klavye
  aracı (skills/desktop_input.py) bu pencereye tıklamaz, yani model kendi onayını veremez.
- Fikir coucou'dan (MIT) alındı; kod ve görseller bu projeye özgüdür.
"""
from __future__ import annotations
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri


import argparse
import json
import math
import os
import sys
import time
import urllib.request
from urllib.parse import parse_qs, urlparse

TITLE = "JARVIS Ada"
POLL_MS = 300            # durum yoklaması (uyanınca adanın büyümesi gecikmesin)
COLORS = {"starting": "#9aa0a6", "listening": "#34a853", "recording": "#00c853", "thinking": "#f9ab00", "speaking": "#4285f4", "muted": "#ea4335",
          "stopped": "#5f6368", "confirm": "#ff6d00"}
MAX_Q = 160
WIDE, NARROW = 580, 210
MASCOT_PX = 34
ACTIVE_PX = 76           # etkin halde (uyandı / düşünüyor / konuşuyor) ortadaki büyük maskot
ACTIVE_W = 250
GROW_MS = 320
HIDE_AFTER = 6.0         # sn: cevap bittikten sonra bu kadar sessizlikte ada yukarı saklanır (autohide)
SLIDE_IN_MS, SLIDE_OUT_MS = 420, 360            # büyüme/küçülme süresi (yaylanan geçiş; coucou'nun "çentikten çıkma" fikri)
ACTIVE_MASCOTS = ("listening", "thinking", "speaking")
FRAME_MS = 66            # maskot kare süresi (~15 kare/sn; küçük çizim, CPU yükü düşük)
REDUCED = os.environ.get("JARVIS_REDUCED_MOTION") == "1"   # hareket azaltma: yalnızca durağan kare
# Çekirdek maskotunun renkleri (assets/cekirdek.svg ile aynı): (çizgi, göz/ağız, gövde)
MASCOT_COLORS = {"alert": ("#f59e0b", "#fcd34d", "#33240a"), "error": ("#f43f5e", "#fda4af", "#33111b")}
MASCOT_DEFAULT = ("#22d3ee", "#67e8f9", "#0e2a35")


# Ada temaları (pano temalarıyla aynı vurgu renkleri): vurgu, vurgu2, maskot gövdesi, hap arka planı, yazı, kenarlık
PALETTES = {
    "cyan": ("#22d3ee", "#67e8f9", "#0e2a35", "rgba(8,14,26,232)", "#e8eef6", "rgba(120,160,200,90)"),
    "amber": ("#ffb23f", "#ffd38a", "#33240a", "rgba(18,12,4,232)", "#f6efe2", "rgba(200,160,100,90)"),
    "green": ("#2ee89a", "#8af5c6", "#0a2a1e", "rgba(4,16,10,232)", "#e6f6ee", "rgba(110,190,150,90)"),
    "violet": ("#a779ff", "#cbb2ff", "#1e1236", "rgba(12,6,22,232)", "#efe9fb", "rgba(160,130,210,90)"),
    "light": ("#0b78b5", "#0a5f93", "#dcebf7", "rgba(244,248,252,242)", "#14283b", "rgba(11,120,181,110)"),
}
SCALES = {"small": .85, "normal": 1.0, "large": 1.25}
EDGE = 12   # sol/sağ konumda ekran kenarından boşluk


def should_show(v: dict, last_active: float, now: float) -> bool:
    """Otomatik gizlenmede ada görünmeli mi? Konuşma (dinliyor/düşünüyor/konuşuyor), onay sorusu, uyarı ya da hata varken
    her zaman; bunlar bittikten sonra HIDE_AFTER sn daha. Bekleme ("Hey Jarvis"i dinliyor) uzarsa saklanır.
    autohide kapalıysa her zaman görünür (Qt'siz test edilir)."""
    if (v.get("cfg") or {}).get("autohide", True) is False:
        return True
    if v.get("mode") in ("active", "confirm") or v.get("mascot") in ("alert", "error"):
        return True
    return now - last_active < HIDE_AFTER


def palette(name: str) -> tuple:
    return PALETTES.get(name, PALETTES["cyan"])


def geometry_for(cfg: dict, width: int, scr_x: int, scr_y: int, scr_w: int) -> tuple[int, int]:
    """Adanın sol üst köşesi: konum ayarı (üst orta/sol/sağ) ve ekran alanına göre (Qt'siz test edilir)."""
    pos = (cfg or {}).get("position", "center")
    x = scr_x + EDGE if pos == "left" else scr_x + scr_w - width - EDGE if pos == "right" else scr_x + (scr_w - width) // 2
    return x, scr_y + 6


def scaled(cfg: dict, px: int) -> int:
    return round(px * SCALES.get((cfg or {}).get("size", "normal"), 1.0))


def _wave(t: float, period: float) -> float:
    """0..1..0 arası yumuşak dalga (CSS ease-in-out 0%,100% -> 50% kare çiftine yakın)."""
    return (1 - math.cos(2 * math.pi * (t % period) / period)) / 2


def mascot_svg(state: str, t: float = 0.0, since: float = 0.0, theme: str = "cyan") -> bytes:
    """Adadaki maskotun t anındaki karesi: assets/cekirdek.svg'nin geometrisi ve @keyframes'i (süreler/değerler aynı).
    Qt'nin SVG çizicisi CSS animasyonu çalıştırmadığı için animasyon burada kare kare hesaplanır (run_qt ~15 kare/sn çizer).
    t: saniye (saat); since: bu duruma geçilen an (hata titremesi yalnızca girişte). t=0 -> durağan ilk kare.
    theme: ada teması; maskot rengi temayı izler (uyarı/hata kendi rengini korur)."""
    line, face, body = MASCOT_COLORS.get(state) or (palette(theme)[:3] if theme in PALETTES else MASCOT_DEFAULT)
    # hale: nefes (4 sn; konuşurken 1,2 sn) ölçek .92-1.05, saydamlık .7-1; uyarıda yanıp sönme (1 sn) .5-1
    if state == "alert":
        hs, ho = 1.0, .5 + .5 * _wave(t, 1.0)
    else:
        w = _wave(t, 1.2 if state == "speaking" else 4.0)
        hs, ho = .92 + .13 * w, .7 + .3 * w
    parts = [f'<circle r="100" fill="{line}" fill-opacity="{.32 * ho:.3f}" transform="scale({hs:.3f})"/>']
    if state == "listening":   # dinleme dalgaları: 1,6 sn, ölçek .6->1,7, saydamlık .8->0, ikinci dalga .8 sn geride
        for off in (0.0, 0.8):
            k = ((t - off) % 1.6) / 1.6
            parts.append(f'<circle r="62" fill="none" stroke="{line}" stroke-width="4" stroke-opacity="{.8 * (1 - k):.3f}" '
                         f'transform="scale({.6 + 1.1 * k:.3f})"/>')
    dx = 5 * math.sin(2 * math.pi * (t - since) / .4) if state == "error" and 0 <= t - since < .8 else 0.0   # titreme .4 sn x2
    parts.append(f'<g transform="translate({dx:.2f} 0)">')
    parts.append(f'<circle r="60" fill="{body}" stroke="{line}" stroke-width="7"/>')
    spin = {"thinking": 2.5, "alert": 6.0}.get(state, 24.0)
    ang = 0.0 if state == "error" else (t % spin) / spin * 360
    dash = "2 14" if state == "error" else "6 8"
    parts.append(f'<circle r="44" fill="none" stroke="{line}" stroke-width="3" stroke-dasharray="{dash}" '
                 f'opacity="{1 if state == "thinking" else .7}" transform="rotate({ang:.1f})"/>')
    if state == "thinking":
        eye_sy = .5
    elif state == "listening":
        eye_sy = 1.15
    else:   # göz kırpma: 5 sn döngünün %92-100'ünde, %95'te en kapalı (.1)
        k = (t % 5.0) / 5.0
        eye_sy = 1.0 if k < .92 else 1 - .9 * (1 - abs(k - .95) / .03) if abs(k - .95) < .03 else 1.0
    for x in (-28, 14):
        cy = -1   # göz merkezi (y=-14, yükseklik 26)
        parts.append(f'<rect x="{x}" y="-14" width="14" height="26" rx="7" fill="{face}" '
                     f'transform="translate(0 {cy}) scale(1 {eye_sy:.3f}) translate(0 {-cy})"/>')
    if state == "thinking":   # üç nokta: 1,2 sn, %40'ta tam görünür, .2 sn arayla
        for i, x in enumerate((-12, 0, 12)):
            k = ((t - .2 * i) % 1.2) / 1.2
            op = .2 + .8 * max(0.0, 1 - abs(k - .4) / .4) if k <= .8 else .2
            parts.append(f'<circle cx="{x}" cy="30" r="4" fill="{face}" fill-opacity="{op:.3f}"/>')
    else:
        mouth = "M-14 34 Q0 22 14 34" if state == "error" else "M-14 26 Q0 36 14 26"
        sy = .3 + 1.3 * _wave(t, .35) if state == "speaking" else 1.0   # konuşma: .35 sn, dikey .3-1,6 (y=28 çevresinde)
        parts.append(f'<path d="{mouth}" fill="none" stroke="{face}" stroke-width="{7 if state == "speaking" else 5}" '
                     f'stroke-linecap="round" transform="translate(0 28) scale(1 {sy:.3f}) translate(0 -28)"/>')
    parts.append("</g>")
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-110 -110 220 220">' + "".join(parts) + "</svg>").encode("utf-8")


def view(snap: dict | None) -> dict:
    """Sunucu durumundan adanın görünümü (Qt'siz test edilir):
    {text, color, buttons, width, qid, title, mascot, mode}. mode: compact (boşta küçük hap) | active ("Hey Jarvis"ten sonra
    dinlerken/düşünürken/konuşurken: ada büyür, maskot ortaya gelir) | confirm (soru + Evet/Hayır).
    snap None ise (Jarvis'e ulaşılamıyor) gri, düğmesiz, maskot 'error'."""
    if not snap:
        return {"text": "Jarvis'e ulaşılamıyor", "color": COLORS["stopped"], "buttons": False, "width": NARROW, "qid": "", "title": "",
                "mascot": "error", "mode": "compact"}
    mascot = snap.get("mascot") if snap.get("mascot") in ("idle", "listening", "thinking", "speaking", "alert", "error") else "idle"
    cfg = snap.get("cfg") if isinstance(snap.get("cfg"), dict) else {}
    label = snap.get("label") or "—"
    color = COLORS.get(snap.get("state", ""), COLORS["starting"])
    if snap.get("kind") in ("confirm", "plan") and snap.get("id"):
        q = " ".join(str(snap.get("question", "")).split())
        q = q if len(q) <= MAX_Q else q[:MAX_Q - 1].rstrip() + "…"
        head = "Onay bekliyor" if snap["kind"] == "confirm" else "Plan onayı"
        left = int(snap.get("left") or 0)
        return {"text": q, "color": COLORS["confirm"], "buttons": True, "width": WIDE, "qid": str(snap["id"]),
                "title": f"{head}{f' · {left} sn' if left else ''}", "mascot": "alert", "mode": "confirm", "cfg": cfg}
    if mascot in ACTIVE_MASCOTS:
        return {"text": label + "…", "color": color, "buttons": False, "width": ACTIVE_W, "qid": "", "title": "", "mascot": mascot, "mode": "active", "cfg": cfg}
    return {"text": label, "color": color, "buttons": False, "width": NARROW, "qid": "", "title": "", "mascot": mascot, "mode": "compact", "cfg": cfg}


class Client:
    """Pano sunucusuyla yerel konuşma (anahtar başlıkta; adres yalnızca 127.0.0.1)."""

    def __init__(self, url: str):
        u = urlparse(url)
        if u.hostname not in ("127.0.0.1", "localhost"):
            raise ValueError("ada yalnızca yerel pano sunucusuna bağlanır")
        self.base = f"{u.scheme}://{u.netloc}"
        self.token = (parse_qs(u.query).get("t") or [""])[0]

    def _req(self, path: str, body: dict | None = None, timeout: float = 1.5):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"X-Token": self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310  (yalnızca 127.0.0.1)
            return json.loads(r.read().decode("utf-8"))

    def snapshot(self) -> dict | None:
        try:
            return self._req("/api/island")
        except (OSError, ValueError):
            return None

    def answer(self, yes: bool, qid: str) -> dict:
        try:
            return self._req("/api/island/answer", {"answer": "yes" if yes else "no", "id": qid})
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": type(exc).__name__}


def alive(pid: int | None) -> bool:
    if not pid:
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run_qt(client: Client, parent: int | None) -> int:
    try:
        from qtpy import QtCore, QtWidgets  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[ada] Qt yok ({type(exc).__name__}); ada açılmadı. pip install 'pywebview[qt]'", flush=True)
        return 1
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("JARVIS Ada")
    Qt = QtCore.Qt
    flags = Qt.WindowType if hasattr(Qt, "WindowType") else Qt

    win = QtWidgets.QWidget()
    win.setWindowTitle(TITLE)
    win.setWindowFlags(flags.FramelessWindowHint | flags.WindowStaysOnTopHint | flags.Tool | flags.WindowDoesNotAcceptFocus)
    wa = Qt.WidgetAttribute if hasattr(Qt, "WidgetAttribute") else Qt
    win.setAttribute(wa.WA_TranslucentBackground, True)
    win.setAttribute(wa.WA_ShowWithoutActivating, True)
    nofocus = (Qt.FocusPolicy if hasattr(Qt, "FocusPolicy") else Qt).NoFocus

    pill = QtWidgets.QFrame(win)
    pill.setObjectName("pill")
    outer = QtWidgets.QVBoxLayout(win)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(pill)
    col = QtWidgets.QVBoxLayout(pill)
    col.setContentsMargins(0, 0, 0, 0)
    rowbox = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(rowbox)
    row.setContentsMargins(14, 7, 10, 7)
    row.setSpacing(10)
    stage = QtWidgets.QWidget()               # etkin hal: büyük maskot ortada, durum yazısı altında
    stage_l = QtWidgets.QVBoxLayout(stage)
    stage_l.setContentsMargins(10, 10, 10, 8)
    stage_l.setSpacing(4)
    caption = QtWidgets.QLabel("")
    caption.setObjectName("caption")
    align = Qt.AlignmentFlag if hasattr(Qt, "AlignmentFlag") else Qt
    caption.setAlignment(align.AlignHCenter)
    stage_l.addWidget(caption)
    col.addWidget(rowbox)
    col.addWidget(stage)
    stage.hide()
    dot = QtWidgets.QLabel("●")
    try:  # maskot (durağan SVG); QtSvg yoksa eski renkli nokta kalır
        try:
            from qtpy.QtSvgWidgets import QSvgWidget  # noqa: PLC0415  (Qt6)
        except Exception:  # noqa: BLE001
            from qtpy.QtSvg import QSvgWidget  # noqa: PLC0415  (Qt5)
        face = QSvgWidget()
        face.setFixedSize(MASCOT_PX, MASCOT_PX)
        face.setToolTip("Çekirdek")
    except Exception:  # noqa: BLE001
        face = None
    texts = QtWidgets.QVBoxLayout()
    texts.setSpacing(0)
    title = QtWidgets.QLabel("")
    title.setObjectName("title")
    body = QtWidgets.QLabel("")
    body.setWordWrap(True)
    texts.addWidget(title)
    texts.addWidget(body)
    yes, no = QtWidgets.QPushButton("Evet"), QtWidgets.QPushButton("Hayır")
    yes.setObjectName("yes")
    for b in (yes, no):
        b.setFocusPolicy(nofocus)   # klavyeyle (Enter/boşluk) tetiklenemez
        b.setCursor(Qt.CursorShape.PointingHandCursor if hasattr(Qt, "CursorShape") else Qt.PointingHandCursor)
    row.addWidget(face if face is not None else dot)
    row.addLayout(texts, 1)
    row.addWidget(yes)
    row.addWidget(no)
    def style(theme: str, cfg: dict) -> str:
        acc, acc2, _body, bg, tx, border = palette(theme)
        fs = lambda px: f"{scaled(cfg, px)}px"  # noqa: E731
        light = theme == "light"
        btn = "rgba(0,0,0,18)" if light else "rgba(255,255,255,24)"
        return (f"#pill{{background:{bg};border:1px solid {border};border-radius:{fs(16)};}}"
                f"QLabel{{color:{tx};font-size:{fs(13)};}} #title{{color:{'#b86e00' if light else '#ffb74d'};font-size:{fs(11)};font-weight:600;}}"
                f"#caption{{color:{acc2 if not light else acc};font-size:{fs(12)};letter-spacing:1px;}}"
                f"QPushButton{{color:{tx};background:{btn};border:1px solid {border};border-radius:10px;padding:4px 14px;font-weight:600;"
                f"font-size:{fs(13)};}} QPushButton:hover{{border-color:{acc};}}"
                "#yes{color:#ffffff;background:rgba(52,168,83,190);border-color:rgba(52,168,83,230);} #yes:hover{background:rgba(52,168,83,230);}")

    cur = {"qid": "", "busy": False, "dead": 0, "last": None, "mode": "", "cfg": None, "theme": "cyan",
           "hidden": False, "last_active": time.monotonic(), "width": NARROW}
    win.setStyleSheet(style("cyan", {}))
    grow = QtCore.QPropertyAnimation(win, b"geometry")
    curve = QtCore.QEasingCurve.Type if hasattr(QtCore.QEasingCurve, "Type") else QtCore.QEasingCurve

    def screen_rect():
        return (win.screen() if hasattr(win, "screen") and win.screen() else app.primaryScreen()).availableGeometry()

    def target(width: int):
        scr = screen_rect()
        # yükseklik yalnızca görünen bölümden (satır ya da sahne) hesaplanır; düzen önbelleği temizlenir, yoksa küçülürken eski
        # (büyük) yükseklikte kalıyordu
        part = stage if stage.isVisibleTo(win) else rowbox
        lay = part.layout()
        lay.invalidate()
        lay.activate()
        h = lay.totalHeightForWidth(width) if lay.hasHeightForWidth() else part.sizeHint().height()
        h = max(h, part.minimumSizeHint().height())
        x, y = geometry_for(cur["cfg"] or {}, width, scr.x(), scr.y(), scr.width())
        return QtCore.QRect(x, y, width, h)

    def place(width: int, animate: bool):
        if cur["hidden"]:   # saklıyken yerleşim sessizce güncellenir; görünürken kayarak gelir (slide_in)
            return
        to = target(scaled(cur["cfg"] or {}, width))
        grow.stop()
        if animate and not REDUCED and win.isVisible():   # büyürken hafif yaylanır, küçülürken yumuşak iner
            grow.setDuration(GROW_MS)
            grow.setEasingCurve(curve.OutBack if to.width() > win.width() else curve.OutCubic)
            grow.setStartValue(win.geometry())
            grow.setEndValue(to)
            grow.start()
        else:
            win.setGeometry(to)

    # Kayma: pencere yöneticisi (Cinnamon) pencereyi ekranın üstüne çıkarmıyor (y 0'da kesiliyor; ölçüldü), bu yüzden pencere
    # yerinde kalır ve İÇİNDEKİ hap kaydırılır: saydam pencerenin üst kenarının arkasından çıkıyormuş gibi görünür.
    slide = QtCore.QVariantAnimation()
    slide.valueChanged.connect(lambda k: pill.move(0, round(-(1.0 - float(k)) * (pill.height() + 8))))

    def slide_in():
        """'Hey Jarvis' (ya da onay/hata): saklandığı yerden (üst kenarın arkası) kayarak gelir, hafifçe yaylanır."""
        cur["hidden"] = False
        to = target(scaled(cur["cfg"] or {}, cur["width"]))
        grow.stop()
        slide.stop()
        win.setGeometry(to)
        if REDUCED:
            pill.move(0, 0)
            win.show()
            return
        pill.move(0, -(to.height() + 8))
        win.show()
        slide.setDuration(SLIDE_IN_MS)
        slide.setEasingCurve(curve.OutBack)
        slide.setStartValue(0.0)
        slide.setEndValue(1.0)
        slide.start()

    def slide_out():
        """Sessizlik: hap yukarı kayıp üst kenarın arkasına saklanır, sonra pencere gizlenir (çizim/CPU yok)."""
        cur["hidden"] = True
        grow.stop()
        slide.stop()
        if REDUCED or not win.isVisible():
            win.hide()
            return
        slide.setDuration(SLIDE_OUT_MS)
        slide.setEasingCurve(curve.InCubic)
        slide.setStartValue(1.0)
        slide.setEndValue(0.0)
        slide.start()

    def slid():
        if cur["hidden"]:
            win.hide()
        pill.move(0, 0)

    slide.finished.connect(slid)

    def visibility(v: dict):
        """Otomatik gizlenme: her yoklamada (değişiklik olmasa da) süre dolmuş mu bakılır."""
        if (v.get("cfg") or {}).get("enabled") is False:
            return
        now = time.monotonic()
        if v.get("mode") in ("active", "confirm") or v.get("mascot") in ("alert", "error"):
            cur["last_active"] = now
        show = should_show(v, cur["last_active"], now)
        if show and cur["hidden"]:
            slide_in()
        elif not show and not cur["hidden"]:
            slide_out()

    def set_mode(mode: str):
        """Maskotu satır ile sahne arasında taşır (tek gösterge)."""
        if face is None or mode == cur["mode"]:
            return
        big = mode == "active"
        row.removeWidget(face)
        stage_l.removeWidget(face)
        px = scaled(cur["cfg"] or {}, ACTIVE_PX if big else MASCOT_PX)
        if big:
            stage_l.insertWidget(0, face, 0, align.AlignHCenter)
        else:
            row.insertWidget(0, face)
        face.setFixedSize(px, px)
        face.setVisible((cur["cfg"] or {}).get("mascot", True) is not False)
        rowbox.setVisible(not big)
        stage.setVisible(big)

    def render(v: dict):
        if v == cur["last"]:
            return
        cur["last"], cur["qid"] = v, v["qid"]
        dot.setStyleSheet(f"color:{v['color']};font-size:15px;")
        if face is not None and v.get("mascot") != cur.get("mascot"):
            cur["mascot"], cur["since"] = v.get("mascot"), time.monotonic()
            face.load(mascot_svg(cur["mascot"] or "idle", cur["since"], cur["since"], cur["theme"]))
        title.setText(v["title"])
        title.setVisible(bool(v["title"]))
        body.setText(v["text"])
        caption.setText(v["text"])
        yes.setVisible(v["buttons"])
        no.setVisible(v["buttons"])
        yes.setEnabled(True)
        no.setEnabled(True)
        cfg = v.get("cfg") or {}
        if cfg != cur["cfg"]:
            apply_cfg(cfg)
        if cfg.get("enabled") is False:
            return
        mode = v.get("mode", "compact") if face is not None else "compact"
        changed = mode != cur["mode"]
        set_mode(mode)
        cur["mode"] = mode
        cur["width"] = v["width"]
        place(v["width"], animate=changed)

    def apply_cfg(cfg: dict):
        """Ayarlar > ADA: tema, boyut, maskot, her zaman üstte, aç/kapa (yeniden başlatmadan uygulanır)."""
        old = cur["cfg"] or {}
        cur["cfg"], cur["theme"] = cfg, cfg.get("theme", "cyan") if cfg.get("theme") in PALETTES else "cyan"
        win.setStyleSheet(style(cur["theme"], cfg))
        cur["mode"] = ""                           # boyut/maskot değiştiyse yerleşim yeniden kurulsun
        if cfg.get("on_top", True) != old.get("on_top", True):
            win.setWindowFlag(flags.WindowStaysOnTopHint, cfg.get("on_top", True) is not False)
        if cfg.get("enabled") is False:
            grow.stop()
            win.hide()                             # yalnızca ada gizlenir; Jarvis çalışmaya devam eder
        elif not win.isVisible() and not cur["hidden"]:
            win.show()
        if face is not None and cur.get("mascot"):
            face.load(mascot_svg(cur["mascot"], time.monotonic(), cur.get("since", 0.0), cur["theme"]))

    def send(ok: bool):
        qid = cur["qid"]
        if not qid or cur["busy"]:
            return
        cur["busy"] = True
        yes.setEnabled(False)
        no.setEnabled(False)
        res = client.answer(ok, qid)
        cur["busy"] = False
        if not res.get("ok"):
            body.setText("Soru değişti ya da süresi doldu.")
        cur["last"] = None   # sonraki yoklamada yeniden çiz

    yes.clicked.connect(lambda: send(True))
    no.clicked.connect(lambda: send(False))

    def tick():
        if not alive(parent):
            cur["dead"] += 1
            if cur["dead"] >= 3:
                app.quit()
            return
        cur["dead"] = 0
        if not cur["busy"]:
            v = view(client.snapshot())
            render(v)
            visibility(v)

    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(POLL_MS)

    def frame():  # maskot animasyonu: durum yoklamasından bağımsız, ~15 kare/sn
        if face is not None and cur.get("mascot") and win.isVisible():
            face.load(mascot_svg(cur["mascot"], time.monotonic(), cur.get("since", 0.0), cur["theme"]))

    anim = QtCore.QTimer()
    anim.timeout.connect(frame)
    if face is not None and not REDUCED:
        anim.start(FRAME_MS)
    render(view(client.snapshot()))
    if (cur["cfg"] or {}).get("enabled", True) is not False:   # Ayarlar'da kapatılmışsa gizli başlar (tepsiden açılır)
        win.show()
    (app.exec if hasattr(app, "exec") else app.exec_)()
    del timer, anim
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Jarvis üst kenar adası")
    ap.add_argument("url", help="pano adresi (http://127.0.0.1:PORT/?t=ANAHTAR)")
    ap.add_argument("--parent", type=int, default=None, help="Jarvis süreç kimliği (kapanınca ada da kapanır)")
    a = ap.parse_args()
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("[ada] grafik oturumu yok; ada açılmadı.", flush=True)
        return 1
    return run_qt(Client(a.url), a.parent)


if __name__ == "__main__":
    sys.exit(main())
