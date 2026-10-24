"""RAM/VRAM raporu ve senaryo ölçümü (kendi bilgisayarında çalıştır).

  python ram_report.py                 # anlık durum: bileşen başına bellek, Ollama modelleri, GPU, senaryo tablosu, öneriler
  python ram_report.py --watch 180     # 180 sn boyunca 2 sn'de bir örnekler; bu sırada senaryoyu uygula
                                       # (ör. sesli sohbet + kod ajanı + tarayıcı). Sonunda tepe değerleri ve en kötü anı yazar
  python ram_report.py --watch 300 --every 1 --label "kod+tarayici"   # sıklık ve etiket (data/ram_watch.csv'ye eklenir)

Senaryo tablosundaki sayılar KABA TAHMİNDİR (±%30); çalışan bileşenler için gerçek ölçüm kullanılır. Asıl doğru sonuç --watch'tır.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import memguard

GB = 1048576.0

# Bileşen sınıflama: (ad, cmdline/ad deseni). Sırayla ilk eşleşen kazanır.
COMPONENTS = [
    ("ollama", re.compile(r"(^|/)(ollama|llama-server)(\s|$)")),  # modeli llama-server alt süreci taşır
    ("jarvis (main.py)", re.compile(r"python[\d.]*\s+.*\bmain\.py\b")),
    ("pano penceresi", re.compile(r"dashboard\.window|QtWebEngineProcess|jarvis.*--app=")),
    ("kod kutusu (bwrap)", re.compile(r"(^|/)bwrap(\s|$)")),
    ("tarayıcı (chromium)", re.compile(r"(chrom(e|ium)|headless_shell)")),
    ("telefon/ADB", re.compile(r"(^|/)adb(\s|$)")),
]

# Senaryo tahminleri (GB). ram: sistem RAM'i, vram: ekran kartı belleği. Ölçüm varsa yerine ölçüm konur.
BASE = {"os": 2.5, "jarvis": 2.0, "ollama": 1.0}      # masaüstü + Jarvis (Whisper/TTS/uyandırma) + Ollama süreci (model GPU'da)
VRAM_BASE = 6.8                                          # Whisper + gemma4:e4b, pano ekran görüntüsünde ölçülen
SCENARIOS = [
    ("A  Boşta (açık, dinliyor)", {"ram": 0.0, "vram": 0.0}),
    ("B  Sesli sohbet (STT+LLM+TTS tepe)", {"ram": 0.6, "vram": 0.3}),
    ("C  B + pano penceresi (Qt WebEngine)", {"ram": 1.3, "vram": 0.3}),
    ("D  C + tarayıcı ajanı (2 sekme)", {"ram": 2.3, "vram": 0.3}),
    ("E  C + kod ajanı (kutu tavanı 3 GB)", {"ram": 4.3, "vram": 0.3}),
    ("F  D + E (hepsi bir arada)", {"ram": 5.3, "vram": 0.3}),
    ("G  C + yedek model (qwen3:8b) da yüklendi", {"ram": 6.8, "vram": 0.3}),
    ("H  Model denemesi gpt-oss:20b (Jarvis kapalı)", {"ram": 8.0, "vram": 1.2, "replace_base": True}),
]


def verdict(used_gb: float, total_gb: float) -> str:
    r = used_gb / total_gb if total_gb else 1
    return "TAMAM" if r <= 0.70 else ("SIKI" if r <= 0.85 else "RİSKLİ")


def parse_ollama_ps(text: str) -> list[dict]:
    """`ollama ps` çıktısı: [{name, size_gb, cpu_pct, gpu_pct, ctx}]."""
    rows = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for ln in lines[1:]:
        cols = re.split(r"\s{2,}", ln.strip())
        if len(cols) < 4:
            continue
        m = re.match(r"([\d.]+)\s*(GB|MB)", cols[2])
        if not m:
            continue
        size = float(m.group(1)) / (1 if m.group(2) == "GB" else 1024)
        proc = cols[3]
        cpu = gpu = 0.0
        if "CPU/GPU" in proc:
            a = re.findall(r"([\d.]+)%", proc)
            if len(a) == 2:
                cpu, gpu = float(a[0]), float(a[1])
        elif "GPU" in proc:
            gpu = 100.0
        elif "CPU" in proc:
            cpu = 100.0
        ctx = cols[4] if len(cols) > 4 and cols[4].isdigit() else ""
        rows.append({"name": cols[0], "size_gb": size, "cpu_pct": cpu, "gpu_pct": gpu, "ctx": ctx})
    return rows


def classify(cmdline: str, comm: str) -> str:
    probe = cmdline or comm
    for name, rx in COMPONENTS:
        if rx.search(probe) or rx.search(comm):
            return name
    return "diğer"


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


def process_table(proc: Path = Path("/proc"), others: dict | None = None) -> dict[str, dict]:
    """{bileşen: {gb, swap, n}}. gb: PSS (okunabiliyorsa) ya da RSS = şu an RAM'de olan; swap: swap'a atılmış kısım (VmSwap).
    Boşta bir süreç swap'a atılmış olabilir; yalnız RSS'e bakmak bileşenin gerçek boyutunu olduğundan küçük gösterir."""
    out: dict[str, dict] = {}
    try:
        pids = [d for d in proc.iterdir() if d.name.isdigit()]
    except OSError:
        return out
    for d in pids:
        status = _read(d / "status")
        if not status:
            continue
        comm, rss, swp = "", 0, 0
        for ln in status.splitlines():
            if ln.startswith("Name:"):
                comm = ln.split(None, 1)[1].strip()
            elif ln.startswith(("VmRSS:", "VmSwap:")):
                p = ln.split()
                val = int(p[1]) if len(p) > 1 and p[1].isdigit() else 0
                if ln.startswith("VmRSS:"):
                    rss = val
                else:
                    swp = val
        if not rss and not swp:
            continue
        pss = 0
        m = re.search(r"^Pss:\s+(\d+)", _read(d / "smaps_rollup"), re.M)
        if m:
            pss = int(m.group(1))
        cmd = _read(d / "cmdline").replace("\0", " ").strip()
        comp = classify(cmd, comm)
        e = out.setdefault(comp, {"gb": 0.0, "swap": 0.0, "n": 0})
        e["gb"] += (pss or rss) / GB
        e["swap"] += swp / GB
        e["n"] += 1
        if others is not None and comp == "diğer":  # Jarvis dışı uygulamalar: ada göre topla
            others[comm] = others.get(comm, 0.0) + ((pss or rss) + swp) / GB
    return out


def gpu_mem() -> tuple[float, float] | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5, check=False)
        a, b = r.stdout.strip().splitlines()[0].split(",")
        return float(a) / 1024, float(b) / 1024
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def ollama_ps() -> list[dict]:
    if not shutil.which("ollama"):
        return []
    try:
        r = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=8, check=False)
        return parse_ollama_ps(r.stdout)
    except (OSError, subprocess.SubprocessError):
        return []


def ollama_env() -> dict[str, str]:
    """systemd servisindeki OLLAMA_* ayarları (okunamazsa boş)."""
    if not shutil.which("systemctl"):
        return {}
    try:
        r = subprocess.run(["systemctl", "show", "ollama", "-p", "Environment"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    return dict(re.findall(r"(OLLAMA_[A-Z_]+)=([^\s\"]+)", r.stdout))


def scenario_table(total_gb: float, vram_total: float | None, measured: dict[str, float]) -> list[tuple[str, float, float, str]]:
    """measured: bileşen -> RAM+swap GB. Ölçüm yalnızca tahmini artırır (GPU'ya taşınmış ya da swap'ta bekleyen
    bellek RSS'i olduğundan küçük gösterir; küçük ölçüm tahmini düşürmemeli)."""
    base = dict(BASE)
    for key, comp in (("jarvis", "jarvis (main.py)"), ("ollama", "ollama"), ("os", "diğer")):
        base[key] = max(base[key], measured.get(comp, 0.0))  # "os": masaüstü + geliştirme araçları + tarayıcı vb. (Jarvis dışı her şey)
    rows = []
    for name, d in SCENARIOS:
        if d.get("replace_base"):
            ram = base["os"] + base["ollama"] + d["ram"] - 1.0
            vram = d["vram"] + (vram_total or 8.0) * 0.9
            v = verdict(ram, total_gb)
            v = "YAVAŞ (model RAM'e taşar)" if v == "TAMAM" else v
        else:
            ram = sum(base.values()) + d["ram"]
            vram = VRAM_BASE + d["vram"]
            v = verdict(ram, total_gb)
            if vram_total and vram > vram_total * 0.97:
                v = "RİSKLİ"
        rows.append((name, ram, vram, v))
    return rows


def advice(mi: dict, env: dict[str, str], ps: list[dict], psi: float | None, others: dict | None = None) -> list[str]:
    out = []
    big = sorted((others or {}).items(), key=lambda kv: -kv[1])[:5]
    if sum((others or {}).values()) > 4.0:
        out.append(f"Jarvis dışı uygulamalar {sum(others.values()):.1f} GB kullanıyor (en büyükler: {', '.join(f'{n} {g:.1f}' for n, g in big)}). "
                   "Kod ajanı/tarayıcı gibi ağır işlerden önce gereksiz olanları kapatmak en büyük kazanç.")
    if mi["swap_total"] < 0.5:
        out.append("Swap yok/çok az: bellek bitince çekirdek rastgele süreç öldürür ve sistem donar. 4 GB swap dosyası ekle (RAM.md'de komutlar) "
                   "ve `sudo apt install earlyoom` kur.")
    if env.get("OLLAMA_MAX_LOADED_MODELS") not in ("1", "2"):
        out.append("OLLAMA_MAX_LOADED_MODELS ayarsız: yedek model devreye girince iki model aynı anda bellekte kalabilir. 1 yap (RAM.md).")
    if env.get("OLLAMA_NUM_PARALLEL") not in ("1",):
        out.append("OLLAMA_NUM_PARALLEL=1 yap: tek kullanıcı için paralel istek KV önbelleğini boşuna büyütür.")
    if env.get("OLLAMA_KV_CACHE_TYPE") not in ("q8_0", "q4_0") or env.get("OLLAMA_FLASH_ATTENTION") != "1":
        out.append("OLLAMA_FLASH_ATTENTION=1 ve OLLAMA_KV_CACHE_TYPE=q8_0: KV önbelleği yaklaşık yarıya iner (uzun bağlamda VRAM/RAM kazancı).")
    st = mi["swap_total"]
    if st > 0.5 and (st - mi["swap_free"]) / st > 0.5:
        used = st - mi["swap_free"]
        out.append(f"Swap %{used / st * 100:.0f} dolu ({used:.1f}/{st:.1f} GB): geçmişte bellek baskısı yaşandı, atılan sayfalar dokunulmadıkça geri gelmez. "
                   "RAM şu an boşsa `sudo swapoff -a && sudo swapon -a` ile boşaltılır (bir süre sürer); hemen yeniden dolarsa gerçek bir bellek sıkışıklığı var, "
                   "`--watch` ile bak.")
    for m in ps:
        if m["cpu_pct"] > 0:
            out.append(f"{m['name']} kısmen CPU/RAM'de çalışıyor (%{m['cpu_pct']:.0f}): VRAM yetmiyor, yanıt yavaşlar ve RAM şişer. "
                       "Daha küçük model ya da daha kısa bağlam (JARVIS_NUM_CTX=4096) düşün.")
    if len(ps) > 1:
        out.append(f"Aynı anda {len(ps)} model yüklü ({', '.join(m['name'] for m in ps)}): `ollama stop <ad>` ile birini boşalt.")
    if psi is not None and psi >= memguard.PSI_LOW:
        out.append(f"Bellek baskısı yüksek (PSI avg10={psi:.0f}%): sistem şu an bellek yüzünden bekliyor.")
    if not out:
        out.append("Belirgin bir sorun görünmüyor.")
    return out


def report() -> int:
    mi = memguard.read_meminfo()
    psi = memguard.read_psi()
    others: dict = {}
    comps = process_table(others=others)
    ps = ollama_ps()
    env = ollama_env()
    gpu = gpu_mem()
    print(f"RAM   : {mi['total'] - mi['available']:.1f} / {mi['total']:.1f} GB kullanımda, {mi['available']:.1f} GB kullanılabilir"
          f"   Swap: {mi['swap_total'] - mi['swap_free']:.1f} / {mi['swap_total']:.1f} GB   PSI: {'yok' if psi is None else f'{psi:.1f}%'}")
    if gpu:
        print(f"VRAM  : {gpu[0]:.1f} / {gpu[1]:.1f} GB")
    print(f"Düzey : {memguard.level(mi, psi)} (uyarı eşiği {memguard.LOW_GB} GB, kritik {memguard.CRIT_GB} GB boş)")
    print("\nBileşenler (GB):  RAM'de   swap'ta")
    measured = {}
    for name, e in sorted(comps.items(), key=lambda kv: -(kv[1]["gb"] + kv[1]["swap"])):
        print(f"  {name:<24}{e['gb']:6.2f}   {e['swap']:6.2f}   ({e['n']} süreç)")
        measured[name] = e["gb"] + e["swap"]
    top_others = sorted(others.items(), key=lambda kv: -kv[1])[:6]
    if top_others:
        print("  'diğer' içinde en büyükler: " + ", ".join(f"{n} {g:.1f}" for n, g in top_others))
    print("\nOllama modelleri:" + ("" if ps else " (yüklü model yok ya da ollama bulunamadı)"))
    for m in ps:
        where = "GPU" if m["cpu_pct"] == 0 else f"%{m['cpu_pct']:.0f} CPU / %{m['gpu_pct']:.0f} GPU"
        print(f"  {m['name']:<22}{m['size_gb']:5.1f} GB   {where}   bağlam {m['ctx'] or '?'}")
    if ps and gpu and sum(m["size_gb"] for m in ps) < 1.0 and gpu[0] > 2.0:
        print("  (Ollama'nın llamacpp çalıştırıcısı boyutu eksik raporluyor; gerçek bellek: yukarıdaki 'ollama' satırı + VRAM)")
    if env:
        print("Ollama ayarları: " + ", ".join(f"{k}={v}" for k, v in sorted(env.items())))
    print("\nSenaryo tahmini (kaba; gerçek için --watch):")
    print(f"  {'senaryo':<46}{'RAM':>7}{'VRAM':>7}  sonuç")
    for name, ram, vram, v in scenario_table(mi["total"], gpu[1] if gpu else None, measured):
        print(f"  {name:<46}{ram:6.1f}G{vram:6.1f}G  {v}")
    print("\nÖneriler:")
    for a in advice(mi, env, ps, psi, others):
        print(f"  - {a}")
    return 0


def watch(seconds: int, every: float, label: str) -> int:
    path = None
    try:
        from skills import _store  # noqa: PLC0415
        path = _store.path("ram_watch.csv")
    except Exception:  # noqa: BLE001
        pass
    print(f"{seconds} sn izleniyor (her {every:g} sn). Şimdi senaryoyu uygula; durdurmak için Ctrl+C.\n")
    rows = []
    t_end = time.time() + seconds
    worst = None
    try:
        while time.time() < t_end:
            mi = memguard.read_meminfo()
            psi = memguard.read_psi() or 0.0
            comps = process_table()
            gpu = gpu_mem()
            row = {"t": time.strftime("%H:%M:%S"), "used": mi["total"] - mi["available"], "avail": mi["available"],
                   "swap_used": mi["swap_total"] - mi["swap_free"], "psi": psi, "vram": gpu[0] if gpu else 0.0,
                   **{k: v["gb"] for k, v in comps.items()}}
            rows.append(row)
            if worst is None or row["avail"] < worst["avail"]:
                worst = {**row, "top": memguard.top_consumers(5)}
            print(f"\r{row['t']}  kullanılabilir {row['avail']:5.1f} GB  swap {row['swap_used']:4.1f}  PSI {psi:4.1f}%  VRAM {row['vram']:4.1f}   ", end="", flush=True)
            time.sleep(every)
    except KeyboardInterrupt:
        pass
    print("\n")
    if not rows:
        return 1
    names = sorted({k for r in rows for k in r if k not in ("t", "used", "avail", "swap_used", "psi", "vram")})
    if path:
        new = not Path(path).exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["etiket", "saat", "kullanilan_gb", "bos_gb", "swap_gb", "psi", "vram_gb", *names])
            for r in rows:
                w.writerow([label, r["t"], f"{r['used']:.2f}", f"{r['avail']:.2f}", f"{r['swap_used']:.2f}", f"{r['psi']:.1f}", f"{r['vram']:.2f}",
                            *[f"{r.get(n, 0):.2f}" for n in names]])
    mx = lambda k: max(r.get(k, 0) for r in rows)  # noqa: E731
    mi = memguard.read_meminfo()
    print(f"ÖZET{(' [' + label + ']') if label else ''}: {len(rows)} örnek")
    print(f"  en az boş bellek : {worst['avail']:.1f} GB (saat {worst['t']})   en çok kullanım: {mx('used'):.1f} / {mi['total']:.1f} GB")
    print(f"  en yüksek swap   : {mx('swap_used'):.1f} GB   en yüksek PSI: {mx('psi'):.1f}%   en yüksek VRAM: {mx('vram'):.1f} GB")
    print("  bileşen tepeleri : " + ", ".join(f"{n} {mx(n):.1f}" for n in names if mx(n) >= 0.1))
    print("  en kötü anda en çok kullananlar: " + ", ".join(f"{n} {g:.1f}" for n, g in worst["top"]))
    lv = memguard.level({"available": worst["avail"]}, mx("psi"))
    print(f"  değerlendirme    : {'RİSKLİ — bellek eşiğin altına indi' if lv == 'critical' else 'SIKI — uyarı eşiğine yaklaştı' if lv == 'low' else 'TAMAM — yeterli pay kaldı'}")
    if path:
        print(f"  ayrıntı          : {path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--watch", type=int, default=0, metavar="SN")
    p.add_argument("--every", type=float, default=2.0)
    p.add_argument("--label", default="")
    a = p.parse_args()
    if a.watch:
        return watch(a.watch, max(0.5, a.every), a.label)
    return report()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
