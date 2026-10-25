"""Güvenlik sertleştirme testleri: data/ izinleri, kullanıcıya özel kilit yolu, uzaktan kapalı araçlar,
kod ajanı kaynak/bellek katmanları, tehlikeli çağrıların koda geri sızmaması (AST taraması)."""
import ast
import os
import stat
import sys
import tempfile
import types
from pathlib import Path

DATA = tempfile.mkdtemp()
os.environ["JARVIS_DATA"] = DATA
sys.modules.setdefault("ollama", types.ModuleType("ollama"))
from skills import _store, codeagent  # noqa: E402

HERE = Path(__file__).resolve().parent
bad = 0


def check(name, cond, extra=""):
    global bad
    print(("OK   " if cond else "HATA ") + name + (f"  {extra}" if extra and not cond else ""))
    bad += (not cond)


# ---------------------------------------------------------------- data/ izinleri
os.chmod(DATA, 0o755)
_store._secured = False
_store.save("secret.json", {"token": "x"})
mode = lambda p: stat.S_IMODE(os.stat(p).st_mode)  # noqa: E731
check("data/ klasörü yalnızca sahibine açık (0700)", mode(DATA) == 0o700, oct(mode(DATA)))
check("kaydedilen dosya yalnızca sahibine açık (0600)", mode(Path(DATA) / "secret.json") == 0o600, oct(mode(Path(DATA) / "secret.json")))
_store.save("secret.json", {"token": "y"})
check("üzerine yazınca izin korunur, içerik güncellenir", mode(Path(DATA) / "secret.json") == 0o600 and _store.load("secret.json", {})["token"] == "y")
check("data/.gitignore her şeyi git dışında tutar", (Path(DATA) / ".gitignore").read_text().strip() == "*")
check("yarım yazılmış .tmp dosyası kalmaz", not list(Path(DATA).glob("*.tmp")))

# ---------------------------------------------------------------- kilit/pid dosyaları
xdg = tempfile.mkdtemp()
os.environ["XDG_RUNTIME_DIR"] = xdg
check("kilit yolu $XDG_RUNTIME_DIR altında", _store.runtime_path("jarvis.lock") == Path(xdg) / "jarvis.lock")
del os.environ["XDG_RUNTIME_DIR"]
p = _store.runtime_path("jarvis.lock")
check("XDG yoksa /tmp/jarvis-<uid> (0700)", p.parent.name == f"jarvis-{os.getuid()}" and mode(p.parent) == 0o700, str(p))
os.chmod(p.parent, 0o777)
_store.runtime_path("x")
check("gevşek izinli klasör yeniden 0700 yapılır", mode(p.parent) == 0o700)
real_uid = os.getuid
os.getuid = lambda: real_uid() + 1  # başka kullanıcıya ait klasör simülasyonu
try:
    d = Path(tempfile.gettempdir()) / f"jarvis-{os.getuid()}"
    d.mkdir(mode=0o700, exist_ok=True)
    d.chmod(0o700)
    try:
        # klasör gerçekte bu kullanıcıya ait; getuid sahte olduğundan "başkasının" görünür
        _store.runtime_path("x")
        check("başkasına ait klasör reddedilir", False)
    except PermissionError:
        check("başkasına ait klasör reddedilir", True)
finally:
    os.getuid = real_uid
    try:
        d.rmdir()
    except OSError:
        pass
src = {n: (HERE / n).read_text(encoding="utf-8") for n in ("main.py", "ui.py", "app.py", "dashboard/window.py")}
check("kodda sabit /tmp kilit/pid yolu kalmadı", not any("/tmp/jarvis" in v for v in src.values()), str([k for k, v in src.items() if "/tmp/jarvis" in v]))
import app  # noqa: E402

check("app.py ve main.py aynı kilit yolunu kullanır", app.LOCK == str(_store.runtime_path("jarvis.lock")))

# ---------------------------------------------------------------- uzaktan kapalı araçlar
import brain as B  # noqa: E402

need = {"move_file", "trash_file", "undo_last_action", "phone_call", "phone_hangup", "phone_ring", "code_run", "code_write", "read_file",
        "recall", "look_at_screen", "look_at_camera", "mouse_click", "keyboard_type", "press_key", "browser_open", "contact_add"}
check("uzaktan kapalı liste: dosya, telefon, kod, ekran/kamera, fare/klavye, tarayıcı", need <= B.REMOTE_BLOCKED, str(need - B.REMOTE_BLOCKED))
br = B.Brain.__new__(B.Brain)
called = []
br.tools = {"trash_file": ({}, lambda **k: called.append(k) or "silindi"), "get_time": ({}, lambda **k: "12:00")}
br.tool_count, br.tool_stats, br.remote = 0, {}, True
check("uzaktan trash_file reddedilir ve çalışmaz", "uzaktan yapmıyorum" in br._call_tool("trash_file", {"path": "x"}) and not called)
check("uzaktan zararsız araç çalışır", br._call_tool("get_time", {}) == "12:00")
br.remote = False
check("yerelde trash_file çalışır (onay kapısı aracın kendisinde)", br._call_tool("trash_file", {"path": "x"}) == "silindi" and called)

# ---------------------------------------------------------------- kod ajanı: katmanlar
codeagent.RUN_TIMEOUT = 30
real_which = codeagent.shutil.which
codeagent.shutil.which = lambda n: {"prlimit": "/usr/bin/prlimit", "bwrap": "/usr/bin/bwrap"}.get(n)
codeagent._memwrap_cache = ["/usr/bin/systemd-run", "--user", "--scope", "-p", "MemoryMax=3G", "--"]
cmd, pre = codeagent.build_cmd([sys.executable, "a.py"], Path("/tmp/ws"), "bwrap")
check("bwrap kipi: cgroup bellek → prlimit → bwrap → komut sırası", cmd[0].endswith("systemd-run") and cmd[cmd.index("/usr/bin/prlimit") - 1] == "--"
      and cmd.index("/usr/bin/prlimit") < cmd.index("/usr/bin/bwrap") and cmd[-2:] == [sys.executable, "a.py"] and pre is None, str(cmd[:14]))
check("python komutuna adres alanı sınırı, diğerlerine yok", any(a.startswith("--as=") for a in cmd) and
      not any(a.startswith("--as=") for a in codeagent.build_cmd(["node", "a.js"], Path("/tmp/ws"), "bwrap")[0]))
cmd, pre = codeagent.build_cmd(["node", "a.js"], Path("/tmp/ws"), "off")
check("'off' (test/korumasız) kipinde cgroup sarmalayıcı yok", not any("systemd-run" in a for a in cmd) and cmd[-2:] == ["node", "a.js"])
n1 = len(codeagent._memwrap_cache)
codeagent.build_cmd(["node", "a.js"], Path("/tmp/ws"), "bwrap")
codeagent.build_cmd(["node", "a.js"], Path("/tmp/ws"), "bwrap")
check("sarmalayıcı önbelleği her çağrıda büyümez (kopya)", len(codeagent._memwrap_cache) == n1)
check("CPU ve dosya boyutu sınırı her zaman var", f"--cpu={codeagent.RUN_TIMEOUT + 5}" in cmd and "--fsize=20000000" in cmd)
codeagent.shutil.which = lambda n: None
cmd, pre = codeagent.build_cmd(["node", "a.js"], Path("/tmp/ws"), "off")
check("prlimit yoksa preexec_fn yedeği", cmd == ["node", "a.js"] and callable(pre))
codeagent.shutil.which = real_which
codeagent._memwrap_cache = None
codeagent.shutil.which = lambda n: None
check("systemd-run yoksa bellek sarmalayıcı boş, çökmez", codeagent._mem_wrap() == [])
codeagent.shutil.which = real_which
codeagent._memwrap_cache = None
# systemd-run --user temiz ortamda bus'a ulaşamaz ("Failed to connect to bus" -> her çalıştırma çıkış kodu 1); bus değişkenleri
# yalnızca dış sarmalayıcıya gider, başka hiçbir oturum/anahtar değişkeni gitmez (bwrap --clearenv programa hiçbirini geçirmez)
_old = {k: os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "GROQ_API_KEY")}
os.environ.update(XDG_RUNTIME_DIR="/run/user/1000", DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus", GROQ_API_KEY="gizli")
we = codeagent._wrap_env()
check("sarmalayıcı ortamı: temel + bus değişkenleri, anahtar yok", set(we) == set(codeagent.BASE_ENV) | {"XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"})
check("bwrap komutu ortamı temizler (--clearenv)", "--clearenv" in codeagent.bwrap_args(Path("/tmp/ws"), ["python", "a.py"]))
for k, v in _old.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v

# ---------------------------------------------------------------- tehlikeli çağrılar koda geri sızmasın
SKIP = ("test_", "tool_diag", "_check", "phone_app", "__pycache__")
bad_calls = []
for f in sorted(HERE.rglob("*.py")):
    s = str(f)
    if any(k in s for k in SKIP) or f.name == "check_all.py" or "workspace" in f.relative_to(HERE).parts:
        continue  # workspace/: kod ajanının ürettiği kod (proje kodu değil)
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        if not isinstance(n, ast.Call):
            continue
        name = ast.unparse(n.func)
        kw = {k.arg: k.value for k in n.keywords}
        if name in ("eval", "exec", "os.system", "os.popen", "pickle.loads", "pickle.load", "yaml.load", "marshal.loads"):
            bad_calls.append(f"{f.name}:{n.lineno} {name}")
        if "shell" in kw and not (isinstance(kw["shell"], ast.Constant) and kw["shell"].value is False):
            bad_calls.append(f"{f.name}:{n.lineno} shell=")
        if name.startswith("tempfile.mktemp"):
            bad_calls.append(f"{f.name}:{n.lineno} mktemp")
check("eval/exec/os.system/pickle/shell=True/mktemp hiçbir yerde yok", not bad_calls, str(bad_calls))
check("TLS doğrulaması kapatılmamış (verify=False / unverified context yok)",
      not any(("verify=False" in t or "_create_unverified_context" in t or "CERT_NONE" in t) for t in
              (f.read_text(encoding="utf-8") for f in HERE.rglob("*.py") if "test_" not in f.name and "phone_app" not in str(f) and "workspace" not in f.relative_to(HERE).parts)))
gi = (HERE / ".gitignore").read_text()
check(".gitignore: data/, Firebase anahtarı, hizmet hesabı dosyaları", "data/" in gi and "google-services.json" in gi)

# ---------------------------------------------------------------- uzaktan kip onay kapısını atlayamaz (güvenlik taraması 2026-10)
from skills import _confirm as confirm  # noqa: E402

ran = []


def _tool(name, fn):
    return name, ({"type": "function", "function": {"name": name, "description": name, "parameters": {"type": "object", "properties": {}}}}, fn)


rb = B.Brain(tools=dict([_tool("trash_file", lambda: confirm.request("rapor.txt çöpe atılacak.", lambda: ran.append("yerel") or "atıldı")),
                         _tool("task_delete", lambda: confirm.request("Görev silinecek.", lambda: ran.append("uzak") or "silindi"))]))
confirm.cancel()
rb._call_tool("trash_file", {})                        # bilgisayarda (yerel) oluşan bekleyen işlem
rb.remote = True
out = " ".join(rb.reply_stream("evet"))
check("uzaktan 'evet' bilgisayarda bekleyen onayı ÇALIŞTIRMAZ; işlem bekler", not ran and confirm.has_pending() and "bilgisayarın başında" in out, out)
out = " ".join(rb.reply_stream("hayır"))
check("uzaktan 'hayır' da yerel onaya dokunmaz", confirm.has_pending() and "bilgisayarın başında" in out)
rb.remote = False
check("bilgisayarda 'evet' yerel onayı çalıştırır", "atıldı" in " ".join(rb.reply_stream("evet")) and ran == ["yerel"])
rb.remote = True
rb._fast_route = lambda t: [("task_delete", {})] if "sil" in t else []   # uzaktan başlatılan onay (telefondan görev silme)
q = " ".join(rb.reply_stream("görevi sil"))
check("uzaktan başlatılan onay uzaktan cevaplanabilir", q.endswith("Onaylıyor musun?") and "silindi" in " ".join(rb.reply_stream("evet")) and ran == ["yerel", "uzak"])
rb.remote = False
rb.team.state = "plan"
rb.team.plan_expires = __import__("time").time() + 100
rb.remote = True
out = " ".join(rb.reply_stream("başla"))
check("bilgisayarda bekleyen ekip planı uzaktan başlatılamaz", rb.team.state == "plan" and "bilgisayarın başında" in out, out)
rb.remote = False
rb.team.abort()
confirm.cancel()
check("dosya adları (find_files) ve hafıza silme (forget) uzaktan kapalı", {"find_files", "forget"} <= B.REMOTE_BLOCKED)

# pano anahtarı: ASCII dışı başlık isteği düşürmez, 403 döner
import http.client  # noqa: E402

from dashboard import server as dserver  # noqa: E402

dd = dserver.Dashboard(types.SimpleNamespace(brain=rb), lambda t, silent=False: None, port=8995)
dd.start()
c = http.client.HTTPConnection("127.0.0.1", dd.port, timeout=5)
c.putrequest("GET", "/api/state")
c.putheader("Host", f"127.0.0.1:{dd.port}")
c.putheader("X-Token", "ğüşı".encode("utf-8"))
c.endheaders()
r = c.getresponse()
check("ASCII dışı anahtar başlığı: çökme yok, 403", r.status == 403, str(r.status))
c.close()
dd.stop()

print("TÜMÜ TAMAM" if not bad else f"{bad} HATA")
sys.exit(1 if bad else 0)
