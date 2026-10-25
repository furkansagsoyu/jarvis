"""Sistem bakım ajanı: RAM/swap/bellek baskısı, VRAM, Ollama modelleri ve ayarları, disk, workspace, Jarvis günlüğü ve unutulmuş
Gradle süreçlerinin sağlık özeti + öneriler.

Kendi başına HİÇBİR değişiklik yapmaz. Güvenle geri alınabilen iki düzeltme (fazladan yüklü Ollama modelini boşaltmak, unutulmuş
Gradle/Kotlin daemon'larını durdurmak) yalnızca onay kapısıyla (_confirm) önerilir; sudo gerektiren işler (swap, sysctl, Ollama servis
ayarları) yalnızca öneri olarak söylenir. Tüm veri yerelde kalır (model çağrısı yok).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from skills import _confirm as confirm
from skills import _store

DISK_WARN_GB = 15.0
DISK_CRIT_GB = 5.0
VRAM_WARN = 0.95          # VRAM doluluk oranı
SWAP_WARN = 0.5
WS_WARN_GB = 1.0
WS_WARN_PROJECTS = 30
LOG_TAIL = 20_000         # günlüğün son kaç karakterine bakılır
DAEMON_MARKS = ("GradleDaemon", "KotlinCompileDaemon")


@dataclass
class Finding:
    level: str            # "sorun" | "uyarı" | "öneri"
    text: str
    fix: str = ""         # onaylanırsa uygulanacak düzeltmenin kısa adı (fixes() içinde)


def _gb(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


# ------------------------------------------------------------------ veri toplama (yalnızca okuma)
def _daemons(proc: Path = Path("/proc")) -> list[tuple[int, str, float]]:
    """Unutulmuş Gradle/Kotlin daemon'ları: [(pid, ad, GB)]. Yalnızca bu kullanıcının süreçleri."""
    out = []
    uid = os.getuid()
    try:
        entries = list(proc.iterdir())
    except OSError:
        return []
    for d in entries:
        if not d.name.isdigit():
            continue
        try:
            if d.stat().st_uid != uid:
                continue
            cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            mark = next((m for m in DAEMON_MARKS if m in cmd), "")
            if not mark:
                continue
            rss = next((int(ln.split()[1]) for ln in (d / "status").read_text().splitlines() if ln.startswith("VmRSS:")), 0)
        except (OSError, ValueError, IndexError):
            continue
        out.append((int(d.name), mark, rss / 1048576.0))
    return out


def _dir_size(root: Path, limit: int = 20000) -> float:
    total, n = 0, 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            n += 1
            if n > limit:
                return total / 1e9
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total / 1e9


def gather() -> dict:
    import memguard  # noqa: PLC0415
    import ram_report  # noqa: PLC0415
    data: dict = {}
    try:
        data["mem"] = {**memguard.read_meminfo(), "psi": memguard.read_psi()}
        data["top"] = memguard.top_consumers(3)
    except OSError:
        data["mem"] = None
    data["vram"] = ram_report.gpu_mem()
    data["models"] = ram_report.ollama_ps()
    data["env"] = ram_report.ollama_env()
    try:
        import brain  # noqa: PLC0415
        data["active_model"] = brain.MODEL
    except Exception:  # noqa: BLE001
        data["active_model"] = ""
    disks = {}
    for p in (Path.home(), Path("/")):
        try:
            u = shutil.disk_usage(p)
        except OSError:
            continue
        if not any(abs(v[1] - u.total / 1e9) < 0.01 and abs(v[0] - u.free / 1e9) < 0.5 for v in disks.values()):  # aynı bölüm iki kez sayılmaz
            disks[str(p)] = (u.free / 1e9, u.total / 1e9)
    data["disk"] = disks
    try:
        from skills import codeagent  # noqa: PLC0415
        ws = codeagent.WORKSPACE
        data["ws"] = {"projects": sum(1 for d in ws.iterdir() if d.is_dir()), "gb": _dir_size(ws)} if ws.is_dir() else None
    except Exception:  # noqa: BLE001
        data["ws"] = None
    log = _store.path("jarvis.log")
    try:
        with open(log, "rb") as f:
            f.seek(max(0, log.stat().st_size - LOG_TAIL))
            data["log"] = {"tracebacks": f.read().decode("utf-8", "replace").count("Traceback")}
    except OSError:
        data["log"] = None
    data["daemons"] = _daemons()
    return data


# ------------------------------------------------------------------ değerlendirme (saf fonksiyon, test edilir)
def analyze(data: dict) -> tuple[list[str], list[Finding]]:
    """(durum cümleleri, bulgular). Bulgular önem sırasına göre."""
    status, found = [], []
    mem = data.get("mem")
    if mem:
        import memguard  # noqa: PLC0415
        lvl = memguard.level(mem, mem.get("psi"))
        status.append(f"Bellekte {_gb(mem['available'])} gigabayt boş ({_gb(mem['total'])} içinden).")
        top = ", ".join(f"{n} {_gb(g)}" for n, g in (data.get("top") or [])[:3])
        if lvl == "critical":
            found.append(Finding("sorun", "Bellek kritik düzeyde azaldı" + (f"; en çok kullananlar: {top}" if top else "") + ". Gereksiz uygulamaları kapat."))
        elif lvl == "low":
            found.append(Finding("uyarı", "Bellek azalıyor" + (f"; en çok kullananlar: {top}" if top else "") + "."))
        st = mem.get("swap_total", 0)
        if st < 0.5:
            found.append(Finding("öneri", "Swap yok ya da çok az; bellek biterse sistem donabilir. RAM.md'deki 4 gigabaytlık swap dosyası adımlarını uygula."))
        elif (st - mem.get("swap_free", 0)) / st > SWAP_WARN:
            found.append(Finding("öneri", f"Swap yüzde {(st - mem['swap_free']) / st * 100:.0f} dolu. RAM şu an boşsa sudo swapoff -a ve swapon -a ile boşaltabilirsin."))
    vram = data.get("vram")
    if vram:
        used, total = vram
        status.append(f"Ekran kartı belleği {_gb(used)} / {_gb(total)} gigabayt.")
        if total and used / total > VRAM_WARN:
            found.append(Finding("uyarı", "Ekran kartı belleği neredeyse dolu; model yavaşlayabilir ya da işlemciye taşabilir."))
    models = data.get("models") or []
    active = data.get("active_model", "")
    for m in models:
        if m.get("cpu_pct", 0) > 0:
            found.append(Finding("uyarı", f"{m['name']} modelinin yüzde {m['cpu_pct']:.0f} kadarı işlemcide çalışıyor; cevaplar yavaşlar."))
    extra = [m["name"] for m in models if m["name"] != active]
    if extra and len(models) > 1:
        found.append(Finding("öneri", f"Aynı anda {len(models)} model yüklü; {', '.join(extra)} boşaltılabilir.", fix="ollama_stop"))
    env = data.get("env") or {}
    if env:
        miss = [k for k, ok in (("OLLAMA_MAX_LOADED_MODELS", ("1",)), ("OLLAMA_NUM_PARALLEL", ("1",)), ("OLLAMA_FLASH_ATTENTION", ("1",)),
                                ("OLLAMA_KV_CACHE_TYPE", ("q8_0", "q4_0"))) if env.get(k) not in ok]
        if miss:
            found.append(Finding("öneri", f"Ollama servisinde {', '.join(miss)} ayarı önerilen değerde değil (RAM.md'de komutlar var)."))
    for path, (free, _total) in (data.get("disk") or {}).items():
        name = "ev klasörünün diskinde" if path == str(Path.home()) else f"{path} diskinde"
        if free < DISK_CRIT_GB:
            found.append(Finding("sorun", f"{name.capitalize()} yalnızca {_gb(free)} gigabayt boş yer kaldı."))
        elif free < DISK_WARN_GB:
            found.append(Finding("uyarı", f"{name.capitalize()} {_gb(free)} gigabayt boş yer var; azalıyor."))
    disk = data.get("disk") or {}
    if disk:
        status.append(f"Diskte {_gb(min(v[0] for v in disk.values()))} gigabayt boş.")
    ws = data.get("ws")
    if ws and (ws["gb"] > WS_WARN_GB or ws["projects"] > WS_WARN_PROJECTS):
        found.append(Finding("öneri", f"Kod ajanı klasöründe {ws['projects']} proje, {_gb(ws['gb'])} gigabayt var; eski projeleri workspace klasöründen elle temizleyebilirsin."))
    log = data.get("log")
    if log and log["tracebacks"]:
        found.append(Finding("uyarı", f"Jarvis günlüğünün son bölümünde {log['tracebacks']} hata izi var; tail -40 data/jarvis.log ile bakabilirsin."))
    dm = data.get("daemons") or []
    if dm:
        found.append(Finding("öneri", f"{len(dm)} unutulmuş derleme süreci (Gradle/Kotlin) {_gb(sum(g for _, _, g in dm))} gigabayt bellek tutuyor; durdurulabilir.",
                             fix="daemons"))
    order = {"sorun": 0, "uyarı": 1, "öneri": 2}
    return status, sorted(found, key=lambda f: order[f.level])


# ------------------------------------------------------------------ düzeltmeler (yalnızca onaydan sonra)
def _ollama_stop(names: list[str]) -> str:
    done = []
    for n in names:
        try:
            r = subprocess.run(["ollama", "stop", n], capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0:
            done.append(n)
    return f"{', '.join(done)} bellekten boşaltıldı." if done else "Model boşaltılamadı."


def _stop_daemons(pids: list[int]) -> str:
    n = 0
    live = {pid for pid, _, _ in _daemons()}   # onay beklerken pid başka bir sürece geçmiş olabilir: yalnızca hâlâ daemon olanlar
    for pid in pids:
        if pid not in live:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            n += 1
        except OSError:
            pass
    return f"{n} derleme süreci durduruldu." if n else "Durdurulacak derleme süreci kalmadı."


def fixes(data: dict, found: list[Finding]) -> list[tuple[str, callable]]:
    out = []
    keys = {f.fix for f in found if f.fix}
    if "ollama_stop" in keys:
        names = [m["name"] for m in data.get("models") or [] if m["name"] != data.get("active_model", "")]
        out.append((f"{', '.join(names)} modelini bellekten boşaltmak", lambda: _ollama_stop(names)))
    if "daemons" in keys:
        pids = [p for p, _, _ in data.get("daemons") or []]
        out.append(("derleme süreçlerini durdurmak", lambda: _stop_daemons(pids)))
    return out


def report(data: dict) -> str:
    status, found = analyze(data)
    fx = fixes(data, found)
    n_bad = sum(f.level in ("sorun", "uyarı") for f in found)
    head = ("Sistem bakım raporu: sorun görünmüyor." if not found else
            f"Sistem bakım raporu: {n_bad} uyarı, {len(found) - n_bad} öneri." if n_bad else f"Sistem bakım raporu: {len(found)} öneri.")
    text = " ".join([head, *status, *(f.text for f in found[:6])])
    if not fx:
        return text
    return confirm.request(f"{text} İstersen {' ve '.join(d for d, _ in fx)} için hazırım; kendiliğimden bir şey yapmayacağım.",
                           lambda: " ".join(run() for _, run in fx))


def system_health() -> str:
    return report(gather())


SKILLS = [
    {"name": "system_health", "description": "Bilgisayarın bakım raporunu verir (bellek, disk, ekran kartı, modeller, günlük) ve öneri sunar.",
     "hidden": True, "run": system_health, "parameters": {"type": "object", "properties": {}}},
]
