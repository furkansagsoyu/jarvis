"""Sistem bakım ajanı testleri: değerlendirme kuralları, onay kapısı (kendi başına değişiklik yok), düzeltmeler, daemon taraması.
Gerçek sistem komutu çalıştırılmaz (ollama/os.kill sahte)."""
import os
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("JARVIS_DATA", tempfile.mkdtemp())
try:
    import ollama  # noqa: F401
except ImportError:
    sys.modules["ollama"] = types.ModuleType("ollama")
from skills import _confirm as confirm  # noqa: E402
from skills import maintenance as M  # noqa: E402

bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


ENV_OK = {"OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}


def healthy(**kw):
    d = {"mem": {"total": 15.3, "available": 8.0, "swap_total": 4.0, "swap_free": 3.5, "psi": 0.0}, "top": [("brave", 2.1)],
         "vram": (4.6, 8.0), "models": [{"name": "gemma4:e4b", "cpu_pct": 0.0}], "active_model": "gemma4:e4b", "env": dict(ENV_OK),
         "disk": {str(Path.home()): (180.0, 390.0)}, "ws": {"projects": 3, "gb": 0.01}, "log": {"tracebacks": 0}, "daemons": []}
    d.update(kw)
    return d


status, found = M.analyze(healthy())
check("sağlıklı sistem: bulgu yok, durum cümleleri var", not found and any("8,0 gigabayt boş" in s for s in status), str(found))
confirm.cancel()
out = M.report(healthy())
check("sağlıklı rapor: 'sorun görünmüyor', onay sorulmaz", "sorun görünmüyor" in out and not confirm.has_pending())

_, found = M.analyze(healthy(mem={"total": 15.3, "available": 0.5, "swap_total": 4.0, "swap_free": 3.9, "psi": 50.0}, top=[("brave", 6.2), ("code", 3.0)]))
check("bellek kritik: 'sorun', en çok kullananlar söylenir, ilk sırada", found[0].level == "sorun" and "brave 6,2" in found[0].text)
_, found = M.analyze(healthy(mem={"total": 15.3, "available": 6.0, "swap_total": 0.0, "swap_free": 0.0, "psi": 0.0}))
check("swap yok: öneri (RAM.md)", any("Swap yok" in f.text and f.level == "öneri" for f in found))
_, found = M.analyze(healthy(mem={"total": 15.3, "available": 6.0, "swap_total": 4.0, "swap_free": 1.0, "psi": 0.0}))
check("swap %75 dolu: öneri", any("Swap yüzde 75" in f.text for f in found))
_, found = M.analyze(healthy(vram=(7.9, 8.0), models=[{"name": "gemma4:e4b", "cpu_pct": 21.0}]))
check("VRAM dolu ve model kısmen CPU'da: uyarılar", sum(f.level == "uyarı" for f in found) == 2)
_, found = M.analyze(healthy(env={"OLLAMA_NUM_PARALLEL": "4"}))
check("Ollama ayarları eksik: tek öneri, eksikler adıyla", len(found) == 1 and "OLLAMA_MAX_LOADED_MODELS" in found[0].text and "OLLAMA_NUM_PARALLEL" in found[0].text)
_, found = M.analyze(healthy(disk={str(Path.home()): (3.0, 390.0)}))
check("disk 3 GB: sorun", found and found[0].level == "sorun" and "3,0 gigabayt" in found[0].text)
_, found = M.analyze(healthy(ws={"projects": 45, "gb": 0.2}, log={"tracebacks": 2}))
check("workspace kalabalık: elle temizleme önerisi (otomatik silme yok); günlükte hata izi uyarısı",
      any("45 proje" in f.text and not f.fix for f in found) and any("2 hata izi" in f.text for f in found))

# düzeltmeler: yalnızca onaydan sonra, yalnızca güvenli iki iş
calls = []
real_run, real_kill, real_daemons = M.subprocess.run, M.os.kill, M._daemons
M.subprocess.run = lambda argv, **kw: calls.append(("run", argv)) or types.SimpleNamespace(returncode=0, stdout="", stderr="")
M.os.kill = lambda pid, sig: calls.append(("kill", pid, sig))
M._daemons = lambda proc=None: [(4242, "GradleDaemon", 1.2), (4343, "KotlinCompileDaemon", 0.4)]
try:
    data = healthy(models=[{"name": "gemma4:e4b", "cpu_pct": 0.0}, {"name": "qwen3:8b", "cpu_pct": 0.0}],
                   daemons=[(4242, "GradleDaemon", 1.2), (4343, "KotlinCompileDaemon", 0.4), (999, "GradleDaemon", 0.1)])
    confirm.cancel()
    out = M.report(data)
    check("düzeltilebilir bulgu: rapor + onay sorusu, henüz HİÇBİR şey yapılmadı",
          confirm.has_pending() and not calls and "qwen3:8b modelini bellekten boşaltmak" in out and "derleme süreçlerini durdurmak" in out
          and out.endswith("Onaylıyor musun?"), out)
    check("etkin model (gemma4:e4b) boşaltma listesinde yok", "gemma4:e4b modelini" not in out)
    res = confirm.approve()
    check("onaydan sonra: yalnızca fazladan model durdurulur", ("run", ["ollama", "stop", "qwen3:8b"]) in calls and not any(c[0] == "run" and "gemma4:e4b" in c[1] for c in calls), str(calls))
    check("onaydan sonra: yalnızca hâlâ daemon olan süreçlere SIGTERM (pid değişmişse dokunulmaz)",
          [c for c in calls if c[0] == "kill"] == [("kill", 4242, M.signal.SIGTERM), ("kill", 4343, M.signal.SIGTERM)], str(calls))
    check("sonuç cümlesi", "qwen3:8b bellekten boşaltıldı" in res and "2 derleme süreci durduruldu" in res, res)
    calls.clear()
    confirm.cancel()
    M.report(data)
    confirm.cancel()  # kullanıcı vazgeçti / süre doldu
    check("onay yoksa hiçbir şey yapılmaz", not calls)
finally:
    M.subprocess.run, M.os.kill, M._daemons = real_run, real_kill, real_daemons
    confirm.cancel()

# daemon taraması: sahte /proc
proc = Path(tempfile.mkdtemp())
for pid, cmd, rss in ((101, b"java\0-cp\0x\0org.gradle.launcher.daemon.bootstrap.GradleDaemon\0", 1048576), (102, b"python\0main.py\0", 500000),
                      (103, b"java\0org.jetbrains.kotlin.daemon.KotlinCompileDaemon\0", 524288)):
    (proc / str(pid)).mkdir()
    (proc / str(pid) / "cmdline").write_bytes(cmd)
    (proc / str(pid) / "status").write_text(f"Name:\tjava\nVmRSS:\t{rss} kB\n")
(proc / "self").mkdir()
got = sorted(M._daemons(proc))
check("daemon taraması: Gradle ve Kotlin bulunur, diğer süreçler değil", got == [(101, "GradleDaemon", 1.0), (103, "KotlinCompileDaemon", 0.5)], str(got))

# skill kaydı
sk = {s["name"]: s for s in M.SKILLS}
check("system_health gizli araç (hızlı yol), parametresiz", sk["system_health"].get("hidden") and not sk["system_health"]["parameters"]["properties"])
import brain as B  # noqa: E402
check("uzaktan kapalı (REMOTE_BLOCKED)", "system_health" in B.REMOTE_BLOCKED)
import team as T  # noqa: E402
check("ekip rolü 'bakim' yalnızca yerel, aracı yalnızca system_health", T.ROLES["bakim"].private and not T.ROLES["bakim"].cloud and T.ROLES["bakim"].tools == ("system_health",))

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
