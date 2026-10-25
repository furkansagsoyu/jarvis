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

import argparse
import json
import os
import sys
import urllib.request
from urllib.parse import parse_qs, urlparse

TITLE = "JARVIS Ada"
POLL_MS = 500
COLORS = {"starting": "#9aa0a6", "listening": "#34a853", "recording": "#00c853", "thinking": "#f9ab00", "speaking": "#4285f4", "muted": "#ea4335",
          "stopped": "#5f6368", "confirm": "#ff6d00"}
MAX_Q = 160
WIDE, NARROW = 580, 210
MASCOT_PX = 30
# Çekirdek maskotunun renkleri (assets/cekirdek.svg ile aynı): (çizgi, göz/ağız, gövde)
MASCOT_COLORS = {"alert": ("#f59e0b", "#fcd34d", "#33240a"), "error": ("#f43f5e", "#fda4af", "#33111b")}
MASCOT_DEFAULT = ("#22d3ee", "#67e8f9", "#0e2a35")


def mascot_svg(state: str) -> bytes:
    """Adada kullanılan DURAĞAN maskot: assets/cekirdek.svg'nin geometrisi, duruma göre renk ve yüz. Qt'nin SVG çizicisi
    CSS animasyonu ve değişken desteklemediği için animasyonlu sürüm yalnızca panoda (tarayıcıda) kullanılır."""
    line, face, body = MASCOT_COLORS.get(state, MASCOT_DEFAULT)
    parts = [f'<circle r="100" fill="{line}" fill-opacity="{.35 if state in ("speaking", "alert") else .18}"/>']
    if state == "listening":
        parts.append(f'<circle r="80" fill="none" stroke="{line}" stroke-width="5" stroke-opacity=".7"/>')
    parts.append(f'<circle r="60" fill="{body}" stroke="{line}" stroke-width="7"/>')
    parts.append(f'<circle r="44" fill="none" stroke="{line}" stroke-width="3" stroke-dasharray="6 8" opacity=".7"/>')
    eye_h, eye_y = (13, -7) if state == "thinking" else (26, -14)
    parts += [f'<rect x="{x}" y="{eye_y}" width="14" height="{eye_h}" rx="7" fill="{face}"/>' for x in (-28, 14)]
    if state == "thinking":
        parts += [f'<circle cx="{x}" cy="30" r="4" fill="{face}"/>' for x in (-12, 0, 12)]
    else:
        mouth = "M-14 34 Q0 22 14 34" if state == "error" else "M-16 24 Q0 42 16 24" if state == "speaking" else "M-14 26 Q0 36 14 26"
        parts.append(f'<path d="{mouth}" fill="none" stroke="{face}" stroke-width="{7 if state == "speaking" else 5}" stroke-linecap="round"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-110 -110 220 220">' + "".join(parts) + "</svg>").encode("utf-8")


def view(snap: dict | None) -> dict:
    """Sunucu durumundan adanın görünümü (Qt'siz test edilir):
    {text, color, buttons, width, qid, title, mascot}. snap None ise (Jarvis'e ulaşılamıyor) gri, düğmesiz, maskot 'error'."""
    if not snap:
        return {"text": "Jarvis'e ulaşılamıyor", "color": COLORS["stopped"], "buttons": False, "width": NARROW, "qid": "", "title": "", "mascot": "error"}
    mascot = snap.get("mascot") if snap.get("mascot") in ("idle", "listening", "thinking", "speaking", "alert", "error") else "idle"
    label = snap.get("label") or "—"
    color = COLORS.get(snap.get("state", ""), COLORS["starting"])
    if snap.get("kind") in ("confirm", "plan") and snap.get("id"):
        q = " ".join(str(snap.get("question", "")).split())
        q = q if len(q) <= MAX_Q else q[:MAX_Q - 1].rstrip() + "…"
        head = "Onay bekliyor" if snap["kind"] == "confirm" else "Plan onayı"
        left = int(snap.get("left") or 0)
        return {"text": q, "color": COLORS["confirm"], "buttons": True, "width": WIDE, "qid": str(snap["id"]),
                "title": f"{head}{f' · {left} sn' if left else ''}", "mascot": "alert"}
    return {"text": label, "color": color, "buttons": False, "width": NARROW, "qid": "", "title": "", "mascot": mascot}


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
    row = QtWidgets.QHBoxLayout(pill)
    row.setContentsMargins(14, 7, 10, 7)
    row.setSpacing(10)
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
    win.setStyleSheet(
        "#pill{background:rgba(8,14,26,232);border:1px solid rgba(120,160,200,90);border-radius:16px;}"
        "QLabel{color:#e8eef6;font-size:13px;} #title{color:#ffb74d;font-size:11px;font-weight:600;}"
        "QPushButton{color:#e8eef6;background:rgba(255,255,255,24);border:1px solid rgba(255,255,255,60);"
        "border-radius:10px;padding:4px 14px;font-weight:600;} QPushButton:hover{background:rgba(255,255,255,48);}"
        "#yes{background:rgba(52,168,83,170);border-color:rgba(52,168,83,230);} #yes:hover{background:rgba(52,168,83,220);}")
    cur = {"qid": "", "busy": False, "dead": 0, "last": None}

    def place(width: int):
        scr = (win.screen() if hasattr(win, "screen") and win.screen() else app.primaryScreen()).availableGeometry()
        win.setFixedWidth(width)
        win.adjustSize()
        win.move(scr.x() + (scr.width() - width) // 2, scr.y() + 6)

    def render(v: dict):
        if v == cur["last"]:
            return
        cur["last"], cur["qid"] = v, v["qid"]
        dot.setStyleSheet(f"color:{v['color']};font-size:15px;")
        if face is not None and v.get("mascot") != cur.get("mascot"):
            cur["mascot"] = v.get("mascot")
            face.load(mascot_svg(v.get("mascot", "idle")))
        title.setText(v["title"])
        title.setVisible(bool(v["title"]))
        body.setText(v["text"])
        yes.setVisible(v["buttons"])
        no.setVisible(v["buttons"])
        yes.setEnabled(True)
        no.setEnabled(True)
        place(v["width"])

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
            render(view(client.snapshot()))

    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(POLL_MS)
    render(view(client.snapshot()))
    win.show()
    (app.exec if hasattr(app, "exec") else app.exec_)()
    del timer
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
