"""Lifecycle hooks — shell commands that run around CHODE's actions.

Config (user ~/.chode/config.json or project .chode/hooks.json):

    "hooks": {
      "session_start": [{"command": "echo hi"}],
      "user_prompt":   [{"command": "..."}],
      "pre_tool":      [{"match": "bash|write_file", "command": "python check.py"}],
      "post_tool":     [{"match": "edit_file", "command": "npx prettier --write $CHODE_FILE"}],
      "session_end":   [{"command": "..."}]
    }

Hook protocol (compatible with Claude Code hooks, so imported ones just work):
  * JSON on stdin: {"event", "hook_event_name", "tool", "tool_name", "args", "tool_input",
                    "tool_output", "cwd", "session_id", "prompt"}
  * env: CHODE_EVENT, CHODE_TOOL, CHODE_CWD, CHODE_FILE (path arg if any)
  * exit 2 → block the action; stderr is shown to the model as the reason
  * exit 0 with JSON stdout {"decision": "block", "reason": ...} → block
  * exit 0 with JSON stdout {"additionalContext": "..."} → text given to the model
"""
import json
import os
import re
import subprocess
from pathlib import Path

from .paths import PROJECT_DIRNAME

EVENTS = ("session_start", "user_prompt", "pre_tool", "post_tool", "session_end", "stop")

# Claude Code → CHODE tool-name aliases so imported matchers keep working.
TOOL_ALIASES = {
    "bash": ["Bash", "Shell", "PowerShell", "exec"],
    "read_file": ["Read", "View", "ReadFile"],
    "write_file": ["Write", "Create", "WriteFile"],
    "edit_file": ["Edit", "MultiEdit", "StrReplace", "Patch"],
    "glob": ["Glob", "FindFiles"],
    "grep": ["Grep", "Search"],
    "web_fetch": ["WebFetch", "Fetch", "Browse"],
    "set_todos": ["TodoWrite", "UpdatePlan"],
    "spawn_agent": ["Task", "Agent"],
}
EVENT_ALIASES = {
    "PreToolUse": "pre_tool", "PostToolUse": "post_tool", "UserPromptSubmit": "user_prompt",
    "SessionStart": "session_start", "SessionEnd": "session_end", "Stop": "stop",
}


def _normalize(raw):
    """Accept both CHODE's flat format and Claude Code's nested matcher format."""
    hooks = {e: [] for e in EVENTS}
    for event, entries in (raw or {}).items():
        ev = EVENT_ALIASES.get(event, event)
        if ev not in hooks or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if "hooks" in entry:  # Claude Code: {"matcher": "Bash", "hooks": [{"type":"command","command":..}]}
                for h in entry.get("hooks", []):
                    if isinstance(h, dict) and h.get("command"):
                        hooks[ev].append({"match": entry.get("matcher", ""), "command": h["command"],
                                          "timeout": h.get("timeout", 20)})
            elif entry.get("command"):
                hooks[ev].append({"match": entry.get("match", entry.get("matcher", "")),
                                  "command": entry["command"], "timeout": entry.get("timeout", 20)})
    return hooks


def load_hooks(cfg, cwd=None):
    merged = _normalize(cfg.get("hooks"))
    f = Path(cwd or Path.cwd()) / PROJECT_DIRNAME / "hooks.json"
    if f.exists():
        try:
            proj = _normalize(json.loads(f.read_text(encoding="utf-8")))
            for ev in EVENTS:
                merged[ev].extend(proj[ev])
        except Exception:
            pass
    return merged


def _matches(pattern, tool):
    if not pattern or pattern in ("*", ".*"):
        return True
    names = [tool] + TOOL_ALIASES.get(tool, [])
    try:
        rx = re.compile(pattern)
    except re.error:
        return pattern in names
    return any(rx.fullmatch(n) or rx.search(n) for n in names)


class HookRunner:
    def __init__(self, cfg, cwd=None, session_id=""):
        self.hooks = load_hooks(cfg, cwd)
        self.session_id = session_id
        self.cwd = str(cwd or Path.cwd())

    def has(self, event):
        return bool(self.hooks.get(event))

    def run(self, event, tool="", args=None, output="", prompt=""):
        """Returns (blocked, reason, extra_context)."""
        extra, blocked, reason = [], False, ""
        for h in self.hooks.get(event, []):
            if tool and not _matches(h.get("match", ""), tool):
                continue
            payload = {"event": event, "hook_event_name": event, "tool": tool, "tool_name": tool,
                       "args": args or {}, "tool_input": args or {}, "tool_output": output[:20000] if output else "",
                       "cwd": self.cwd, "session_id": self.session_id, "prompt": prompt}
            env = {**os.environ, "CHODE_EVENT": event, "CHODE_TOOL": tool, "CHODE_CWD": self.cwd,
                   "CHODE_FILE": str((args or {}).get("path", ""))}
            try:
                proc = subprocess.run(h["command"], shell=True, input=json.dumps(payload),
                                      capture_output=True, text=True, cwd=self.cwd, env=env,
                                      timeout=int(h.get("timeout", 20) or 20))
            except subprocess.TimeoutExpired:
                extra.append(f"[hook timed out: {h['command'][:60]}]")
                continue
            except Exception as e:
                extra.append(f"[hook failed to run: {e}]")
                continue
            out = (proc.stdout or "").strip()
            if proc.returncode == 2:
                blocked, reason = True, (proc.stderr or out or "blocked by hook").strip()[:1000]
                break
            if out.startswith("{"):
                try:
                    data = json.loads(out)
                    if data.get("decision") == "block" or data.get("continue") is False:
                        blocked, reason = True, str(data.get("reason") or data.get("stopReason") or "blocked by hook")[:1000]
                        break
                    ctx = data.get("additionalContext") or (data.get("hookSpecificOutput") or {}).get("additionalContext")
                    if ctx:
                        extra.append(str(ctx)[:4000])
                    continue
                except Exception:
                    pass
            if out and event in ("user_prompt", "session_start", "post_tool"):
                extra.append(out[:4000])
        return blocked, reason, "\n".join(extra)
