import os
import sys
from pathlib import Path

from chode.mcp import McpManager, McpServer

HERE = Path(__file__).resolve().parent
PY = sys.executable


def test_stdio_client_against_mock_server():
    s = McpServer("mock", {"transport": "stdio", "command": PY, "args": [str(HERE / "mock_mcp.py")]})
    s.start()
    assert not s.error and [t["name"] for t in s.tools] == ["echo"]
    assert s.call_tool("echo", {"message": "yo"}) == "MCP ECHO: yo"
    s.stop()


def test_manager_namespacing(project):
    tmp, cfg, app = project
    cfg["mcp_servers"] = {"mock": {"command": PY, "args": [str(HERE / "mock_mcp.py")]},
                          "off": {"command": PY, "args": ["x"], "disabled": True}}
    mgr = McpManager(cfg)
    mgr.start_all(quiet=True)
    defs = mgr.tool_defs()
    assert [d["name"] for d in defs] == ["mcp__mock__echo"] and defs[0]["safe"] is False
    assert mgr.execute("mcp__mock__echo", {"message": "hi"}) == "MCP ECHO: hi"
    assert mgr.execute("mcp__nope__echo", {}).startswith("Error")
    mgr.stop_all()


def test_chode_as_mcp_server(project):
    """Drive `chode mcp-serve` with our own client: tools list + a guarded call."""
    tmp, cfg, app = project
    env = {**os.environ, "CHODE_MCP_CWD": str(tmp)}
    s = McpServer("chode", {"transport": "stdio", "command": PY, "args": ["-m", "chode", "mcp-serve", "--mode", "edits"], "env": env})
    s.start()
    assert not s.error, s.error
    names = {t["name"] for t in s.tools}
    assert {"read_file", "write_file", "bash", "search_codebase", "remember", "recall", "order_status", "ship"} <= names
    assert "spawn_agent" not in names
    out = s.call_tool("write_file", {"path": "via_mcp.txt", "content": "ok\n"})
    assert out.startswith("Created") and (tmp / "via_mcp.txt").read_text(encoding="utf-8") == "ok\n"
    # edits mode + no tty → bash is refused, and says so
    out = s.call_tool("bash", {"command": "touch via_bash.txt"})
    assert "refused" in out and not (tmp / "via_bash.txt").exists()
    assert "hi" in s.call_tool("bash", {"command": "echo hi"})  # `echo` is on the default allowlist
    out = s.call_tool("order_status", {})
    assert "ORDER score" in out
    s.stop()
