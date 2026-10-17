"""The chat REPL: wires UI, agent loop, memory, hooks, ORDER and publishing together."""
import os
import re
import sys
import threading
import time
from pathlib import Path

from . import VERSION, conscience, state
from .agent import build_system_prompt, oneshot_ask, run_agent
from .commands import SLASH_NAMES, discover_commands, handle_slash
from .config import MODE_ICONS, PROVIDERS
from .hooks import HookRunner
from .llm import LLMClient, LLMError
from .mcp import McpManager
from .memory import append_note, instructions_block, parse_reflection, REFLECT_PROMPT
from .paths import MEMORY_FILENAME, ensure_home
from .permissions import Permissions
from .session import SessionStore
from .tools import tool_bash, _truncate
from .ui import (Spinner, TerminalUI, accent, accent_bold, blue, bold, cyan, dim, green, greeting, magenta, red,
                 set_title, yellow)

AT_FILE_RX = re.compile(r"@([\w./~\-]+)")


class Repl:
    def __init__(self, cfg, args=None, ui=None):
        self.cfg = cfg
        self.args = args
        self.ui = ui or TerminalUI()
        self.client = LLMClient(cfg)
        self.perms = Permissions(cfg, self.ui)
        self.store = SessionStore()
        self.custom_cmds = discover_commands()
        self.history = []
        self.system_ref = [""]
        self.app = state.set_app(state.App(cfg, ui=self.ui))
        self.app.client = self.client
        self.app.perms = self.perms
        self.app.history = self.history
        self.app.hooks = HookRunner(cfg, session_id=self.app.session_id)
        self.turns = 0

    # ---- lifecycle ----
    def boot(self, cont=False, quiet=False):
        ensure_home()
        a = self.app
        # lifeline: never start with a provider that can't possibly answer
        from . import lifeline
        lifeline.ensure_usable(self.cfg, notify=lambda m, lvl="warn": self.ui.notice("  🪢 " + m, lvl))
        self.client.on_fallback = lambda note: self.ui.notice("  🪢 " + note, "warn")
        if cont:
            sessions = SessionStore.list_sessions()
            if sessions:
                self.history.extend(SessionStore.load(sessions[0]))
                self.ui.notice(f"  continuing session ({len(self.history)} messages)", "dim")
            else:
                self.ui.notice("  no previous session here — starting fresh", "dim")
        a.mcp = McpManager(self.cfg if not getattr(self.args, "no_mcp", False) else {"mcp_servers": {}})
        if a.mcp.servers and not quiet:
            self.ui.notice("  starting MCP servers…", "dim")
        a.mcp.start_all(quiet=quiet)
        # ORDER: auto backup + background index
        try:
            from .order import maybe_auto_backup
            r = maybe_auto_backup(cfg=self.cfg)
            if r and r.get("ok") and not quiet:
                self.ui.notice(f"  🗄  auto-backup: {r['files']} files → {Path(r['path']).name}", "dim")
        except Exception:
            pass
        if self.cfg.get("rag", {}).get("auto_index", True):
            threading.Thread(target=self._bg_index, daemon=True).start()
        if a.hooks.has("session_start"):
            blocked, reason, extra = a.hooks.run("session_start")
            if extra:
                a.pending_context.append("[session_start hook]: " + extra)
        self.system_ref[0] = build_system_prompt(self.client, self.cfg)

    def _bg_index(self):
        try:
            idx = self.app.rag_index()
            if not idx.chunks or (time.time() - idx.built_at) > 3600:
                idx.build()
        except Exception:
            pass

    def banner(self):
        cfg, client = self.cfg, self.client
        mode_icon = MODE_ICONS[cfg["mode"]]
        model_label = client.model or "(server default)"
        print(f"  {dim('v' + VERSION)}   provider: {bold(client.provider)}   model: {bold(model_label)}   mode: {bold(cfg['mode'])} {mode_icon}"
              + (dim("   (session fallback — /provider keep to make it default)") if cfg.get("_fallback_from") else ""))
        print(f"  {dim('cwd:')} {os.getcwd()}")
        extras = []
        if instructions_block():
            extras.append(green("memory files loaded"))
        try:
            n_mem = len(self.app.memory_store().all())
            if n_mem:
                extras.append(green(f"{n_mem} memories"))
        except Exception:
            pass
        if self.app.skills:
            extras.append(cyan(f"{len(self.app.skills)} skill(s)"))
        mcp_tools = len(self.app.mcp.tool_defs()) if self.app.mcp else 0
        if mcp_tools:
            extras.append(magenta(f"{mcp_tools} MCP tool(s)"))
        if self.custom_cmds:
            extras.append(blue(f"{len(self.custom_cmds)} custom command(s)"))
        if extras:
            print("  " + dim(" · ").join(extras))
        if cfg.get("order", {}).get("auto_check", True):
            try:
                from .order import status_line
                line, audit = status_line(cfg=cfg)
                print("  " + dim(line) + (dim("  → /order to fix") if audit["score"] < 75 else ""))
            except Exception:
                pass
        print(dim("  /help for commands · /gui for the browser deck · Ctrl-D or /exit to quit"))
        print("  " + accent(greeting(cfg)) + "\n")
        set_title(f"chode · {Path.cwd().name}")

    # ---- turns ----
    def run_turn(self, message):
        a = self.app
        if a.hooks.has("user_prompt"):
            blocked, reason, extra = a.hooks.run("user_prompt", prompt=message)
            if blocked:
                self.ui.notice(f"  ⛔ hook blocked the prompt: {reason}", "warn")
                return
            if extra:
                message = extra + "\n\n" + message
        self.history.append({"role": "user", "content": message})
        before = len(a.touched_files)
        try:
            run_agent(self.client, self.perms, self.system_ref[0], self.history, ui=self.ui)
        except LLMError as e:
            from . import lifeline
            self.ui.notice(f"\n🪢 the model didn't answer — {e.pretty()}", "error")
            self.ui.notice("\n" + lifeline.playbook(self.cfg, e) + "\n  (type /fix and CHODE will try to repair this itself)", "warn")
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
        except KeyboardInterrupt:
            self.ui.notice("\ninterrupted — history kept, ask away", "warn")
            self._repair_history()
        self.turns += 1
        self.store.save(self.history, model=self.client.model, provider=self.client.provider,
                        cost=round(self.client.total_cost, 4))
        if len(a.touched_files) > before and self.cfg.get("publish", {}).get("autocommit") == "turn":
            from .publish import autocommit
            msg = autocommit(cfg=self.cfg, summary=message.splitlines()[0][:60])
            if msg:
                self.ui.notice("  " + msg, "dim")
        self.status_line()

    def _repair_history(self):
        """After an interrupt mid-tool-loop the last assistant message may have unanswered tool calls."""
        if self.history and self.history[-1]["role"] == "assistant" and self.history[-1].get("tool_calls"):
            for tc in self.history[-1]["tool_calls"]:
                self.history.append({"role": "tool", "tool_call_id": tc["id"], "name": tc["name"],
                                     "content": "(interrupted by user before this ran)"})

    def status_line(self):
        c = self.client
        bits = [c.model, self.cfg["mode"], f"ctx {c.last_input_tokens//1000}k ({c.context_pct()}%)"]
        if c.api_style == "plan":
            bits.append("plan")
        elif c.total_cost:
            bits.append(f"${c.total_cost:.3f}")
        print(dim("  ⟨ " + " · ".join(bits) + " ⟩"))

    def preprocess_input(self, user):
        """Handles shortcuts. Returns the message to send, or None if fully handled."""
        a = self.app
        if user.startswith("!"):
            cmd = user[1:].strip()
            out = tool_bash({"command": cmd})
            print(dim(out[:3000]))
            a.pending_context.append(f"I ran `{cmd}` myself; output:\n{out[:8000]}")
            return None
        if user.startswith("#"):
            note = user[1:].strip()
            if note:
                mem = append_note(note)
                print(dim(f"noted in {mem}"))
                try:
                    a.memory_store().add(note, kind="fact", scope="project", source="user")
                except Exception:
                    pass
            return None
        attachments = []
        for m in AT_FILE_RX.finditer(user):
            p = Path(m.group(1)).expanduser()
            if p.is_file():
                try:
                    attachments.append(f"\n\n--- contents of {p} ---\n{_truncate(p.read_text(errors='replace', encoding='utf-8'), 15000)}")
                except Exception:
                    pass
            elif p.is_dir():
                try:
                    listing = "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())[:200])
                    attachments.append(f"\n\n--- listing of {p} ---\n{listing}")
                except Exception:
                    pass
        msg = user + "".join(attachments)
        if a.pending_context:
            msg = "\n\n".join(a.pending_context) + "\n\n" + msg
            a.pending_context.clear()
        return msg

    # ---- wrap-up ----
    def wrap_up(self):
        a = self.app
        if a.hooks.has("session_end"):
            a.hooks.run("session_end")
        if self.cfg.get("publish", {}).get("autocommit") == "session" and a.touched_files:
            from .publish import autocommit
            msg = autocommit(cfg=self.cfg, summary="session changes")
            if msg:
                self.ui.notice("  " + msg, "dim")
        user_turns = sum(1 for m in self.history if m["role"] == "user")
        if a.oneshot or user_turns < 3 or self.client.api_style == "plan":
            return
        try:
            if self.cfg.get("memory", {}).get("auto_reflect", True):
                with Spinner("reflecting on what to remember"):
                    hist = [m for m in self.history if m["role"] in ("user", "assistant")][-24:]
                    text = self.client.chat(self.system_ref[0], hist + [{"role": "user", "content": REFLECT_PROMPT}], tools=None)["content"]
                saved = 0
                store = a.memory_store()
                for item in parse_reflection(text):
                    if store.add(item["text"], kind=item["kind"], scope=item["scope"], source="reflection"):
                        saved += 1
                if saved:
                    self.ui.notice(f"  🧠 remembered {saved} thing(s) for next time (/memories)", "dim")
            if self.cfg.get("conscience", {}).get("reflect", True) and a.session_events:
                with Spinner("updating conscience"):
                    text = oneshot_ask(self.client, conscience.reflect_prompt(a.session_events), max_tokens=120)
                if conscience.apply_reflection(text):
                    self.ui.notice("  🪞 conscience updated (/conscience)", "dim")
        except (LLMError, KeyboardInterrupt):
            pass
        except Exception:
            pass

    # ---- main loop ----
    def loop(self):
        self._setup_readline()
        try:
            while True:
                try:
                    user = read_input().strip()
                except (EOFError, KeyboardInterrupt):
                    print(dim("\nbye 👋"))
                    break
                if not user:
                    continue
                if user.startswith("/"):
                    try:
                        keep, msg = handle_slash(user, self)
                    except KeyboardInterrupt:
                        print()
                        continue
                    if not keep:
                        print(dim("bye 👋"))
                        break
                    if msg:
                        self.run_turn(msg)
                        self.system_ref[0] = build_system_prompt(self.client, self.cfg)
                    continue
                msg = self.preprocess_input(user)
                if msg is None:
                    continue
                self.run_turn(msg)
        finally:
            try:
                self.wrap_up()
            finally:
                self.store.save(self.history, model=self.client.model, provider=self.client.provider)
                if self.app.mcp:
                    self.app.mcp.stop_all()
                self.app.checkpoints.cleanup()

    def _setup_readline(self):
        try:
            import readline as _rl
            names = SLASH_NAMES + ["/" + k for k in self.custom_cmds]

            def _complete(text, state_):
                if text.startswith("/"):
                    hits = [c2 for c2 in names if c2.startswith(text)]
                elif text.startswith("@"):
                    frag = text[1:]
                    base = Path(frag).parent if "/" in frag else Path(".")
                    pre = Path(frag).name if "/" in frag else frag
                    try:
                        hits = ["@" + str(p) + ("/" if p.is_dir() else "")
                                for p in base.iterdir() if p.name.startswith(pre)][:50]
                    except Exception:
                        hits = []
                else:
                    hits = []
                return hits[state_] if state_ < len(hits) else None
            _rl.set_completer(_complete)
            _rl.set_completer_delims(" ")
            _rl.parse_and_bind("tab: complete")
        except Exception:
            pass


def read_input():
    lines = []
    prompt = f"{accent_bold('you')} {dim('›')} "
    while True:
        line = input(prompt if not lines else f"{dim('...')} ")
        if line.endswith("\\"):
            lines.append(line[:-1])
            continue
        lines.append(line)
        return "\n".join(lines)


def start_chat(cfg, args, cont=False, oneshot=None):
    repl = Repl(cfg, args)
    if oneshot:
        repl.app.oneshot = True
        repl.ui.quiet = True
        if not sys.stdin.isatty():
            # nobody can answer a permission prompt → deny unsafe actions instead of hanging forever
            repl.ui.interactive = False
            if cfg["mode"] in ("ask", "edits"):
                repl.ui.notice(f"  (non-interactive: actions that need approval are denied in mode '{cfg['mode']}' — use --mode yolo or --mode edits)", "dim")
        repl.boot(cont=cont or getattr(args, "cont", False), quiet=True)
        try:
            repl.run_turn(oneshot)
        finally:
            repl.store.save(repl.history, model=repl.client.model, provider=repl.client.provider)
            if repl.app.mcp:
                repl.app.mcp.stop_all()
        return
    repl.boot(cont=cont or getattr(args, "cont", False))
    repl.banner()
    repl.loop()
