import json
from http.server import BaseHTTPRequestHandler, HTTPServer

STATE = {"n": 0}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        out = json.dumps({"data": [{"id": "test"}, {"id": "test-large"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["n"] += 1
        # turn 1: ask to write a file; turn 2: ask to run bash; turn 3: finish
        if STATE["n"] == 1:
            msg = {"role": "assistant", "content": "Creating the file.",
                   "tool_calls": [{"id": "c1", "type": "function", "function": {
                       "name": "write_file",
                       "arguments": json.dumps({"path": "hello.txt", "content": "hi from chad\n"})}}]}
        elif STATE["n"] == 2:
            msg = {"role": "assistant", "content": "",
                   "tool_calls": [{"id": "c2", "type": "function", "function": {
                       "name": "bash", "arguments": json.dumps({"command": "cat hello.txt"})}}]}
        else:
            # verify the tool results actually round-tripped in the request
            tool_msgs = [m for m in body["messages"] if m.get("role") == "tool"]
            last = tool_msgs[-1]["content"][:40] if tool_msgs else "nothing"
            msg = {"role": "assistant",
                   "content": f"Done. Saw {len(tool_msgs)} tool results; last said: {last!r}",
                   "tool_calls": None}
        resp = {"choices": [{"message": msg}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        out = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8080), H).serve_forever()
