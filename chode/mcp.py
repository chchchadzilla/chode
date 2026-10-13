"""MCP (Model Context Protocol) client — stdio and Streamable-HTTP transports."""
import json
import os
import shutil
import subprocess
import threading
import time

import requests

from . import VERSION
from .paths import MAX_TOOL_OUTPUT
from .ui import dim, yellow


def _truncate(text, limit=MAX_TOOL_OUTPUT):
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n\n… [truncated {len(text) - limit} chars] …\n\n" + text[-half:]


class McpServer:
    """One connected MCP server. stdio: JSON-RPC over newline-delimited stdin/stdout.
    http: JSON-RPC POSTs (Streamable HTTP; handles plain-JSON and simple SSE replies)."""

    def __init__(self, name, spec):
        self.name = name
        self.spec = spec
        self.transport = spec.get("transport") or spec.get("type") or ("http" if spec.get("url") else "stdio")
        if self.transport in ("sse", "streamable-http", "streamable_http"):
            self.transport = "http"
        self.proc = None
        self.tools = []
        self.error = None
        self.session_id = None
        self._id = 0
        self._lock = threading.Lock()
        self._responses = {}
        self._resp_event = threading.Condition()

    def start(self):
        try:
            if self.transport == "stdio":
                self._start_stdio()
            init = self.request("initialize", {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "chode", "version": VERSION},
            }, timeout=25)
            if "error" in init:
                raise RuntimeError(init["error"])
            self.notify("notifications/initialized", {})
            listed = self.request("tools/list", {}, timeout=25)
            self.tools = (listed.get("result") or {}).get("tools", [])
        except Exception as e:
            self.error = str(e)[:300]
            self.stop()

    @staticmethod
    def _resolve_cmd(cmd):
        for cand in (cmd, cmd + ".cmd", cmd + ".exe", cmd + ".bat"):
            hit = shutil.which(cand)
            if hit:
                return hit
        return cmd

    def _start_stdio(self):
        cmd = [self._resolve_cmd(self.spec["command"])] + list(self.spec.get("args", []))
        env = {**os.environ, **{k: str(v) for k, v in (self.spec.get("env") or {}).items()}}
        cwd = self.spec.get("cwd") or None
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, env=env, bufsize=1, cwd=cwd,
                                     encoding="utf-8", errors="replace")
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "id" in msg and ("result" in msg or "error" in msg):
                    with self._resp_event:
                        self._responses[msg["id"]] = msg
                        self._resp_event.notify_all()
        except Exception:
            pass

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None

    def _next_id(self):
        with self._lock:
            self._id += 1
            return self._id

    def request(self, method, params, timeout=60):
        rid = self._next_id()
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        if self.transport == "stdio":
            if not self.proc or self.proc.poll() is not None:
                raise RuntimeError("server process not running")
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
            deadline = time.time() + timeout
            with self._resp_event:
                while rid not in self._responses:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        raise RuntimeError(f"timeout waiting for {method}")
                    self._resp_event.wait(remaining)
                return self._responses.pop(rid)
        return self._http_rpc(msg, timeout)

    def notify(self, method, params):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if self.transport == "stdio":
            if self.proc and self.proc.poll() is None:
                self.proc.stdin.write(json.dumps(msg) + "\n")
                self.proc.stdin.flush()
        else:
            try:
                self._http_rpc(msg, 10, is_notification=True)
            except Exception:
                pass

    def _http_rpc(self, msg, timeout, is_notification=False):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   **{k: str(v) for k, v in (self.spec.get("headers") or {}).items()}}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        r = requests.post(self.spec["url"], json=msg, headers=headers, timeout=timeout)
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        if is_notification or r.status_code == 202 or not r.text.strip():
            return {}
        if "text/event-stream" in r.headers.get("Content-Type", ""):
            data = "{}"
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    data = line[5:].strip()
            return json.loads(data)
        return r.json()

    def call_tool(self, tool_name, arguments):
        resp = self.request("tools/call", {"name": tool_name, "arguments": arguments}, timeout=120)
        if "error" in resp:
            return f"MCP error: {json.dumps(resp['error'])[:500]}"
        result = resp.get("result") or {}
        parts = []
        for block in result.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(f"[{block.get('type','?')} content omitted]")
        out = "\n".join(parts) or json.dumps(result)[:2000]
        if result.get("isError"):
            out = "Tool reported an error:\n" + out
        return _truncate(out)


class McpManager:
    SEP = "__"

    def __init__(self, cfg):
        self.servers = {}
        for name, spec in (cfg.get("mcp_servers") or {}).items():
            if isinstance(spec, dict) and spec.get("disabled"):
                continue
            self.servers[name] = McpServer(name, spec)

    def start_all(self, quiet=False):
        if not self.servers:
            return
        threads = []
        for s in self.servers.values():
            t = threading.Thread(target=s.start, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=30)
        if quiet:
            return
        for s in self.servers.values():
            if s.error:
                print(yellow(f"  mcp: '{s.name}' failed to start: {s.error}"))
            elif s.tools:
                print(dim(f"  mcp: '{s.name}' connected ({len(s.tools)} tools)"))

    def tool_defs(self):
        defs = []
        for s in self.servers.values():
            for t in s.tools:
                defs.append({
                    "name": f"mcp{self.SEP}{s.name}{self.SEP}{t['name']}",
                    "description": f"[MCP:{s.name}] {(t.get('description') or '')[:800]}",
                    "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}},
                    "safe": False,
                })
        return defs

    def execute(self, namespaced, args):
        try:
            _, server, tool = namespaced.split(self.SEP, 2)
        except ValueError:
            return f"Error: bad MCP tool name {namespaced}"
        s = self.servers.get(server)
        if not s:
            return f"Error: unknown MCP server '{server}'"
        try:
            return s.call_tool(tool, args)
        except Exception as e:
            return f"MCP call failed: {e}"

    def stop_all(self):
        for s in self.servers.values():
            s.stop()
