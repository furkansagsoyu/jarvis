#!/usr/bin/env python3
"""Tek komutlu sağlık ve doğruluk testi.

    python check_all.py              # mantık testleri (modelsiz, saniyeler) + ortam kontrolü
    python check_all.py --model      # + gerçek model araç seçimi (tool_check.py, GPU ve Ollama ister, birkaç dk)
    python check_all.py --quick      # yalnızca mantık testleri
    python check_all.py --env        # yalnızca ortam kontrolü
    python check_all.py --vision     # + gerçek ekran görüşü (ekran görüntüsünü yerel modele okutur)

Kişisel veri dosyalarına dokunmaz: geçici bir data/ ve geçici bir ev klasörü kullanılır.
Çıkış kodu: hata varsa 1 (UYARI hata sayılmaz).
"""
import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REAL_DATA = HERE / "data"           # gerçek veri klasörü (ortam kontrolü yalnızca OKUR)
TMP = Path(tempfile.mkdtemp(prefix="jarvis_check_"))
os.environ["JARVIS_DATA"] = str(TMP / "data")  # testler gerçek hatırlatıcı/hafıza dosyalarını bozmasın

results: list[tuple[str, str, str]] = []  # (durum, ad, ayrıntı)


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    mark = {"OK": "OK   ", "UYARI": "UYARI", "HATA": "HATA "}[status]
    print(f"  {mark} {name}" + (f"  — {detail}" if detail else ""), flush=True)


def check(name):
    """Fonksiyonu test olarak çalıştırır: AssertionError/istisna = HATA."""
    def deco(fn):
        try:
            detail = fn() or ""
            record("OK", name, detail)
        except Exception as exc:  # noqa: BLE001
            record("HATA", name, f"{type(exc).__name__}: {exc}")
        return fn
    return deco


# --------------------------------------------------------------------- 1) mantık testleri
def logic_tests() -> None:
    print("\n[1] Mantık testleri (model gerekmez)")
    try:
        import ollama  # noqa: F401
    except ImportError:
        sys.modules["ollama"] = types.ModuleType("ollama")

    home = TMP / "home"
    for d in ("Belgeler", "Indirilenler", "Masaustu"):
        (home / d).mkdir(parents=True, exist_ok=True)
    (home / "Belgeler/rapor.txt").write_text("eski rapor")
    time.sleep(0.02)
    (home / "Indirilenler/rapor.txt").write_text("yeni rapor")
    (home / "Belgeler/notlar.txt").write_text("notlar")
    bat = TMP / "bat/BAT0"
    bat.mkdir(parents=True)
    (bat / "capacity").write_text("18")
    (bat / "status").write_text("Discharging")
    os.environ["JARVIS_POWER_DIR"] = str(bat.parent)

    from skills import _confirm, _undo, battery, briefing, files, load_skills, reminders, web  # noqa: PLC0415
    from skills import _store  # noqa: PLC0415
    files.HOME = home

    @check("Yetenekler yükleniyor, çift isim yok")
    def _():
        tools = load_skills()
        assert len(tools) >= 22, f"yalnızca {len(tools)} araç"
        return f"{len(tools)} araç"

    @check("Hatırlatıcı kalıcılığı (yeniden başlatma + kaçırılanlar)")
    def _():
        reminders.set_reminder(minutes=10, message="deneme")
        for r in list(reminders._active):
            r["timer"].cancel()
        reminders._active.clear()
        assert reminders.restore() == "" and "deneme" in reminders.list_reminders()
        _store.save("reminders.json", [{"id": 9, "when": (dt.datetime.now() - dt.timedelta(minutes=3)).isoformat(), "message": "ilaç"}])
        assert "ilaç" in reminders.restore()
        reminders.cancel_reminders()

    @check("Dosya bul → 'ikincisini oku' bağlamı")
    def _():
        files._last = []
        assert "bilmiyorum" in files.read_file("onu")
        assert "2 dosya" in files.find_files("rapor")
        assert "dosyasının içeriği" in files.read_file("ikincisini")
        assert "kaçıncı" in files.read_file("onu")

    @check("Aynı isimli dosya uyarısı")
    def _():
        assert "aynı isimde 1 dosya daha" in files.read_file("rapor.txt")

    @check("Taşı → onay kapısı → evet → geri al")
    def _():
        assert "Onaylıyor musun" in files.move_file("notlar", "Masaustu")
        assert _confirm.has_pending() and _confirm.classify("evet") == "yes"
        assert "taşıdım" in _confirm.approve()
        assert (home / "Masaustu/notlar.txt").exists()
        assert "geri taşındı" in _undo.undo_last()
        assert (home / "Belgeler/notlar.txt").exists()

    @check("Onay kapısı: hayır / bekleyen yok")
    def _():
        files.move_file("notlar", "Masaustu")
        assert _confirm.classify("hayır") == "no" and _confirm.classify("saat kaç") == "other"
        _confirm.cancel()
        assert not _confirm.has_pending()

    @check("Hassas dosya engeli (.env, gizli klasör)")
    def _():
        (home / ".gizli").mkdir(exist_ok=True)
        (home / ".gizli/x.txt").write_text("x")
        (home / "anahtar.env").write_text("K=1")
        assert "bulamadım" in files.read_file("anahtar") or "güvenlik" in files.read_file("anahtar")

    @check("Pil: okuma ve uyarı eşikleri")
    def _():
        assert "yüzde 18" in battery.get_battery()
        said = []
        m = battery.Monitor(said.append)
        m.check()
        m.check()
        assert len(said) == 1, said
        (bat / "capacity").write_text("9")
        m.check()
        assert len(said) == 2
        (bat / "status").write_text("Charging")
        m.check()
        assert not m._warned

    @check("Web: ayrıştırıcı ve yedek zinciri")
    def _():
        page = ('<a class="result__a" href="//x">Ankara - <b>Vikipedi</b></a>'
                '<a class="result__snippet" href="#">Başkent &amp; büyük şehir.</a>')
        assert web.parse_ddg(page) == [("Ankara - Vikipedi", "Başkent & büyük şehir.")]
        assert web.parse_ddg("<html>captcha</html>") == []
        web._ddg = lambda q: web.parse_ddg(page)
        out = web.web_search("ankara")
        assert "yalnızca veri" in out and "Başkent" in out

    @check("Sabah özeti: bir kez / saat penceresi")
    def _():
        t = dt.datetime(2026, 10, 17, 8, 0)
        assert briefing.due_today(t)
        briefing.mark_done(t)
        assert not briefing.due_today(t.replace(hour=9))
        assert briefing.due_today(t.replace(day=18))
        assert not briefing.due_today(t.replace(day=19, hour=15))

    @check("Telegram: yetkisiz sohbet yok sayılır, read_file/recall uzaktan kapalı")
    def _():
        import brain as B  # noqa: PLC0415
        import telegram_bot as tb  # noqa: PLC0415
        brain = B.Brain()
        sent = []

        def api(method, **p):
            if method == "getUpdates":
                return {"ok": True, "result": [
                    {"update_id": 1, "message": {"chat": {"id": 111}, "text": "pil kaç"}},
                    {"update_id": 2, "message": {"chat": {"id": 999}, "text": "dosyaları sil"}}]}
            sent.append(p)
            return {"ok": True}
        bot = tb.TelegramBot("T", 111, lambda t: "".join(brain.reply_stream(t)), api=api)
        bot.poll_once(timeout=0)
        assert [p["chat_id"] for p in sent] == [111], sent
        brain.remote = True
        assert "uzaktan yapmıyorum" in brain._call_tool("read_file", {"name": "x"})
        assert "uzaktan yapmıyorum" in brain._call_tool("recall", {"query": "x"})
        assert len(tb.chunks("a" * 9000)) == 3

    @check("Arayüz durumu ve sessize alma")
    def _():
        import ui  # noqa: PLC0415
        import ui_state  # noqa: PLC0415
        ui_state.reset()
        ui_state.add_turn("sen", "merhaba")
        ui_state.set_state("thinking")
        assert ui.effective_state(ui_state.read_status()) == "thinking"
        ui_state.set_muted(True)
        assert ui.effective_state(ui_state.read_status()) == "muted"
        ui_state.set_muted(False)
        ui.ascii_title("Jarvis: Düşünüyor, Kapalı, Başlıyor").encode("latin-1")  # tepsi Latin-1 hatası bir daha olmasın

    @check("Hoparlör seçici (numara / ad parçası)")
    def _():
        import tts  # noqa: PLC0415
        devs = [{"name": "HDA Intel", "max_output_channels": 2}, {"name": "HDMI 0", "max_output_channels": 8},
                {"name": "Mikrofon", "max_output_channels": 0}, {"name": "USB Kulaklık", "max_output_channels": 2}]
        assert tts.pick_output(devs, "hdmi")[0] == 1 and tts.pick_output(devs, "3")[0] == 3
        assert tts.pick_output(devs, "2")[0] is None and tts.pick_output(devs, "yok")[0] is None

    @check("Sustur isteği (arayüz → ana döngü)")
    def _():
        import threading  # noqa: PLC0415
        import tts  # noqa: PLC0415
        import ui_state  # noqa: PLC0415
        ui_state.reset()
        assert not ui_state.consume_stop()
        ui_state.request_stop()
        assert ui_state.consume_stop() and not ui_state.consume_stop()
        sp = tts.BaseSpeaker()
        sp._stop = threading.Event()
        assert not sp.is_busy() and not sp.interrupted()
        sp._pending = 1
        sp._stop.set()
        assert sp.is_busy() and sp.interrupted()

    @check("Susturma takılmıyor: konuşma anında kesilir, sonraki cevap yutulmaz")
    def _():
        import threading  # noqa: PLC0415

        import numpy as np  # noqa: PLC0415
        log = {"abort": 0, "stop": 0}

        class FakeStream:  # gerçek zamanlı çalıyormuş gibi bekler
            def __init__(self, **kw): pass
            def start(self): pass
            def write(self, x): time.sleep(len(x) / 48000)
            def abort(self): log["abort"] += 1
            def stop(self): log["stop"] += 1
            def close(self): pass
        fake = types.ModuleType("sounddevice")
        fake.OutputStream = FakeStream
        saved = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = fake
        try:
            import tts  # noqa: PLC0415

            class Sp(tts.BaseSpeaker):
                sample_rate = 48000
                def __init__(self): self._stop = threading.Event()
                def _synth(self, s): return np.zeros(96000, dtype=np.float32)  # cümle başına 2 sn
            sp = Sp()
            sp.say("Birinci cümle burada. İkinci cümle burada. Üçüncü cümle burada.")
            time.sleep(0.4)
            t0 = time.perf_counter()
            sp.stop()
            sp.wait()
            assert time.perf_counter() - t0 < 1.0 and log["abort"] == 1, "kesilmedi ya da takıldı"
            sp.say("Yeni cevap.")
            sp.wait()
            assert log["stop"] == 1, "kesmeden sonraki cevap çalınmadı"
        finally:
            if saved is None:
                sys.modules.pop("sounddevice", None)
            else:
                sys.modules["sounddevice"] = saved

    @check("Ekran görüşü: görüntü modele gidiyor, görüntüsüz model net hata veriyor")
    def _():
        import ollama  # noqa: PLC0415
        from skills import screen  # noqa: PLC0415
        seen = {}
        real_chat = getattr(ollama, "chat", None)

        def fake(**kw):
            seen.update(kw)
            if seen.get("fail"):
                raise RuntimeError("model does not support images")
            return {"message": {"content": "Ekranda bir terminal açık."}}
        ollama.chat = fake
        real_cap = screen.capture
        screen.capture = lambda: b"PNG"
        try:
            assert "terminal" in screen.look_at_screen("ne var")
            assert seen["messages"][0]["images"] == [b"PNG"] and seen["think"] is False
            ollama.chat = lambda **kw: (_ for _ in ()).throw(RuntimeError("model does not support images"))
            assert "görüntü okuyamıyor" in screen.look_at_screen("")
        finally:
            screen.capture = real_cap
            if real_chat:
                ollama.chat = real_chat

    @check("Hızlı yol cümleleri (test_routes)")
    def _():
        r = subprocess.run([sys.executable, str(HERE / "test_routes.py")], capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(HERE)}, timeout=120)
        assert r.returncode == 0, r.stdout[-400:]
        return re.findall(r"TÜMÜ TAMAM|\d+ HATA", r.stdout)[-1]


# --------------------------------------------------------------------- 2) ortam kontrolü
def env_checks() -> None:
    print("\n[2] Ortam kontrolü (bu bilgisayar)")

    @check("Python ortamı")
    def _():
        env = os.environ.get("CONDA_DEFAULT_ENV", "")
        if env != "freya":
            raise AssertionError(f"freya ortamında değilsin (şu an: {env or 'yok'})")
        return sys.version.split()[0]

    for mod, why in (("faster_whisper", "konuşmayı yazıya çevirme"), ("sounddevice", "mikrofon/hoparlör"),
                     ("ollama", "model bağlantısı"), ("openwakeword", "Hey Jarvis"), ("ema_lightning", "EMA ses motoru")):
        try:
            __import__(mod)
            record("OK", f"{mod} kurulu", why)
        except Exception as exc:  # noqa: BLE001  (ImportError ya da PortAudio gibi sistem kütüphanesi hatası)
            record("HATA", f"{mod} yüklenemedi ({type(exc).__name__})", why)
    try:
        import pystray  # noqa: F401
        record("OK", "pystray kurulu", "tepsi simgesi")
    except ImportError:
        record("UYARI", "pystray kurulu değil", "isteğe bağlı: pip install pystray pillow")

    @check("Ollama çalışıyor ve gemma4:e4b var")
    def _():
        import ollama  # noqa: PLC0415
        names = [getattr(m, "model", None) or m.get("model") or m.get("name") for m in ollama.list()["models"]]
        assert any(str(n).startswith("gemma4:e4b") for n in names), f"modeller: {names}"

    @check("Mikrofon bulundu")
    def _():
        import sounddevice as sd  # noqa: PLC0415
        n = sum(1 for d in sd.query_devices() if d["max_input_channels"] > 0)
        assert n > 0, "giriş cihazı yok"
        return f"{n} giriş cihazı"

    smi = shutil.which("nvidia-smi")
    if smi:
        out = subprocess.run([smi, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True).stdout.strip()
        try:
            used, total = (int(x) for x in out.split(","))
            free = total - used
            record("OK" if free >= 1000 else "UYARI", "GPU boş bellek", f"{free} MB boş / {total} MB"
                   + ("" if free >= 1000 else " (Whisper+Gemma yüklüyken normal; kapalıyken az ise başka program kullanıyor)"))
        except ValueError:
            record("UYARI", "GPU bellek okunamadı")
    else:
        record("UYARI", "nvidia-smi yok", "GPU bilgisi alınamadı")

    from skills import battery  # noqa: PLC0415
    battery.SYS = Path(os.environ.get("JARVIS_REAL_POWER_DIR", "/sys/class/power_supply"))  # mantık testindeki sahte pili bırak
    b = battery.read_battery()
    if not b:
        record("OK", "Pil", "pil yok (masaüstü)")
    elif b[1] == "Discharging":
        record("UYARI", "Şarja takılı değil", f"yüzde {b[0]}: pilde GPU yaklaşık 9 kat yavaş")
    else:
        record("OK", "Şarja takılı", f"yüzde {b[0]}")

    if os.environ.get("DISPLAY"):
        try:
            from skills import screen  # noqa: PLC0415
            n = len(screen.capture())
            record("OK", "Ekran görüntüsü alınabiliyor", f"{n // 1024} KB (bellekte, diske yazılmadı)")
        except Exception as exc:  # noqa: BLE001
            record("UYARI", "Ekran görüntüsü alınamadı", f"{exc}")
    record("OK" if os.environ.get("DISPLAY") else "UYARI", "Grafik oturumu (DISPLAY)",
           "" if os.environ.get("DISPLAY") else "arayüz (--ui) açılamaz")

    cfg = {}
    try:
        import json  # noqa: PLC0415
        cfg = json.loads((REAL_DATA / "telegram.json").read_text())
    except (OSError, ValueError):
        pass
    record("OK" if cfg.get("token") and cfg.get("chat_id") else "UYARI", "Telegram",
           "kurulu" if cfg.get("token") and cfg.get("chat_id") else "kurulu değil (python telegram_bot.py --setup)")

    desktop = Path.home() / ".config/autostart/jarvis.desktop"
    if desktop.exists():
        text = desktop.read_text()
        flags = [f for f in ("--wake", "--ui", "--morning", "--telegram") if f in text]
        want_tg = bool(cfg.get("token") and cfg.get("chat_id"))
        stale = want_tg and "--telegram" not in text
        record("UYARI" if stale else "OK", "Otomatik başlatma", "kurulu: " + " ".join(flags)
               + (" — Telegram kurulu ama bayrak yok: python autostart.py --install" if stale else ""))
    else:
        record("UYARI", "Otomatik başlatma kurulu değil", "python autostart.py --install")
    log = REAL_DATA / "jarvis.log"
    if log.exists():
        tail = log.read_text(errors="replace")[-3000:]
        record("UYARI" if "Traceback" in tail else "OK", "Son otomatik başlatma günlüğü",
               "Traceback var: tail -40 data/jarvis.log" if "Traceback" in tail else "temiz")


# --------------------------------------------------------------------- 3) model testi
def model_checks(repeat: int) -> None:
    print(f"\n[3] Gerçek model araç seçimi (tool_check.py, her cümle {repeat} kez)")
    r = subprocess.run([sys.executable, str(HERE / "tool_check.py"), "--repeat", str(repeat)],
                       capture_output=True, text=True, cwd=HERE, timeout=1800)
    out = r.stdout + r.stderr
    bad = [ln for ln in out.splitlines() if ln.startswith("HATA")]
    m = re.search(r"TOPLAM: (\d+)/(\d+)", out)
    if not m:
        record("HATA", "tool_check çalışmadı", out[-300:].replace("\n", " "))
        return
    ok, total = int(m.group(1)), int(m.group(2))
    ratio = ok / total
    record("OK" if ratio >= 0.97 else "HATA", "Araç seçimi", f"{ok}/{total} (%{ratio * 100:.0f})")
    for ln in bad[:10]:
        print("        " + ln)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model", action="store_true", help="gerçek model araç seçimini de çalıştır")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--vision", action="store_true", help="gerçek ekran görüşünü dene (görsel model ister)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true", help="yalnızca mantık testleri")
    g.add_argument("--env", action="store_true", help="yalnızca ortam kontrolü")
    a = ap.parse_args()
    t0 = time.perf_counter()
    if not a.env:
        logic_tests()
    if not a.quick:
        env_checks()
    if a.model:
        model_checks(a.repeat)
    if a.vision:
        print("\n[4] Ekran görüşü (gerçek model)")
        from skills import screen  # noqa: PLC0415
        t1 = time.perf_counter()
        ans = screen.look_at_screen("Ekranda ne olduğunu iki cümleyle anlat.")
        bad = ans.startswith("Hata") or "okuyamıyor" in ans or "okuyamadım" in ans
        record("HATA" if bad else "OK", "Ekran görüşü", f"{time.perf_counter() - t1:.1f} sn: {ans[:200]}")
    shutil.rmtree(TMP, ignore_errors=True)
    n = {s: sum(1 for r in results if r[0] == s) for s in ("OK", "UYARI", "HATA")}
    print(f"\nÖZET: {n['OK']} OK, {n['UYARI']} uyarı, {n['HATA']} hata ({time.perf_counter() - t0:.0f} sn)")
    for s, name, detail in results:
        if s == "HATA":
            print(f"  HATA: {name} — {detail}")
    sys.exit(1 if n["HATA"] else 0)


if __name__ == "__main__":
    main()
