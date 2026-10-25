"""Yerel MCP (Model Context Protocol) istemcisi: stdio üzerinden JSON-RPC 2.0 (satır başına bir mesaj). Ek bağımlılık yok.

Sunucular kullanıcı tarafından data/mcp.json dosyasında tanımlanır (Jarvis kendisi sunucu eklemez):
    {"servers": {"zaman": {"command": "uvx", "args": ["mcp-server-time"], "env": {}, "tools": ["get_current_time"], "timeout": 30}}}
- command + args doğrudan çalıştırılır (kabuk yok). "tools" verilirse yalnızca o araçlar kullanılabilir (izin listesi).
- Sunucuya Jarvis'in ortamı GEÇMEZ (anahtarlar/oturum değişkenleri yok): yalnızca PATH, HOME, LANG + config'teki "env".
- Yalnızca yerel stdio sunucuları; uzak (HTTP) sunucu desteği bilerek yok.
Araçların Jarvis'e bağlanışı ve onay kapısı: skills/mcp.py.
"""
from __future__ import annotations

import atexit
import itertools
import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field

PROTOCOL = "2025-06-18"
CONFIG = "mcp.json"
DEFAULT_TIMEOUT = 30.0
START_TIMEOUT = 20.0
MAX_LINE = 4_000_000


class McpError(Exception):
    pass


@dataclass
class ServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[str] | None = None      # izin listesi (None: hepsi)
    timeout: float = DEFAULT_TIMEOUT


def parse_config(raw) -> tuple[dict[str, ServerConfig], list[str]]:
    """data/mcp.json içeriğini doğrular: (sunucular, uyarılar). Bozuk girdiler atlanır, nedeni uyarıya yazılır."""
    out: dict[str, ServerConfig] = {}
    warn: list[str] = []
    servers = raw.get("servers") if isinstance(raw, dict) else None
    if not isinstance(servers, dict):
        return out, ["mcp.json içinde 'servers' nesnesi yok"] if raw else []
    for name, c in servers.items():
        if not isinstance(name, str) or not name.replace("-", "").replace("_", "").isalnum():
            warn.append(f"geçersiz sunucu adı: {name!r}")
            continue
        if not isinstance(c, dict) or not isinstance(c.get("command"), str) or not c["command"].strip():
            warn.append(f"{name}: 'command' eksik")
            continue
        args, env, tools = c.get("args", []), c.get("env", {}), c.get("tools")
        if not (isinstance(args, list) and all(isinstance(a, str) for a in args)):
            warn.append(f"{name}: 'args' metin listesi olmalı")
            continue
        if not (isinstance(env, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())):
            warn.append(f"{name}: 'env' metin->metin olmalı")
            continue
        if tools is not None and not (isinstance(tools, list) and all(isinstance(t, str) for t in tools)):
            warn.append(f"{name}: 'tools' metin listesi olmalı")
            continue
        try:
            timeout = min(max(float(c.get("timeout", DEFAULT_TIMEOUT)), 1.0), 300.0)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        out[name.lower()] = ServerConfig(name.lower(), c["command"].strip(), args, env, tools, timeout)
    return out, warn


def server_env(cfg: ServerConfig) -> dict[str, str]:
    """Sunucunun ortamı: Jarvis'in anahtarları (GROQ_API_KEY vb.) ve oturum değişkenleri GEÇMEZ."""
    base = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if os.environ.get(k)}
    return {**base, **cfg.env}


class StdioServer:
    """Tek bir MCP sunucu süreci: başlat, initialize, tools/list, tools/call."""

    def __init__(self, cfg: ServerConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self._ids = itertools.count(1)
        self._waiting: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._write = threading.Lock()
        self.info: dict = {}
        self._tools: list[dict] | None = None
        self._eof = False   # okuyucu çıktının kapandığını gördü (poll() bir an daha None dönebilir)

    # ------------------------------------------------------------ süreç
    def alive(self) -> bool:
        return self.proc is not None and not self._eof and self.proc.poll() is None

    def start(self) -> None:
        try:
            self.proc = subprocess.Popen([self.cfg.command, *self.cfg.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, env=server_env(self.cfg), start_new_session=True)
        except OSError as exc:
            raise McpError(f"{self.cfg.name} başlatılamadı ({exc.strerror or type(exc).__name__})") from exc
        threading.Thread(target=self._reader, daemon=True).start()
        res = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                          "clientInfo": {"name": "jarvis", "version": "2"}}, timeout=START_TIMEOUT)
        self.info = res.get("serverInfo") or {}
        self.notify("notifications/initialized")

    def close(self) -> None:
        p, self.proc = self.proc, None
        self._tools = None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()

    # ------------------------------------------------------------ JSON-RPC
    def _send(self, msg: dict) -> None:
        if not self.alive():
            raise McpError(f"{self.cfg.name} çalışmıyor")
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self._write:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
        except OSError as exc:
            raise McpError(f"{self.cfg.name} bağlantısı koptu") from exc

    def _reader(self) -> None:
        proc = self.proc
        for line in iter(lambda: proc.stdout.readline(MAX_LINE), b""):
            try:
                msg = json.loads(line)
            except ValueError:
                continue                     # sunucunun stdout'a yazdığı log satırları
            if not isinstance(msg, dict):
                continue
            if "method" in msg and "id" in msg:  # sunucudan istemciye istek (örn. ping, sampling): yalnızca ping desteklenir
                reply = {"jsonrpc": "2.0", "id": msg["id"]}
                reply.update({"result": {}} if msg["method"] == "ping" else {"error": {"code": -32601, "message": "desteklenmiyor"}})
                try:
                    self._send(reply)
                except McpError:
                    pass
                continue
            with self._lock:
                q = self._waiting.get(msg.get("id"))
            if q:
                q.put(msg)
        self._eof = True                      # önce işaretle: Manager.get yeniden başlatsın
        with self._lock:                      # süreç kapandı: bekleyenleri uyandır
            for q in self._waiting.values():
                q.put({"error": {"message": "sunucu kapandı"}})

    def request(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        rid = next(self._ids)
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._waiting[rid] = q
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params is not None else {})})
            try:
                msg = q.get(timeout=timeout or self.cfg.timeout)
            except queue.Empty:
                self.close()   # takılmış sunucu sonraki çağrıları bekletmesin: kapatılır, bir sonraki kullanımda temiz başlar
                raise McpError(f"{self.cfg.name} {int(timeout or self.cfg.timeout)} sn içinde yanıt vermedi") from None
        finally:
            with self._lock:
                self._waiting.pop(rid, None)
        if "error" in msg:
            err = msg["error"] if isinstance(msg["error"], dict) else {}
            raise McpError(str(err.get("message") or "bilinmeyen hata")[:200])
        return msg.get("result") or {}

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})})

    # ------------------------------------------------------------ MCP
    def tools(self) -> list[dict]:
        """İzin listesine göre süzülmüş araçlar: [{name, description, inputSchema}]."""
        if self._tools is None:
            got, cursor = [], None
            for _ in range(20):               # sayfalama
                res = self.request("tools/list", {"cursor": cursor} if cursor else {})
                got += [t for t in res.get("tools") or [] if isinstance(t, dict) and isinstance(t.get("name"), str)]
                cursor = res.get("nextCursor")
                if not cursor:
                    break
            allow = self.cfg.tools
            self._tools = [t for t in got if allow is None or t["name"] in allow]
        return self._tools

    def call(self, tool: str, arguments: dict) -> tuple[str, bool]:
        """(metin, hata_mı). Metin dışı içerik (görsel, kaynak) yalnızca türüyle anılır."""
        res = self.request("tools/call", {"name": tool, "arguments": arguments})
        parts = []
        for c in res.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(str(c.get("text", "")))
            elif isinstance(c, dict):
                parts.append(f"[{c.get('type', 'içerik')}]")
        if not parts and res.get("structuredContent") is not None:
            parts.append(json.dumps(res["structuredContent"], ensure_ascii=False))
        return "\n".join(parts).strip(), bool(res.get("isError"))


class Manager:
    """Sunucuları tembel başlatır ve açık tutar; Jarvis kapanınca hepsini kapatır."""

    def __init__(self, configs: dict[str, ServerConfig]):
        self.configs = configs
        self.servers: dict[str, StdioServer] = {}
        self._lock = threading.Lock()
        atexit.register(self.close_all)

    def get(self, name: str) -> StdioServer:
        cfg = self.configs.get((name or "").lower())
        if not cfg:
            raise McpError(f"'{name}' adında MCP sunucusu tanımlı değil")
        with self._lock:
            srv = self.servers.get(cfg.name)
            if srv is None or not srv.alive():   # ilk kullanım ya da çökmüş: yeniden başlat
                if srv:
                    srv.close()
                srv = StdioServer(cfg)
                try:
                    srv.start()
                except McpError:
                    srv.close()
                    raise
                self.servers[cfg.name] = srv
            return srv

    def close_all(self) -> None:
        for s in list(self.servers.values()):
            s.close()
        self.servers.clear()
