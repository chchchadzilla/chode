"""The Deck — CHODE's browser GUI. Zero dependencies: http.server + Server-Sent Events.

Same brain as the terminal (same agent loop, permissions, memory, ORDER). The
page is bound to 127.0.0.1 and every route carries a per-launch secret token,
so other sites in your browser can't poke it.
"""
import contextlib
import io
import json
import queue
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import VERSION, TAGLINE, state
from .ui import TerminalUI


class WebUI(TerminalUI):
    """Pushes events to connected browsers; blocks on permission/question answers."""
    name = "web"
    interactive = True

    def __init__(self):
        super().__init__(quiet=True)
        self.clients = []           # list of queue.Queue
        self.pending = {}           # id -> {"event": threading.Event, "answer": str}
        self.lock = threading.Lock()
        self.transcript = []        # rendered events for late joiners (bounded)
        self._text_buf = []

    # -- plumbing --
    def emit(self, kind, **data):
        ev = {"kind": kind, "ts": time.time(), **data}
        with self.lock:
            if kind not in ("text_delta", "thinking"):
                self.transcript.append(ev)
                self.transcript = self.transcript[-400:]
            for q in list(self.clients):
                try:
                    q.put_nowait(ev)
                except Exception:
                    pass

    def subscribe(self):
        q = queue.Queue(maxsize=2000)
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def answer(self, pid, ans):
        with self.lock:
            p = self.pending.get(pid)
        if not p:
            return False
        p["answer"] = ans
        p["event"].set()
        return True

    def _wait(self, kind, payload, timeout=900):
        pid = secrets.token_hex(6)
        p = {"event": threading.Event(), "answer": None}
        with self.lock:
            self.pending[pid] = p
        self.emit(kind, id=pid, **payload)
        p["event"].wait(timeout)
        with self.lock:
            self.pending.pop(pid, None)
        self.emit("resolved", id=pid)
        return p["answer"]

    # -- UI protocol --
    def text_start(self, dimmed=False):
        self._text_buf = []
        self.emit("text_start")

    def text_delta(self, s):
        self._text_buf.append(s)
        self.emit("text_delta", text=s)

    def text_end(self):
        self.emit("text_end", text="".join(self._text_buf))
        self._text_buf = []

    def text_full(self, text, dimmed=False):
        self.emit("text_start")
        self.emit("text_end", text=text, dimmed=dimmed)

    def tool_start(self, name, preview):
        from .ui import _strip_ansi
        self.emit("tool_start", name=name, preview=_strip_ansi(preview))

    def tool_result(self, name, result):
        self.emit("tool_result", name=name, result=result[:12000])

    def tool_denied(self, name):
        self.emit("tool_denied", name=name)

    def todos(self, todos):
        self.emit("todos", todos=todos)

    def notice(self, msg, level="dim"):
        from .ui import _strip_ansi
        self.emit("notice", text=_strip_ansi(msg).strip(), level=level)

    def status(self, text):
        self.emit("notice", text=text, level="dim")

    def thinking(self, label):
        ui = self

        class _T:
            def __enter__(self_):
                ui.emit("thinking", on=True, label=label)
                return self_

            def stop(self_):
                ui.emit("thinking", on=False)

            def __exit__(self_, *a):
                ui.emit("thinking", on=False)
                return False
        return _T()

    def ask_permission(self, req):
        payload = {"name": req["name"], "describe": _plain(req.get("describe", "")), "diff": req.get("plain_diff", ""),
                   "outside": req.get("outside"), "danger": req.get("danger"), "sensitive": req.get("sensitive"),
                   "can_prefix": req.get("can_prefix"), "prefix_word": req.get("prefix_word"),
                   "args": {k: (v if len(json.dumps(v)) < 4000 else "…") for k, v in req.get("args", {}).items()}}
        ans = self._wait("permission", payload)
        if ans is None:
            return "n"
        if req.get("danger"):
            return "y" if ans == "yes" else "n"
        return ans if ans in ("y", "n", "a", "p") else "n"

    def ask_user(self, question, default=""):
        ans = self._wait("question", {"question": question})
        return ans if ans is not None else default


def _plain(s):
    from .ui import _strip_ansi
    return _strip_ansi(str(s)).strip()


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------

class Deck:
    def __init__(self, cfg, repl=None):
        from .repl import Repl
        self.cfg = cfg
        self.token = secrets.token_urlsafe(18)
        self.ui = WebUI()
        if repl is None:
            self.repl = Repl(cfg, None, ui=self.ui)
            self.owned = True
        else:
            self.repl = repl
            self.owned = False
            self._old_ui = repl.ui
            repl.ui = self.ui
            repl.app.ui = self.ui
            repl.perms.ui = self.ui
        self.inbox = queue.Queue()
        self.busy = False
        self.worker = threading.Thread(target=self._work, daemon=True)

    def start(self):
        if self.owned:
            self.repl.boot(quiet=True)
        self.worker.start()

    def stop(self):
        if self.owned:
            try:
                self.repl.wrap_up()
            finally:
                self.repl.store.save(self.repl.history, model=self.repl.client.model, provider=self.repl.client.provider)
                if self.repl.app.mcp:
                    self.repl.app.mcp.stop_all()
        else:
            self.repl.ui = self._old_ui
            self.repl.app.ui = self._old_ui
            self.repl.perms.ui = self._old_ui

    def _work(self):
        from .commands import handle_slash
        from .agent import build_system_prompt
        while True:
            kind, payload = self.inbox.get()
            self.busy = True
            self.ui.emit("busy", on=True)
            try:
                if kind == "message":
                    self.ui.emit("user", text=payload)
                    msg = self.repl.preprocess_input(payload)
                    if msg:
                        self.repl.run_turn(msg)
                elif kind == "cmd":
                    self.ui.emit("user", text=payload)
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        keep, msg = handle_slash(payload, self.repl)
                    out = _plain(buf.getvalue())
                    if out:
                        self.ui.emit("notice", text=out, level="plain")
                    if msg:
                        self.repl.run_turn(msg)
                        self.repl.system_ref[0] = build_system_prompt(self.repl.client, self.cfg)
            except Exception as e:
                self.ui.emit("notice", text=f"error: {e}", level="error")
            finally:
                self.busy = False
                self.ui.emit("busy", on=False)
                self.ui.emit("status", **self.state_summary())

    def state_summary(self):
        c = self.repl.client
        a = self.repl.app
        try:
            from .order import status_line
            order_line, audit = status_line(cfg=self.cfg)
            order = {"line": order_line, "score": audit["score"], "label": audit["label"],
                     "checks": [{"label": ch["label"], "ok": ch["ok"], "detail": ch["detail"]} for ch in audit["checks"]]}
        except Exception:
            order = {"line": "", "score": 0, "label": "", "checks": []}
        try:
            mems = [{"id": e["id"], "kind": e.get("kind"), "scope": e.get("scope"), "text": e["text"]}
                    for e in sorted(a.memory_store().all(), key=lambda x: -x.get("ts", 0))[:30]]
        except Exception:
            mems = []
        return {"model": c.model, "provider": c.provider, "mode": self.cfg["mode"], "cost": round(c.total_cost, 4),
                "plan": c.api_style == "plan", "ctx": c.context_pct(), "tokens_in": c.total_in, "tokens_out": c.total_out,
                "cwd": str(Path.cwd()), "order": order, "memories": mems, "todos": a.todos, "busy": self.busy,
                "version": VERSION, "name": self.cfg.get("name") or "legend", "theme": self.cfg.get("theme", "magenta")}


def make_handler(deck):
    token = deck.token
    ui = deck.ui

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (json.dumps(body) if ctype.startswith("application/json") else body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "text" in ctype else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(data)

        def _route(self):
            path = urlparse(self.path).path
            prefix = f"/t/{token}"
            if path == "/":
                return "root", ""
            if not path.startswith(prefix):
                return None, ""
            return "api", path[len(prefix):] or "/"

        def do_GET(self):
            kind, sub = self._route()
            if kind == "root":
                self.send_response(302)
                self.send_header("Location", f"/t/{token}/")
                self.end_headers()
                return
            if kind is None:
                return self._send(404, {"error": "not found"})
            if sub == "/":
                return self._send(200, HTML.replace("__TOKEN__", token).replace("__VERSION__", VERSION).replace("__TAGLINE__", TAGLINE), "text/html")
            if sub == "/state":
                s = deck.state_summary()
                s["transcript"] = ui.transcript[-200:]
                return self._send(200, s)
            if sub == "/events":
                q = ui.subscribe()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    self.wfile.write(b": hello\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            ev = q.get(timeout=15)
                            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    ui.unsubscribe(q)
                return
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            kind, sub = self._route()
            if kind != "api":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, {"error": "bad json"})
            if sub == "/send":
                text = (body.get("message") or "").strip()
                if not text:
                    return self._send(400, {"error": "empty"})
                if text.startswith("/"):
                    blocked = ("/gui", "/ride", "/import", "/resume", "/intro", "/exit", "/quit")
                    if text.split()[0] in blocked:
                        ui.emit("notice", text=f"{text.split()[0]} is terminal-only — use the terminal for that one", level="warn")
                        return self._send(200, {"ok": True})
                    deck.inbox.put(("cmd", text))
                else:
                    deck.inbox.put(("message", text))
                return self._send(200, {"ok": True})
            if sub == "/answer":
                ok = ui.answer(body.get("id", ""), str(body.get("answer", "")))
                return self._send(200, {"ok": ok})
            if sub == "/mode":
                from .config import MODES, save_config
                m = body.get("mode")
                if m in MODES:
                    deck.cfg["mode"] = m
                    save_config(deck.cfg)
                    from .agent import build_system_prompt
                    deck.repl.system_ref[0] = build_system_prompt(deck.repl.client, deck.cfg)
                ui.emit("status", **deck.state_summary())
                return self._send(200, {"ok": True})
            if sub == "/undo":
                msg = deck.repl.app.checkpoints.undo()
                ui.emit("notice", text=msg or "nothing to undo", level="dim")
                return self._send(200, {"ok": True})
            if sub == "/forget":
                deck.repl.app.memory_store().forget(body.get("id", ""))
                ui.emit("status", **deck.state_summary())
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})

    return H


def serve(cfg, repl=None):
    deck = Deck(cfg, repl)
    port = int((cfg.get("gui") or {}).get("port", 7331) or 7331)
    httpd = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), make_handler(deck))
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        print("could not bind a port for the GUI")
        return
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/t/{deck.token}/"
    deck.start()
    print(f"\n  🖥  the Deck is up → {url}\n  {'' if repl else '   '}Ctrl-C to stop\n")
    if (cfg.get("gui") or {}).get("open_browser", True):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown() if False else None
        httpd.server_close()
        deck.stop()
        print("  deck closed")


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CHODE · the Deck</title>
<style>
:root{--bg:#0b0b10;--panel:#121219;--panel2:#17171f;--line:#23232e;--text:#e8e8f0;--muted:#8d8da3;--m:#ff3fb3;--c:#2ee6ff;--ok:#3dff8f;--warn:#ffd23f;--bad:#ff4d4d;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;display:grid;grid-template-rows:52px 1fr auto;grid-template-columns:1fr 300px;grid-template-areas:"top top" "chat side" "composer side"}
header{grid-area:top;display:flex;align-items:center;gap:16px;padding:0 18px;border-bottom:1px solid var(--line);background:var(--panel)}
.brand{font-weight:900;font-size:20px;letter-spacing:1px;font-family:var(--sans)}.brand b{color:var(--m)}.brand i{color:var(--c);font-style:normal}
.brand small{color:var(--muted);font-weight:400;font-size:11px;margin-left:8px;letter-spacing:0}
.pill{border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:12px;color:var(--muted);background:var(--panel2);display:flex;align-items:center;gap:6px}
.pill select{background:transparent;color:var(--text);border:0;font-size:12px;outline:0}
.spacer{flex:1}.dot{width:8px;height:8px;border-radius:50%;background:var(--muted)}.dot.on{background:var(--ok);box-shadow:0 0 10px var(--ok)}
#chat{grid-area:chat;overflow-y:auto;padding:22px 26px;scroll-behavior:smooth}
#side{grid-area:side;border-left:1px solid var(--line);background:var(--panel);overflow-y:auto;padding:16px;font-size:13px}
#composer{grid-area:composer;border-top:1px solid var(--line);background:var(--panel);padding:12px 18px;display:flex;gap:10px;align-items:flex-end}
textarea{flex:1;background:var(--panel2);border:1px solid var(--line);border-radius:12px;color:var(--text);font:inherit;padding:12px 14px;resize:none;min-height:48px;max-height:200px;outline:0}
textarea:focus{border-color:var(--c)}button{background:var(--panel2);border:1px solid var(--line);color:var(--text);border-radius:10px;padding:10px 14px;cursor:pointer;font:inherit}
button:hover{border-color:var(--c)}button.primary{background:linear-gradient(90deg,var(--m),var(--c));color:#0b0b10;border:0;font-weight:700}
.msg{max-width:860px;margin:0 0 18px}.msg.user{margin-left:auto;max-width:720px}.msg.user .b{background:var(--panel2);border:1px solid var(--line);border-radius:14px 14px 4px 14px;padding:10px 14px;white-space:pre-wrap}
.msg.bot .b{line-height:1.55}.msg .who{font-size:11px;color:var(--muted);margin-bottom:4px;letter-spacing:.5px;text-transform:uppercase}
.b h1,.b h2,.b h3{margin:10px 0 6px;font-size:15px}.b p{margin:6px 0}.b code{background:#1b1b25;border:1px solid var(--line);border-radius:5px;padding:1px 5px;font-family:var(--mono);font-size:12.5px}
.b pre{background:#0e0e14;border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;font-family:var(--mono);font-size:12.5px;line-height:1.5}.b pre code{background:none;border:0;padding:0}
.b ul,.b ol{margin:6px 0;padding-left:22px}.b a{color:var(--c)}
.tool{font-family:var(--mono);font-size:12px;color:var(--muted);margin:4px 0 4px 2px;border-left:2px solid var(--line);padding-left:10px}
.tool .n{color:var(--c)}.tool details{margin-top:2px}.tool summary{cursor:pointer;color:var(--muted);list-style:none}.tool summary::before{content:"⎿ ";opacity:.7}.tool pre{white-space:pre-wrap;margin:4px 0 0;color:#b9b9cc;max-height:280px;overflow:auto}
.notice{font-size:12px;color:var(--muted);margin:6px 0;white-space:pre-wrap;font-family:var(--mono)}.notice.warn{color:var(--warn)}.notice.error{color:var(--bad)}.notice.ok{color:var(--ok)}.notice.info{color:var(--c)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:10px 0;max-width:860px}
.card.perm{border-color:var(--warn)}.card.danger{border-color:var(--bad)}.card h4{margin:0 0 8px;font-size:13px;letter-spacing:.3px}.card pre{background:#0e0e14;border:1px solid var(--line);border-radius:8px;padding:10px;max-height:300px;overflow:auto;font-family:var(--mono);font-size:12px}
.card .row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}.card.resolved{opacity:.55}.card.resolved .row{display:none}
.diff .add{color:var(--ok)}.diff .del{color:var(--bad)}.diff .hunk{color:var(--c)}
.side h3{margin:14px 0 8px;font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--muted)}
.score{display:flex;align-items:baseline;gap:8px}.score b{font-size:28px;font-weight:900}.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;margin:6px 0 10px}.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--m),var(--c))}
.chk{display:flex;gap:6px;color:var(--muted);margin:2px 0;font-size:12px}.chk.ok{color:var(--text)}.chk span:first-child{width:14px}
.mem{border-left:2px solid var(--line);padding-left:8px;margin:6px 0;font-size:12px;color:#c9c9da}.mem small{color:var(--muted);text-transform:uppercase;font-size:10px;letter-spacing:.5px}.mem button{float:right;padding:0 6px;font-size:11px;border:0;background:none;color:var(--muted)}
.todo{font-size:12px;margin:3px 0}.todo.done{color:var(--muted);text-decoration:line-through}
.thinking{color:var(--muted);font-size:12px;font-family:var(--mono)}.thinking::after{content:"";display:inline-block;width:1em;animation:dots 1.2s steps(4,end) infinite}
@keyframes dots{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}}
.quick{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.quick button{padding:5px 9px;font-size:11px;border-radius:8px}
@media(max-width:900px){body{grid-template-columns:1fr;grid-template-areas:"top" "chat" "composer"}#side{display:none}}
</style></head>
<body>
<header><div class="brand"><b>CH</b><i>ODE</i><small>the Deck · v__VERSION__</small></div>
<div class="pill" id="modelPill">model</div>
<div class="pill">mode <select id="mode"><option>plan</option><option>ask</option><option>edits</option><option>yolo</option></select></div>
<div class="pill" id="costPill">$0.000</div><div class="pill" id="ctxPill">ctx 0%</div>
<div class="spacer"></div><div class="pill"><span class="dot" id="dot"></span><span id="busyText">idle</span></div></header>
<main id="chat"></main>
<aside id="side" class="side">
 <h3>ORDER</h3><div class="score"><b id="score">–</b><span id="scoreLabel" style="color:var(--muted)"></span></div><div class="bar"><i id="scoreBar" style="width:0"></i></div><div id="checks"></div>
 <div class="quick"><button onclick="send('/order')">/order</button><button onclick="send('/ship')">/ship</button><button onclick="send('/backup')">/backup</button><button onclick="send('/tidy')">/tidy</button><button onclick="post('undo',{})">undo</button></div>
 <h3>todos</h3><div id="todos" style="color:var(--muted)">–</div>
 <h3>memory</h3><div id="mems" style="color:var(--muted)">–</div>
 <h3>session</h3><div id="sess" style="color:var(--muted);font-size:12px"></div>
</aside>
<div id="composer"><textarea id="box" placeholder="tell CHODE what to build… (Enter to send, Shift+Enter for a new line, / for commands)"></textarea><button class="primary" id="sendBtn">send</button></div>
<script>
const T='__TOKEN__';const api=p=>`/t/${T}/${p}`;
const chat=document.getElementById('chat');let cur=null,curText='';let thinkingEl=null;
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function md(s){s=esc(s);const fences=[];s=s.replace(/```([\w-]*)\n([\s\S]*?)```/g,(m,l,c)=>{fences.push(`<pre><code>${c}</code></pre>`);return `\u0000${fences.length-1}\u0000`});
 s=s.replace(/^### (.*)$/gm,'<h3>$1</h3>').replace(/^## (.*)$/gm,'<h2>$1</h2>').replace(/^# (.*)$/gm,'<h1>$1</h1>');
 s=s.replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>').replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
 s=s.replace(/^(?:[-*] .*(?:\n|$))+/gm,b=>'<ul>'+b.trim().split('\n').map(l=>'<li>'+l.replace(/^[-*] /,'')+'</li>').join('')+'</ul>');
 s=s.replace(/^(?:\d+[.)] .*(?:\n|$))+/gm,b=>'<ol>'+b.trim().split('\n').map(l=>'<li>'+l.replace(/^\d+[.)] /,'')+'</li>').join('')+'</ol>');
 s=s.split(/\n{2,}/).map(p=>/^<(h\d|ul|ol|pre)/.test(p.trim())||/\u0000/.test(p)?p:`<p>${p.replace(/\n/g,'<br>')}</p>`).join('');
 return s.replace(/\u0000(\d+)\u0000/g,(m,i)=>fences[i])}
function add(html,cls){const d=document.createElement('div');d.className=cls||'';d.innerHTML=html;chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d}
function ensureBot(){if(!cur){cur=add('<div class="who">chode</div><div class="b"></div>','msg bot');curText=''}return cur.querySelector('.b')}
function diffHtml(d){return d.split('\n').map(l=>{const c=l.startsWith('+')&&!l.startsWith('+++')?'add':l.startsWith('-')&&!l.startsWith('---')?'del':l.startsWith('@@')?'hunk':'';return `<span class="${c}">${esc(l)}</span>`}).join('\n')}
function handle(ev){switch(ev.kind){
 case 'user':cur=null;add(`<div class="who">you</div><div class="b">${esc(ev.text)}</div>`,'msg user');break;
 case 'text_start':cur=null;ensureBot();break;
 case 'text_delta':{const b=ensureBot();curText+=ev.text;b.innerHTML=md(curText);chat.scrollTop=chat.scrollHeight;break}
 case 'text_end':{const b=ensureBot();b.innerHTML=md(ev.text||curText);if(ev.dimmed)b.style.opacity=.75;cur=null;break}
 case 'tool_start':cur=null;add(`<span class="n">${esc(ev.name)}</span> ${esc(ev.preview||'')}`,'tool').dataset.name=ev.name;break;
 case 'tool_result':{const els=[...chat.querySelectorAll('.tool')].reverse();const el=els.find(e=>e.dataset.name===ev.name&&!e.querySelector('details'));const first=(ev.result||'').split('\n')[0].slice(0,140);(el||add('','tool')).insertAdjacentHTML('beforeend',`<details><summary>${esc(first)}</summary><pre>${esc(ev.result||'')}</pre></details>`);break}
 case 'tool_denied':add(`denied ${esc(ev.name)}`,'notice warn');break;
 case 'notice':add(esc(ev.text||''),'notice '+(ev.level||''));break;
 case 'todos':renderTodos(ev.todos);break;
 case 'thinking':if(ev.on){if(!thinkingEl)thinkingEl=add(esc(ev.label||'thinking'),'thinking')}else if(thinkingEl){thinkingEl.remove();thinkingEl=null}break;
 case 'permission':perm(ev);break;
 case 'question':question(ev);break;
 case 'resolved':{const c=document.getElementById('p-'+ev.id);if(c)c.classList.add('resolved');break}
 case 'busy':document.getElementById('dot').classList.toggle('on',ev.on);document.getElementById('busyText').textContent=ev.on?'working':'idle';break;
 case 'status':renderStatus(ev);break;}}
function perm(ev){cur=null;const dang=!!ev.danger;const c=add(`<h4>${dang?'⚠ DANGEROUS — ':''}allow <code>${esc(ev.name)}</code>?</h4><div class="notice">${esc(ev.describe||'')}</div>${ev.outside?`<div class="notice warn">⚠ writes outside the working directory: ${esc(ev.outside)}</div>`:''}${ev.sensitive?`<div class="notice warn">⚠ this file usually holds secrets (${esc(ev.sensitive)})</div>`:''}${dang?`<div class="notice error">${esc(ev.danger)}</div>`:''}${ev.diff?`<pre class="diff">${diffHtml(ev.diff)}</pre>`:''}<div class="row"></div>`,'card perm'+(dang?' danger':''));
 c.id='p-'+ev.id;const row=c.querySelector('.row');const mk=(l,a,cls)=>{const b=document.createElement('button');b.textContent=l;if(cls)b.className=cls;b.onclick=()=>post('answer',{id:ev.id,answer:a});row.appendChild(b)};
 if(dang){mk('yes, run it','yes','');mk('deny','n','primary')}else{mk('allow','y','primary');mk('always this tool','a','');if(ev.can_prefix)mk(`always "${ev.prefix_word}…"`,'p','');mk('deny','n','')}}
function question(ev){cur=null;const c=add(`<h4>CHODE asks</h4><div>${esc(ev.question)}</div><div class="row"><input id="q-${ev.id}" style="flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:8px;font:inherit"><button class="primary">answer</button></div>`,'card');c.id='p-'+ev.id;const inp=c.querySelector('input');const go=()=>post('answer',{id:ev.id,answer:inp.value});c.querySelector('button').onclick=go;inp.onkeydown=e=>{if(e.key==='Enter')go()};inp.focus()}
function renderTodos(t){const el=document.getElementById('todos');if(!t||!t.length){el.textContent='–';return}el.innerHTML=t.map(x=>`<div class="todo ${x.status}">${x.status==='done'?'☑':x.status==='in_progress'?'◐':'☐'} ${esc(x.text)}</div>`).join('')}
function renderStatus(s){document.getElementById('modelPill').textContent=`${s.provider} · ${s.model}`;document.getElementById('mode').value=s.mode;document.getElementById('costPill').textContent=s.plan?'plan':'$'+(s.cost||0).toFixed(3);document.getElementById('ctxPill').textContent='ctx '+(s.ctx||0)+'%';
 if(s.order){document.getElementById('score').textContent=s.order.score;document.getElementById('scoreLabel').textContent=s.order.label;document.getElementById('scoreBar').style.width=s.order.score+'%';document.getElementById('checks').innerHTML=(s.order.checks||[]).map(c=>`<div class="chk ${c.ok?'ok':''}"><span>${c.ok?'✓':'✗'}</span><span>${esc(c.label)}</span></div>`).join('')}
 const m=document.getElementById('mems');m.innerHTML=(s.memories||[]).length?s.memories.map(e=>`<div class="mem"><small>${esc(e.kind||'')}${e.scope==='global'?' · global':''}</small><button title="forget" onclick="post('forget',{id:'${e.id}'})">×</button><div>${esc(e.text)}</div></div>`).join(''):'<span style="color:var(--muted)">nothing yet — CHODE remembers as you work</span>';
 renderTodos(s.todos);document.getElementById('sess').innerHTML=`${esc(s.cwd)}<br>${s.tokens_in.toLocaleString()} in · ${s.tokens_out.toLocaleString()} out<br>hi ${esc(s.name)} 👋`}
async function post(p,body){const r=await fetch(api(p),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json()}
function send(text){const box=document.getElementById('box');const t=(text!==undefined?text:box.value).trim();if(!t)return;if(text===undefined){box.value='';box.style.height='48px'}post('send',{message:t})}
document.getElementById('sendBtn').onclick=()=>send();const box=document.getElementById('box');box.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}};box.oninput=()=>{box.style.height='48px';box.style.height=Math.min(200,box.scrollHeight)+'px'};
document.getElementById('mode').onchange=e=>post('mode',{mode:e.target.value});
fetch(api('state')).then(r=>r.json()).then(s=>{renderStatus(s);(s.transcript||[]).forEach(handle);cur=null;});
const es=new EventSource(api('events'));es.onmessage=e=>handle(JSON.parse(e.data));es.onerror=()=>{document.getElementById('busyText').textContent='reconnecting…'};
</script></body></html>
"""
