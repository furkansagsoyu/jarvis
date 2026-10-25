"""MCP araçları: kullanıcının data/mcp.json'da tanımladığı yerel MCP sunucularını listeler ve araçlarını çağırır.

Güvenlik (kodda):
- İki araç da gizli (model şemasında yok); yalnızca açık komutla hızlı yoldan çağrılır:
    "mcp araçları"                          -> sunucular ve araçları
    "mcp: <sunucu> <araç> anahtar=değer ..." ya da "mcp: <sunucu> <araç> {json}"
- HER çağrı onay kapısından geçer (sunucu, araç ve argümanlar okunur); model onay veremez.
- Sonuç modele gitmez, olduğu gibi okunur (hızlı yol); yine de mcp_call dış içerik sayılır (UNTRUSTED_TOOLS).
- Uzaktan (Telegram/telefon) kapalı (REMOTE_BLOCKED). Sunucuya Jarvis'in ortamı/anahtarları geçmez (mcp_client.server_env).
"""
from __future__ import annotations

import json
import shlex

from . import _confirm as confirm
from . import _store

MAX_OUT = 800
_state: dict = {"raw": None, "mgr": None, "warn": []}


def _manager():
    import mcp_client  # noqa: PLC0415
    raw = _store.load(mcp_client.CONFIG, None)
    if raw != _state["raw"] or _state["mgr"] is None:   # yapılandırma değiştiyse eski sunucular kapatılır
        if _state["mgr"]:
            _state["mgr"].close_all()
        cfgs, warn = mcp_client.parse_config(raw or {})
        _state.update(raw=raw, mgr=mcp_client.Manager(cfgs), warn=warn)
    return _state["mgr"]


def parse_args(text: str) -> dict | str:
    """'a=1 yol="/tmp/x y"' ya da '{"a": 1}' -> dict; bozuksa hata cümlesi."""
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            d = json.loads(text)
        except ValueError:
            return "Argümanlar geçerli JSON değil."
        return d if isinstance(d, dict) else "Argümanlar bir JSON nesnesi olmalı."
    try:
        parts = shlex.split(text)
    except ValueError:
        return "Argümanlardaki tırnaklar kapanmamış."
    out = {}
    for p in parts:
        if "=" not in p:
            return f"'{p}' anahtar=değer biçiminde değil."
        k, v = p.split("=", 1)
        try:
            out[k] = json.loads(v)          # sayı, true/false, liste...
        except ValueError:
            out[k] = v
    return out


def speakable(text: str) -> str:
    """JSON sonucu sesli okunabilir düz metne çevirir ('source datetime: 2026-...; time_difference: +6.0h').
    Gerçek mcp-server-time çıktısı girintili JSON; TTS süslü parantez ve tırnakları okumasın. JSON değilse aynen döner."""
    t = (text or "").strip()
    if not t.startswith(("{", "[")):
        return text
    try:
        data = json.loads(t)
    except ValueError:
        return text
    out: list[str] = []

    def walk(v, path: str) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path} {k}".strip())
        elif isinstance(v, list):
            for i, x in enumerate(v, 1):
                walk(x, f"{path} {i}".strip())
        else:
            val = {True: "evet", False: "hayır", None: "yok"}.get(v, v) if isinstance(v, (bool, type(None))) else v
            out.append(f"{path.replace('_', ' ')}: {val}" if path else str(val))
    walk(data, "")
    return "; ".join(out) + "." if out else "Boş sonuç."


def mcp_list() -> str:
    import mcp_client  # noqa: PLC0415
    mgr = _manager()
    if not mgr.configs:
        warn = f" ({'; '.join(_state['warn'])})" if _state["warn"] else ""
        return f"Tanımlı MCP sunucusu yok{warn}. Sunucuları data/mcp.json dosyasına sen eklersin; örnek README'de."
    lines = []
    for name in sorted(mgr.configs):
        try:
            tools = [t["name"] for t in mgr.get(name).tools()]
            lines.append(f"{name}: {', '.join(tools) if tools else 'araç yok'}.")
        except mcp_client.McpError as exc:
            lines.append(f"{name}: açılamadı ({exc}).")
    return "MCP sunucuları. " + " ".join(lines)


def mcp_call(server: str, tool: str, args: str | dict = "") -> str:
    import mcp_client  # noqa: PLC0415
    arguments = args if isinstance(args, dict) else parse_args(args)
    if isinstance(arguments, str):
        return arguments
    mgr = _manager()
    try:
        srv = mgr.get(server)
        spec = next((t for t in srv.tools() if t["name"] == tool), None)
    except mcp_client.McpError as exc:
        return f"MCP: {exc}."
    if spec is None:
        return f"'{server}' sunucusunda '{tool}' adında izinli bir araç yok."
    missing = [r for r in (spec.get("inputSchema") or {}).get("required") or [] if r not in arguments]
    if missing:
        return f"'{tool}' için eksik argüman: {', '.join(missing)}."
    shown = json.dumps(arguments, ensure_ascii=False)
    shown = shown if len(shown) <= 200 else shown[:199] + "…"

    def run() -> str:
        try:
            text, is_err = mgr.get(server).call(tool, arguments)
        except mcp_client.McpError as exc:
            return f"MCP: {exc}."
        text = speakable(text)
        text = text if len(text) <= MAX_OUT else text[:MAX_OUT - 1] + "…"
        return f"MCP aracı hata verdi: {text}" if is_err else (text or "Araç çalıştı, çıktı yok.")
    return confirm.request(f"MCP: '{server}' sunucusunda '{tool}' aracı şu argümanlarla çalışacak: {shown}.", run)


SKILLS = [
    {"name": "mcp_list", "description": "Tanımlı yerel MCP sunucularını ve araçlarını listeler.", "hidden": True, "run": mcp_list,
     "parameters": {"type": "object", "properties": {}}},
    {"name": "mcp_call", "description": "Yerel bir MCP sunucusunun aracını onayla çalıştırır.", "hidden": True, "run": mcp_call,
     "parameters": {"type": "object", "properties": {
         "server": {"type": "string", "description": "sunucu adı (data/mcp.json)"},
         "tool": {"type": "string", "description": "araç adı"},
         "args": {"type": "string", "description": "anahtar=değer ... ya da JSON nesnesi"}},
         "required": ["server", "tool"]}},
]
