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
COLORS = {"starting": "#9aa0a6", "listening": "#34a853", "thinking": "#f9ab00", "speaking": "#4285f4", "muted": "#ea4335",
          "stopped": "#5f6368", "confirm": "#ff6d00"}
MAX_Q = 160
WIDE, NARROW = 560, 190


def view(snap: dict | None) -> dict:
    """Sunucu durumundan adanın görünümü (Qt'siz test edilir):
    {text, color, buttons, width, qid, title}. snap None ise (Jarvis'e ulaşılamıyor) gri, düğmesiz."""
    if not snap:
        return {"text": "Jarvis'e ulaşılamıyor", "color": COLORS["stopped"], "buttons": False, "width": NARROW, "qid": "", "title": ""}
    label = snap.get("label") or "—"
    color = COLORS.get(snap.get("state", ""), COLORS["starting"])
    if snap.get("kind") in ("confirm", "plan") and snap.get("id"):
        q = " ".join(str(snap.get("question", "")).split())
        q = q if len(q) <= MAX_Q else q[:MAX_Q - 1].rstrip() + "…"
        head = "Onay bekliyor" if snap["kind"] == "confirm" else "Plan onayı"
        left = int(snap.get("left") or 0)
        return {"text": q, "color": COLORS["confirm"], "buttons": True, "width": WIDE, "qid": str(snap["id"]),
                "title": f"{head}{f' · {left} sn' if left else ''}"}
    return {"text": label, "color": color, "buttons": False, "width": NARROW, "qid": "", "title": ""}


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
    row.addWidget(dot)
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
