"""Bellek koruması ve RAM raporu testleri (sahte /proc ve saat ile)."""
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # depo kökü: core/, voice/, desktop/... paketleri

import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
from core import memguard  # noqa: E402
from tools import ram_report as rr  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


MEMINFO = """MemTotal:       15728640 kB
MemFree:         1048576 kB
MemAvailable:    8388608 kB
SwapTotal:             0 kB
SwapFree:              0 kB
"""
mi = memguard.read_meminfo(MEMINFO)
check("meminfo: GB'ye çevirir", abs(mi["total"] - 15.0) < 0.01 and abs(mi["available"] - 8.0) < 0.01 and mi["swap_total"] == 0)
check("psi okunur", memguard.read_psi("some avg10=12.34 avg60=1.00 avg300=0.50 total=123\nfull avg10=3.00 avg60=0 avg300=0 total=1") == 12.34)
check("psi bozuksa None", memguard.read_psi("saçma") is None)

# ---------------------------------------------------------------- düzey
mk = lambda a: {"available": a, "total": 15.0, "swap_total": 0, "swap_free": 0}  # noqa: E731
check("düzey: bol bellek ok", memguard.level(mk(6.0), 0.0, 1.5, 0.8) == "ok")
check("düzey: 1,2 GB low", memguard.level(mk(1.2), 0.0, 1.5, 0.8) == "low")
check("düzey: 0,5 GB critical", memguard.level(mk(0.5), 0.0, 1.5, 0.8) == "critical")
check("düzey: bellek bol ama PSI yüksek (swap/thrash) low/critical", memguard.level(mk(6.0), 20.0, 1.5, 0.8) == "low" and memguard.level(mk(6.0), 55.0, 1.5, 0.8) == "critical")

# ---------------------------------------------------------------- need
check("need: yeterliyse boş", memguard.need("tarayıcı", 1.0, mk(4.0)) == "")
msg = memguard.need("kod çalıştırmak", 1.0, mk(1.3))
check("need: yetersizse iş reddedilir, neden ve sayılar söylenir", "kod çalıştırmak" in msg and "1,3" in msg and "yetersiz" in msg, msg)
check("need: tam sınırda (gb + kritik eşik) kabul", memguard.need("x", 1.0, mk(1.0 + memguard.CRIT_GB)) == "")

# ---------------------------------------------------------------- en çok kullananlar (sahte /proc)
fake = Path(tempfile.mkdtemp())
for pid, name, rss in ((101, "ollama", 4_000_000), (102, "ollama", 2_000_000), (103, "chrome", 1_000_000), (104, "chrome", 500_000), (105, "bash", 4000), (106, "kthreadd", 0)):
    d = fake / str(pid)
    d.mkdir()
    (d / "status").write_text(f"Name:\t{name}\nVmRSS:\t{rss} kB\n")
(fake / "self").mkdir()
top = memguard.top_consumers(2, proc=fake)
check("top_consumers: aynı adlılar toplanır, büyükten küçüğe", [n for n, _ in top] == ["ollama", "chrome"] and abs(top[0][1] - 6_000_000 / memguard.GB) < 0.01, str(top))

# ---------------------------------------------------------------- Monitor
now = [0.0]
said = []
state = {"level": "low", "available": 1.2}
mon = memguard.Monitor(said.append, cooldown=600, clock=lambda: now[0], sample=lambda: dict(state), top=lambda n: [("ollama", 6.0), ("chrome", 1.5)])
m1 = mon.check()
check("Monitor: düşünce bir kez uyarır, kullananları sayar", len(said) == 1 and "Bellek azaldı" in said[0] and "ollama 6,0" in said[0], str(said))
mon.check()
now[0] += 30
mon.check()
check("Monitor: aynı düzeyde tekrar etmez", len(said) == 1)
state.update(level="critical", available=0.6)
mon.check()
check("Monitor: low -> critical'e kötüleşince hemen yeniden uyarır", len(said) == 2 and "kritik" in said[1])
mon.check()
check("Monitor: kritikte de tekrar etmez", len(said) == 2)
state.update(level="ok", available=2.0)
mon.check()
state.update(level="low", available=1.2)
now[0] += 60
mon.check()
check("Monitor: eşik civarında titreşimde (histerezis) yeniden uyarmaz", len(said) == 2)
state.update(level="ok", available=3.0)
mon.check()
now[0] += 700
state.update(level="low", available=1.2)
mon.check()
check("Monitor: gerçekten düzelip (>2,25 GB) sonra yine düşünce, bekleme süresi dolmuşsa uyarır", len(said) == 3)
state.update(level="ok", available=3.0)
mon.check()
now[0] += 10
state.update(level="low", available=1.2)
mon.check()
check("Monitor: düzelip kısa sürede tekrar düşse bekleme süresi içinde susar", len(said) == 3)
bad_mon = memguard.Monitor(lambda m: (_ for _ in ()).throw(RuntimeError("tts")), sample=lambda: {"level": "low", "available": 1.0}, top=lambda n: [])
try:
    bad_mon.start()
    check("Monitor: iş parçacığı başlatılır (hata programı düşürmez)", True)
finally:
    bad_mon.stop()

# ---------------------------------------------------------------- araç entegrasyonu
from skills import codeagent  # noqa: E402

real = memguard.read_meminfo
memguard.read_meminfo = lambda text=None: {"total": 15.0, "available": 0.9, "swap_total": 0.0, "swap_free": 0.0}
codeagent._project = Path(tempfile.mkdtemp())
r = codeagent.code_run("python3 -c 'print(1)'")
check("kod çalıştırma: bellek azsa BAŞLAMAZ ve nedenini söyler", r.startswith("Hata:") and "Bellek yetersiz" in r, r)
import skills.browser as br  # noqa: E402

w = br._Worker()
import threading  # noqa: E402

ev = threading.Event()
w._run(ev)
check("tarayıcı: bellek azsa açılmaz, hata kaydedilir", ev.is_set() and isinstance(w.error, MemoryError) and "Bellek yetersiz" in str(w.error), str(w.error))
memguard.read_meminfo = real

# ---------------------------------------------------------------- ram_report
PS = """NAME            ID              SIZE      PROCESSOR          CONTEXT    UNTIL
gemma4:e4b      abc123          9.6 GB    100% GPU           4096       29 minutes from now
gpt-oss:20b     def456          14 GB     48%/52% CPU/GPU    8192       4 minutes from now
tiny:1b         ghi789          700 MB    100% CPU           2048       Forever
"""
rows = rr.parse_ollama_ps(PS)
check("ollama ps: üç satır ayrıştırılır", [r["name"] for r in rows] == ["gemma4:e4b", "gpt-oss:20b", "tiny:1b"], str(rows))
check("ollama ps: GPU/CPU payları ve boyut (MB->GB)", rows[0]["gpu_pct"] == 100 and rows[1]["cpu_pct"] == 48 and rows[1]["gpu_pct"] == 52 and rows[2]["cpu_pct"] == 100 and abs(rows[2]["size_gb"] - 700 / 1024) < 0.01)
check("ollama ps: boş çıktı boş liste", rr.parse_ollama_ps("") == [] and rr.parse_ollama_ps("NAME ID SIZE PROCESSOR CONTEXT UNTIL\n") == [])
check("sınıflama: ollama/jarvis/pano/kutu/tarayıcı", [rr.classify(c, n) for c, n in (
    ("/usr/local/bin/ollama serve", "ollama"), ("/usr/local/lib/ollama/llama-server --model x --port 1", "llama-server"),
    ("/home/f/.conda/envs/freya/bin/python /home/f/jarvis_v2/main.py --dash --telegram", "python"),
    ("python -m dashboard.window http://127.0.0.1:8765/?t=x", "python"), ("/usr/bin/bwrap --unshare-all", "bwrap"),
    ("/usr/lib/chromium/chromium --headless", "chromium"), ("/usr/bin/vim", "vim"))] ==
    ["ollama", "ollama", "jarvis (main.py)", "pano penceresi", "kod kutusu (bwrap)", "tarayıcı (chromium)", "diğer"])
for pid, name, cmd, rss, pss in ((201, "ollama", "/usr/local/bin/ollama serve", 500_000, 0), (202, "ollama", "/usr/local/bin/ollama runner", 3_000_000, 2_800_000),
                                 (203, "python", "python /x/main.py --dash", 2_000_000, 1_500_000)):
    d = fake / str(pid)
    d.mkdir(exist_ok=True)
    (d / "status").write_text(f"Name:\t{name}\nVmRSS:\t{rss} kB\nVmSwap:\t{1_000_000 if pid == 203 else 0} kB\n")
    (d / "cmdline").write_text(cmd.replace(" ", "\0"))
    if pss:
        (d / "smaps_rollup").write_text(f"Rss: {rss} kB\nPss: {pss} kB\n")
tab = rr.process_table(proc=fake)
exp_ollama = (4_000_000 + 2_000_000 + 500_000 + 2_800_000) / memguard.GB  # 101,102 (yalnız RSS) + 201 (RSS) + 202 (PSS)
check("process_table: PSS varsa PSS, yoksa RSS; bileşene toplanır", abs(tab["ollama"]["gb"] - exp_ollama) < 0.01 and tab["ollama"]["n"] == 4
      and abs(tab["jarvis (main.py)"]["gb"] - 1_500_000 / memguard.GB) < 0.01, str(tab))
oth = {}
rr.process_table(proc=fake, others=oth)
check("'diğer' bileşeni ada göre toplanır (vim 4 MB vb.)", "python" not in oth and all(v >= 0 for v in oth.values()))
tbl4 = rr.scenario_table(15.0, 8.0, {"diğer": 7.5, "jarvis (main.py)": 1.1, "ollama": 2.3})
check("Jarvis dışı yük büyükse (7,5 GB) senaryolar buna göre kötüleşir (A>=11 GB)", tbl4[0][1] >= 11.0 and tbl4[0][3] == "SIKI", str(tbl4[0]))
adv4 = rr.advice({"swap_total": 4.0, "swap_free": 4.0, "total": 15, "available": 8}, {}, [], 0.0, {"firefox": 3.1, "java": 2.0, "code": 1.5})
check("öneri: Jarvis dışı >4 GB ise büyükleri sayar", any("Jarvis dışı" in a and "firefox 3.1" in a for a in adv4), str(adv4))
check("verdict eşikleri", rr.verdict(5, 15) == "TAMAM" and rr.verdict(11, 15) == "SIKI" and rr.verdict(13.5, 15) == "RİSKLİ")
tbl = rr.scenario_table(15.0, 8.0, {})
names = [r[0][0] for r in tbl]
check("senaryo tablosu A..H, yük arttıkça RAM artar (H hariç)", names == list("ABCDEFGH") and all(tbl[i][1] < tbl[i + 1][1] for i in range(6)))
check("15 GB'ta boşta/sesli sohbet TAMAM, hepsi bir arada ve yedek model SIKI ya da kötüsü",
      tbl[0][3] == "TAMAM" and tbl[2][3] == "TAMAM" and tbl[5][3] in ("SIKI", "RİSKLİ") and tbl[6][3] in ("SIKI", "RİSKLİ"), str(tbl))
tbl2 = rr.scenario_table(15.0, 8.0, {"jarvis (main.py)": 4.0})
check("ölçülen Jarvis belleği tahminden BÜYÜKSE tahmin yükselir", tbl2[0][1] > tbl[0][1] + 1.9)
tbl3 = rr.scenario_table(15.0, 8.0, {"jarvis (main.py)": 0.3, "ollama": 0.03})
check("küçük ölçüm (GPU'ya taşınmış/swap'ta) tahmini DÜŞÜRMEZ", tbl3[0][1] == tbl[0][1])
check("tabloda swap'taki bellek Jarvis'e eklenir (RAM+swap)", abs(tab["jarvis (main.py)"]["swap"] - 1_000_000 / memguard.GB) < 0.01)
check("gpt-oss:20b satırı 'riskli' değil 'yavaş' (RAM yeterliyse)", "YAVAŞ" in tbl[7][3], tbl[7][3])
adv = rr.advice({"swap_total": 0.0, "swap_free": 0.0, "total": 15, "available": 8}, {}, rows, 30.0)
check("öneriler: swap yok, Ollama ayarları, CPU'ya taşan model, çoklu model, yüksek PSI", all(any(k in a for a in adv) for k in ("Swap", "OLLAMA_MAX_LOADED_MODELS", "OLLAMA_NUM_PARALLEL", "FLASH", "gpt-oss:20b kısmen", "3 model", "PSI")), str(adv))
adv3 = rr.advice({"swap_total": 4.0, "swap_free": 0.2, "total": 15, "available": 10}, {}, [], 0.0)
check("öneri: swap %95 doluyken swapoff/swapon tarifi", any("Swap %95 dolu" in a and "swapoff" in a for a in adv3), str(adv3))
adv2 = rr.advice({"swap_total": 4.0, "swap_free": 4.0, "total": 15, "available": 8},
                 {"OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}, rows[:1], 1.0)
check("her şey ayarlıysa sorun yok der", adv2 == ["Belirgin bir sorun görünmüyor."], str(adv2))
check("rapor betiği çökmeden çalışır", rr.report() == 0)

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
