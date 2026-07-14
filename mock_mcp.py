#!/usr/bin/env python3
"""Tiny MCP stdio server with one 'echo' tool — for testing Chad Code's MCP client."""
import json, sys

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mock-mcp", "version": "1.0"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [{
            "name": "echo",
            "description": "Echoes back the message you send.",
            "inputSchema": {"type": "object",
                            "properties": {"message": {"type": "string"}},
                            "required": ["message"]}}]}})
    elif method == "tools/call":
        text = "MCP ECHO: " + msg["params"]["arguments"].get("message", "")
        send({"jsonrpc": "2.0", "id": mid,
              "result": {"content": [{"type": "text", "text": text}]}})
    elif mid is not None:  # unknown request
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "not found"}})
    # notifications: ignore
