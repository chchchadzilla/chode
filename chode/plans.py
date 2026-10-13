"""Plan Bridge — ride the AI subscription you already pay for.

No API key. CHODE drives the official CLIs (`claude`, `codex`, `gemini`, or any
custom one) in non-interactive mode and attaches ITSELF as an MCP server, so the
vendor's model thinks with its plan and acts through CHODE's tools — with
CHODE's permission lanes, memory, ORDER and ledger wrapped around it.

Two ways to use it:
  * provider = claude-plan / codex-plan / gemini-plan  → the vendor CLI is CHODE's "model"
  * `chode ride claude|codex|gemini`                  → hand off to the vendor's own TUI with
                                                        CHODE's tools + memory mounted via MCP
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .config import PROVIDERS
from . import conscience

PLAN_CLIS = {
    "claude-plan": ("claude", "Claude Code — Claude Pro/Max", "npm i -g @anthropic-ai/claude-code  → then: claude login"),
    "codex-plan":  ("codex",  "Codex CLI — ChatGPT Plus/Pro", "npm i -g @openai/codex  → then: codex login"),
    "gemini-plan": ("gemini", "Gemini CLI — Google AI Pro/Ultra", "npm i -g @google/gemini-cli  → then: gemini (sign in)"),
    "custom-plan": (None, "any agent CLI", "set plans.custom.command in config"),
}
TEMPLATE_KEYS = {"claude-plan": "claude", "codex-plan": "codex", "gemini-plan": "gemini", "custom-plan": "custom"}


def _which(cmd):
    if not cmd:
        return None
    for cand in (cmd, cmd + ".cmd", cmd + ".exe"):
        hit = shutil.which(cand)
        if hit:
            return hit
    return None


def detect_plans():
    """[(provider, cli, path_or_None, label, install_hint)]"""
    out = []
    for prov, (cli, label, hint) in PLAN_CLIS.items():
        out.append((prov, cli, _which(cli) if cli else None, label, hint))
    return out


def chode_mcp_spec(mode="edits", cwd=None):
    """How a vendor CLI should launch CHODE's MCP server."""
    return {"command": sys.executable, "args": ["-m", "chode", "mcp-serve", "--mode", mode],
            "env": {"CHODE_MCP_CWD": str(cwd or Path.cwd()), "PYTHONIOENCODING": "utf-8"}}


def write_mcp_config(mode="edits", cwd=None, fmt="claude"):
    """Write a temp MCP config file in the vendor's format and return its path."""
    spec = chode_mcp_spec(mode, cwd)
    if fmt == "codex":  # codex uses TOML config overrides instead; handled in command building
        return ""
    data = {"mcpServers": {"chode": {"type": "stdio", **spec}}}
    fd, path = tempfile.mkstemp(prefix="chode-mcp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def render_command(template, **values):
    """Split a shell-ish template into argv and substitute {placeholders} token-wise,
    so prompts with quotes/newlines never get mangled by the shell."""
    try:
        tokens = shlex.split(template, posix=True)
    except ValueError:
        tokens = template.split()
    argv = []
    for tok in tokens:
        if tok.startswith("{") and tok.endswith("}") and tok[1:-1] in values:
            v = values[tok[1:-1]]
            if v is None or v == "":
                continue
            if isinstance(v, list):
                argv.extend(v)
            else:
                argv.append(str(v))
        else:
            for k, v in values.items():
                if "{" + k + "}" in tok and isinstance(v, str):
                    tok = tok.replace("{" + k + "}", v)
            argv.append(tok)
    return argv


class PlanClient:
    def __init__(self, cfg, provider):
        self.cfg = cfg
        self.provider = provider
        self.key = TEMPLATE_KEYS.get(provider, "custom")
        self.tpl = (cfg.get("plans") or {}).get(self.key) or {}
        self.cli = PLAN_CLIS.get(provider, (None,))[0]
        self.session_id = None
        self.turns = 0

    def _check(self):
        if self.key == "custom":
            if not self.tpl.get("command"):
                raise RuntimeError("custom-plan has no command template. Set plans.custom.command in ~/.chode/config.json, "
                                   "e.g. \"mycli --prompt {prompt}\"")
            return
        if not _which(self.cli):
            _, label, hint = PLAN_CLIS[self.provider]
            raise RuntimeError(f"`{self.cli}` CLI not found ({label}). Install it: {hint}")

    def _model_tokens(self):
        model = self.cfg.get("model") or PROVIDERS[self.provider][3]
        flag = self.tpl.get("model_flag") or ""
        if not model or not flag:
            return []
        return render_command(flag, model=model)

    def _resume_tokens(self):
        flag = self.tpl.get("resume_flag") or ""
        if not self.session_id or not flag:
            return []
        return render_command(flag, id=self.session_id)

    def _build_prompt(self, system, messages):
        """The vendor CLI keeps its own history only if we can resume; otherwise we pack
        a compact transcript so the conversation still makes sense."""
        latest = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        parts = []
        include_system = self.turns == 0 or not self.session_id
        if include_system and system:
            parts.append("<chode_context>\n" + system[:14000] + "\n</chode_context>")
        if not self.session_id and len(messages) > 1:
            prior = []
            for m in messages[:-1]:
                if m["role"] == "user":
                    prior.append(f"USER: {m['content'][:1500]}")
                elif m["role"] == "assistant" and m.get("content"):
                    prior.append(f"ASSISTANT: {m['content'][:1500]}")
            if prior:
                parts.append("<previous_conversation>\n" + "\n\n".join(prior[-12:]) + "\n</previous_conversation>")
        parts.append(latest)
        return "\n\n".join(parts)

    def chat(self, system, messages, on_text=None):
        self._check()
        mode = self.cfg.get("mode", "ask")
        bridge_mode = {"plan": "plan", "ask": "edits", "edits": "edits", "yolo": "yolo"}[mode]
        prompt = self._build_prompt(system, messages)
        mcp_path = write_mcp_config(bridge_mode, fmt=self.key)
        extra_codex = []
        if self.key == "codex":
            spec = chode_mcp_spec(bridge_mode)
            extra_codex = ["-c", f'mcp_servers.chode.command="{spec["command"]}"',
                           "-c", "mcp_servers.chode.args=" + json.dumps(spec["args"]),
                           "-c", f'mcp_servers.chode.env={json.dumps(spec["env"])}']
            if mode == "yolo":
                extra_codex += ["--dangerously-bypass-approvals-and-sandbox"]
            elif mode == "plan":
                extra_codex += ["-s", "read-only"]
            else:
                extra_codex += ["--full-auto"]
        argv = render_command(self.tpl.get("command", ""), prompt=prompt, model=self._model_tokens(),
                              resume=self._resume_tokens(), mcp_config=mcp_path, system=system[:14000] if system else "",
                              cwd=str(Path.cwd()))
        if extra_codex:
            argv = [argv[0]] + extra_codex + argv[1:] if argv else argv
        if self.key == "claude" and mode == "yolo" and "--permission-mode" not in argv:
            argv += ["--permission-mode", "bypassPermissions"]
        if argv and _which(argv[0]):
            argv[0] = _which(argv[0])
        conscience.log("plan_bridge", provider=self.provider, detail=" ".join(argv[:2]))
        t0 = time.time()
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=3600,
                                  cwd=str(Path.cwd()), encoding="utf-8", errors="replace")
        except FileNotFoundError:
            raise RuntimeError(f"could not run {argv[0]!r}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("plan bridge timed out after 1h")
        finally:
            if mcp_path:
                try:
                    os.unlink(mcp_path)
                except Exception:
                    pass
        self.turns += 1
        if proc.returncode != 0 and not proc.stdout.strip():
            err = (proc.stderr or "").strip()[-1500:]
            raise RuntimeError(f"{self.cli or 'plan cli'} exited {proc.returncode}: {err or 'no output'}")
        parsed = self._parse(proc.stdout, proc.stderr)
        parsed["secs"] = time.time() - t0
        if on_text and parsed.get("content"):
            on_text(parsed["content"])
        return parsed

    # ---- output parsing per CLI ----
    def _parse(self, stdout, stderr):
        text = stdout.strip()
        res = {"content": "", "usage_in": 0, "usage_out": 0, "cost": None}
        if self.key == "claude":
            obj = _last_json_object(text)
            if obj:
                res["content"] = str(obj.get("result") or "")
                self.session_id = obj.get("session_id") or self.session_id
                u = obj.get("usage") or {}
                res["usage_in"] = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                res["usage_out"] = u.get("output_tokens", 0)
                res["cost"] = 0.0  # covered by the plan
                if obj.get("is_error"):
                    res["content"] = "Claude Code reported an error:\n" + res["content"]
                return res
        elif self.key == "codex":
            msgs = []
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("type") == "thread.started":
                    self.session_id = ev.get("thread_id") or self.session_id
                item = ev.get("item") or {}
                if ev.get("type") in ("item.completed",) and item.get("type") == "agent_message":
                    msgs.append(item.get("text", ""))
                if ev.get("type") == "turn.completed":
                    u = ev.get("usage") or {}
                    res["usage_in"] = u.get("input_tokens", 0)
                    res["usage_out"] = u.get("output_tokens", 0)
            if msgs:
                res["content"] = "\n\n".join(m for m in msgs if m)
                res["cost"] = 0.0
                return res
        elif self.key == "gemini":
            obj = _last_json_object(text)
            if obj and ("response" in obj or "result" in obj):
                res["content"] = str(obj.get("response") or obj.get("result") or "")
                self.session_id = obj.get("session_id") or obj.get("sessionId") or self.session_id
                stats = obj.get("stats") or {}
                res["usage_in"] = int(stats.get("input_tokens") or stats.get("promptTokenCount") or 0)
                res["usage_out"] = int(stats.get("output_tokens") or stats.get("candidatesTokenCount") or 0)
                res["cost"] = 0.0
                return res
        # fallback: whatever the CLI printed is the answer
        res["content"] = text or (stderr or "").strip()[-2000:] or "(no output)"
        res["cost"] = 0.0
        return res

    def list_models(self):
        return {"claude": ["sonnet", "opus", "haiku", "fable"],
                "codex": ["gpt-5-codex", "gpt-5", "o3"],
                "gemini": ["gemini-2.5-pro", "gemini-2.5-flash"],
                "custom": []}.get(self.key, [])


def _last_json_object(text):
    """Find the last top-level JSON object in a blob of CLI output."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    start = text.rfind("\n{")
    if start != -1:
        try:
            return json.loads(text[start + 1:])
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------
# `chode ride <cli>` — interactive handoff with CHODE mounted as MCP
# --------------------------------------------------------------------------

def ride(which, cfg, extra_args=None):
    """Launch the vendor's own interactive TUI with CHODE's tools+memory attached."""
    extra_args = extra_args or []
    mode = cfg.get("mode", "ask")
    bridge_mode = {"plan": "plan", "ask": "edits", "edits": "edits", "yolo": "yolo"}[mode]
    spec = chode_mcp_spec(bridge_mode)
    from .agent import build_system_prompt_lite
    context = build_system_prompt_lite(cfg)
    if which == "claude":
        exe = _which("claude")
        if not exe:
            return "claude CLI not found — npm i -g @anthropic-ai/claude-code"
        path = write_mcp_config(bridge_mode)
        argv = [exe, "--mcp-config", path, "--append-system-prompt", context] + extra_args
    elif which == "codex":
        exe = _which("codex")
        if not exe:
            return "codex CLI not found — npm i -g @openai/codex"
        argv = [exe, "-c", f'mcp_servers.chode.command="{spec["command"]}"',
                "-c", "mcp_servers.chode.args=" + json.dumps(spec["args"]),
                "-c", f'mcp_servers.chode.env={json.dumps(spec["env"])}'] + extra_args
        _write_agents_hint(context)
    elif which == "gemini":
        exe = _which("gemini")
        if not exe:
            return "gemini CLI not found — npm i -g @google/gemini-cli"
        # Gemini CLI reads project-level .gemini/settings.json for MCP servers
        gdir = Path.cwd() / ".gemini"
        gdir.mkdir(exist_ok=True)
        sfile = gdir / "settings.json"
        try:
            settings = json.loads(sfile.read_text(encoding="utf-8")) if sfile.exists() else {}
        except Exception:
            settings = {}
        settings.setdefault("mcpServers", {})["chode"] = spec
        sfile.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        argv = [exe] + extra_args
        _write_agents_hint(context, name="GEMINI.md")
    else:
        return f"unknown ride target '{which}' (claude | codex | gemini)"
    conscience.log("plan_bridge", provider=which, detail="interactive ride")
    try:
        if os.name == "nt":
            return subprocess.call(argv)
        os.execv(argv[0], argv)
    except Exception as e:
        return f"could not launch {which}: {e}"


def _write_agents_hint(context, name="AGENTS.md"):
    """Codex/Gemini read AGENTS.md/GEMINI.md — drop CHODE's context in a clearly marked
    block (only if the file doesn't already have one)."""
    f = Path.cwd() / name
    marker = "<!-- chode:context -->"
    try:
        existing = f.read_text(encoding="utf-8") if f.exists() else ""
        if marker in existing:
            return
        block = f"\n\n{marker}\n<!-- added by `chode ride`; safe to delete -->\n{context[:6000]}\n<!-- /chode:context -->\n"
        f.write_text(existing + block, encoding="utf-8")
    except Exception:
        pass
