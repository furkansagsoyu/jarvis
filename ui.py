#!/usr/bin/env python3
"""Jarvis arayüzü: küçük durum penceresi + (varsa) sistem tepsisi simgesi.

main.py --ui ile otomatik başlar; elle de açılabilir: python ui.py
- Pencere: durum noktası, son konuşma satırları, "Sessize al" ve "Kapat" düğmeleri.
- Tepsi simgesi (pystray + pillow kuruluysa): renk durumu gösterir; menü: Göster, Sessize al, Kapat.
  Kurulu değilse yalnızca pencere açılır (pip install pystray pillow).
- Ses/model işine karışmaz: yalnızca data/status.json'u okur, data/control.json'a yazar (bkz. ui_state.py).
"""
import os
import queue
import signal
import sys

import ui_state

COLORS = {"starting": "#9aa0a6", "listening": "#34a853", "thinking": "#f9ab00", "speaking": "#4285f4", "muted": "#ea4335", "stopped": "#5f6368"}
POLL_MS = 400


def effective_state(st: dict) -> str:
    """Sessize alınmışsa durum ne olursa olsun 'muted' gösterilir."""
    return "muted" if ui_state.is_muted() else st.get("state", "starting")


def turns_text(st: dict) -> str:
    return "\n".join(f"{'Sen' if t['who'] == 'sen' else 'Jarvis'}: {t['text']}" for t in st.get("turns", []))


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_jarvis(st: dict) -> None:
    pid = st.get("pid")
    if alive(pid) and pid != os.getpid():
        os.kill(pid, signal.SIGTERM)


_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def ascii_title(text: str) -> str:
    """X11 tepsi ipucu Latin-1 ister; Türkçe harfler ASCII'ye çevrilir (pencerede Türkçe kalır)."""
    return text.translate(_TR)


def make_icon(color: str):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
    return img


def run():
    import tkinter as tk  # noqa: PLC0415

    root = tk.Tk()
    root.title("Jarvis")
    root.geometry("360x300+40+60")
    root.attributes("-topmost", True)
    dot = tk.Label(root, text="●", font=("Sans", 22))
    label = tk.Label(root, text="", font=("Sans", 13, "bold"))
    dot.grid(row=0, column=0, padx=(12, 4), pady=8)
    label.grid(row=0, column=1, sticky="w")
    box = tk.Text(root, height=10, width=44, wrap="word", state="disabled", font=("Sans", 10))
    box.grid(row=1, column=0, columnspan=3, padx=10, pady=4, sticky="nsew")
    root.grid_rowconfigure(1, weight=1)
    root.grid_columnconfigure(2, weight=1)
    btns = tk.Frame(root)
    btns.grid(row=2, column=0, columnspan=3, pady=8)

    def toggle_mute():
        ui_state.set_muted(not ui_state.is_muted())

    def quit_all():
        stop_jarvis(ui_state.read_status())
        shutdown()

    mute_btn = tk.Button(btns, text="Sessize al", command=toggle_mute)
    mute_btn.pack(side="left", padx=6)
    tk.Button(btns, text="Jarvis'i kapat", command=quit_all).pack(side="left", padx=6)

    actions: queue.Queue = queue.Queue()  # tepsi iş parçacığından gelen istekler ana (Tk) iş parçacığında işlenir
    icon = None
    try:
        import pystray  # noqa: PLC0415

        menu = pystray.Menu(
            pystray.MenuItem("Göster", lambda: actions.put("show"), default=True),
            pystray.MenuItem("Sessize al / aç", lambda: actions.put("mute")),
            pystray.MenuItem("Jarvis'i kapat", lambda: actions.put("quit")),
        )
        icon = pystray.Icon("jarvis", make_icon(COLORS["starting"]), "Jarvis", menu)
        icon.run_detached()
    except Exception as exc:  # noqa: BLE001  (kütüphane yok / tepsi desteklenmiyor: yalnızca pencere)
        print(f"[ui] tepsi simgesi yok ({type(exc).__name__}); yalnızca pencere açık.", flush=True)
        icon = None

    def show():
        root.deiconify()
        root.lift()

    def shutdown():
        # icon.stop() "setup did not finish within 5.0 seconds" uyarısı veriyordu; süreç zaten bitiyor,
        # simge de onunla kapanır. Bu yüzden durdurmak yerine süreci doğrudan sonlandırıyoruz.
        try:
            root.destroy()
        finally:
            os._exit(0)

    # Tepsi varken pencereyi kapatmak gizler; tepsi yoksa arayüz kapanır (Jarvis çalışmaya devam eder).
    root.protocol("WM_DELETE_WINDOW", root.withdraw if icon else shutdown)

    last = {"state": None, "text": None}

    def tick():
        while not actions.empty():
            act = actions.get_nowait()
            {"show": show, "mute": toggle_mute, "quit": quit_all}[act]()
            if act == "quit":
                return
        st = ui_state.read_status()
        state = effective_state(st)
        if state != last["state"]:
            dot.config(fg=COLORS.get(state, "#9aa0a6"))
            label.config(text=ui_state.STATES.get(state, state))
            mute_btn.config(text="Sesi aç" if state == "muted" else "Sessize al")
            if icon:
                try:
                    icon.icon = make_icon(COLORS.get(state, "#9aa0a6"))
                    icon.title = ascii_title(f"Jarvis: {ui_state.STATES.get(state, state)}")
                except Exception as exc:  # noqa: BLE001  (tepsi güncellemesi arayüzü asla düşürmesin)
                    print(f"[ui] tepsi güncellenemedi ({type(exc).__name__}: {exc})", flush=True)
            last["state"] = state
        text = turns_text(st)
        if text != last["text"]:
            box.config(state="normal")
            box.delete("1.0", "end")
            box.insert("end", text)
            box.see("end")
            box.config(state="disabled")
            last["text"] = text
        if st.get("pid") and not alive(st["pid"]) and state != "stopped":
            ui_state.set_state("stopped")  # Jarvis çökmüş ya da öldürülmüş: kapalı göster
        root.after(POLL_MS, tick)

    tick()
    root.mainloop()


if __name__ == "__main__":
    if not os.environ.get("DISPLAY"):
        sys.exit("DISPLAY yok: arayüz grafik oturum ister.")
    run()
