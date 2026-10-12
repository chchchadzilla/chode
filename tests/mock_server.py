#!/usr/bin/env python3
"""A scriptable fake OpenAI-compatible server for testing CHODE's agent loop.

Run standalone:   python tests/mock_server.py [port]      (default 8080)
Use in tests:     with MockLLM(script) as m: ...  → m.url  (see test_agent.py)

A "script" is a list of turns; each turn is either a string (plain assistant
text) or a dict {"content": str, "tool_calls": [{"name":..., "arguments": {...}}]}.
Both streaming (SSE) and non-streaming requests are supported; every request
body is recorded in `.requests`.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_SCRIPT = [
    {"content": "Creating the file.", "tool_calls": [{"name": "write_file", "arguments": {"path": "hello.txt", "content": "hi from chode\n"}}]},
    {"content": "", "tool_calls": [{"name": "bash", "arguments": {"command": "cat hello.txt"}}]},
    "Done. Created hello.txt and verified it.",
]


class MockLLM:
    def __init__(self, script=None, port=0, stream_ok=True):
        self.script = list(script or DEFAULT_SCRIPT)
        self.requests = []
        self.turn = 0
        self.stream_ok = stream_ok
        self.lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/v1"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _next(self):
        with self.lock:
            if self.turn < len(self.script):
                t = self.script[self.turn]
            else:
                t = "Nothing more to do."
            self.turn += 1
        if isinstance(t, str):
            t = {"content": t, "tool_calls": []}
        return t

    def _handler(self):
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                out = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_GET(self):
                if self.path.endswith("/models"):
                    return self._json(200, {"data": [{"id": "mock-1"}, {"id": "mock-2"}]})
                self._json(404, {"error": "nope"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                mock.requests.append(body)
                if self.path.endswith("/embeddings"):
                    inputs = body.get("input") or []
                    return self._json(200, {"data": [{"index": i, "embedding": [float(len(t) % 7), 1.0, 0.5]} for i, t in enumerate(inputs)]})
                turn = mock._next()
                tcs = [{"id": f"call_{i}", "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                       for i, tc in enumerate(turn.get("tool_calls") or [])]
                usage = {"prompt_tokens": 100 + 10 * len(mock.requests), "completion_tokens": 20}
                if body.get("stream") and mock.stream_ok:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()

                    def chunk(delta, finish=None, with_usage=False):
                        obj = {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                        if with_usage:
                            obj["usage"] = usage
                        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                    text = turn.get("content") or ""
                    for i in range(0, len(text), 7):
                        chunk({"content": text[i:i + 7]})
                    for i, tc in enumerate(tcs):
                        chunk({"tool_calls": [{"index": i, "id": tc["id"], "type": "function", "function": {"name": tc["function"]["name"], "arguments": ""}}]})
                        args = tc["function"]["arguments"]
                        for j in range(0, len(args), 11):
                            chunk({"tool_calls": [{"index": i, "function": {"arguments": args[j:j + 11]}}]})
                    chunk({}, finish="tool_calls" if tcs else "stop", with_usage=True)
                    self.wfile.write(b"data: [DONE]\n\n")
                    return
                msg = {"role": "assistant", "content": turn.get("content") or "", "tool_calls": tcs or None}
                self._json(200, {"choices": [{"message": msg}], "usage": usage})
        return H


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    m = MockLLM(port=port)
    print(f"mock LLM on {m.url}")
    m.thread.start()
    try:
        m.thread.join()
    except KeyboardInterrupt:
        pass
