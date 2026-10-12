"""CHODE as an MCP server (`chode mcp-serve`).

Exposes CHODE's tools over stdio JSON-RPC so Claude Code, Codex, Gemini CLI,
Cursor, VS Code — anything that speaks MCP — can use CHODE's memory, ORDER,
search, backups and guarded file/shell tools. This is how the Plan Bridge works.

Permissions: there is no chat UI here, so decisions come from the lanes only
(--mode plan|edits|yolo). Dangerous commands are always refused. When a real
terminal is attached (/dev/tty), CHODE asks you there.
"""
import json
import os
import sys
from pathlib import Path

from . import VERSION, conscience, state
from .config import load_config
from .paths import ensure_home
from .tools import TOOLS, execute_tool, tool_def
from .ui import SilentUI


class TtyUI(SilentUI):
    """Asks permission on the controlling terminal when one exists (stdin/stdout are the protocol)."""
    interactive = True

    def __init__(self):
        super().__init__()
        self.tty_in = self.tty_out = None
        try:
            if os.name == "nt":
                self.tty_in = open("CONIN$", "r")
                self.tty_out = open("CONOUT$", "w")
            else:
                self.tty_in = open("/dev/tty", "r")
                self.tty_out = open("/dev/tty", "w")
        except Exception:
            self.tty_in = self.tty_out = None
            self.interactive = False

    def ask_permission(self, req):
        if not self.tty_out:
            return "n"
        try:
            self.tty_out.write(f"\n[chode] {req['name']} {req.get('describe','')}\n")
            if req.get("plain_diff"):
                self.tty_out.write(req["plain_diff"][:3000] + "\n")
            if req.get("danger"):
                self.tty_out.write(f"  DANGEROUS: {req['danger']} — type 'yes' to allow: ")
                self.tty_out.flush()
                return "y" if self.tty_in.readline().strip() == "yes" else "n"
            self.tty_out.write("  allow? [y]es/[n]o/[a]lways: ")
            self.tty_out.flush()
            ans = self.tty_in.readline().strip().lower()
            return {"": "y", "y": "y", "yes": "y", "a": "a", "always": "a"}.get(ans, "n")
        except Exception:
            return "n"

    def ask_user(self, question, default=""):
        if not self.tty_out:
            return default
        try:
            self.tty_out.write(f"\n[chode] {question}\n> ")
            self.tty_out.flush()
            return self.tty_in.readline().strip() or default
        except Exception:
            return default


EXPOSED = [t for t in TOOLS if t["name"] not in ("set_todos", "spawn_agent", "skill")]


def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def serve(mode="edits"):
    ensure_home()
    cwd = os.environ.get("CHODE_MCP_CWD")
    if cwd and Path(cwd).is_dir():
        os.chdir(cwd)
    cfg = load_config()
    cfg["mode"] = mode if mode in ("plan", "ask", "edits", "yolo") else "edits"
    ui = TtyUI()
    app = state.set_app(state.App(cfg, ui=ui))
    app.oneshot = not ui.interactive
    from .permissions import Permissions
    from .llm import LLMClient
    app.perms = Permissions(cfg, ui)
    app.client = LLMClient(cfg) if cfg.get("provider") and "plan" not in cfg.get("provider", "") else None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "chode", "version": VERSION}}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]} for t in EXPOSED]}})
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            if not tool_def(name) or name not in {t["name"] for t in EXPOSED}:
                _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown tool {name}"}})
                continue
            if name == "ask_user" and not ui.interactive:
                text = "The user is not reachable from MCP-server mode; make a reasonable assumption and say so."
            elif not app.perms.ask(name, args):
                conscience.log("mcp_denied", tool=name, detail=str(args)[:200])
                text = (f"CHODE refused `{name}` in mode '{cfg['mode']}' (no terminal to ask on). "
                        f"Run the host with CHODE in a more permissive mode, or do it another way.")
                _send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": True}})
                continue
            else:
                try:
                    text = execute_tool(name, args)
                except Exception as e:
                    text = f"Error executing {name}: {e}"
                if cfg.get("redact_secrets", True):
                    from .security import redact_secrets
                    text, _ = redact_secrets(text)
            _send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}]}})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})
        # notifications are ignored
