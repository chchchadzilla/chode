#!/usr/bin/env python3
"""A scriptable fake OpenAI-compatible server for testing CHODE's agent loop and lifeline.

Run standalone:   python tests/mock_server.py [port]      (default 8080)
Use in tests:     with MockLLM(script) as m: ...  → m.url  (see test_agent.py / test_lifeline.py)

A "script" is a list of turns; each turn is either a string (plain assistant text) or a dict
{"content": str, "tool_calls": [{"name":..., "arguments": {...}}]}.

Knobs:
  stream_ok=False       answer stream requests with plain JSON (servers that ignore `stream`)
  fail_with=[401, 503]  HTTP codes to return for the first N chat requests (then behave normally)
  valid_models={...}    404 (OpenAI-style error body) for any other model name
  models=[...]          what GET /models advertises (default mock-1, mock-2)
  retry_after=2         Retry-After header on 429/503 answers
Also serves GET /api/tags (Ollama shape) and POST /embeddings. Every request body is in `.requests`.
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
    def __init__(self, script=None, port=0, stream_ok=True, fail_with=None, valid_models=None, models=None,
                 retry_after=None):
        self.script = list(script or DEFAULT_SCRIPT)
        self.requests = []
        self.turn = 0
        self.stream_ok = stream_ok
        self.fail_with = list(fail_with or [])
        self.valid_models = set(valid_models) if valid_models else None
        self.models = list(models or ["mock-1", "mock-2"])
        self.retry_after = retry_after
        self.lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/v1"
        self.root = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _next(self):
        with self.lock:
            t = self.script[self.turn] if self.turn < len(self.script) else "Nothing more to do."
            self.turn += 1
        if isinstance(t, str):
            t = {"content": t, "tool_calls": []}
        return t

    def _handler(self):
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj, headers=None):
                out = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                for k, v in (headers or {}).items():
                    self.send_header(k, str(v))
                self.end_headers()
                self.wfile.write(out)

            def do_GET(self):
                if self.path.endswith("/models"):
                    return self._json(200, {"data": [{"id": m} for m in mock.models]})
                if self.path.endswith("/api/tags"):
                    return self._json(200, {"models": [{"name": m} for m in mock.models]})
                self._json(404, {"error": "nope"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                mock.requests.append(body)
                if self.path.endswith("/embeddings"):
                    inputs = body.get("input") or []
                    return self._json(200, {"data": [{"index": i, "embedding": [float(len(t) % 7), 1.0, 0.5]} for i, t in enumerate(inputs)]})
                with mock.lock:
                    code = mock.fail_with.pop(0) if mock.fail_with else None
                if code:
                    msgs = {401: "Incorrect API key provided", 403: "forbidden", 404: "The model does not exist",
                            429: "Rate limit reached", 500: "internal error", 503: "overloaded"}
                    hdrs = {"Retry-After": mock.retry_after} if mock.retry_after and code in (429, 503) else None
                    return self._json(code, {"error": {"message": msgs.get(code, "error"), "type": "mock_error", "code": code}}, hdrs)
                if mock.valid_models is not None and body.get("model") not in mock.valid_models:
                    return self._json(404, {"error": {"message": f"The model `{body.get('model')}` does not exist or you do not have access to it.",
                                                      "type": "invalid_request_error", "code": "model_not_found"}})
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
