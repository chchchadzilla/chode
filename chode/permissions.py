"""Permissions: modes, allow/deny lists, dangerous-command guard, diff preview."""
import difflib
import json
from pathlib import Path

from . import conscience
from .config import save_config
from .security import (command_denied, command_matches_prefix, dangerous_command, path_inside_cwd,
                       sensitive_path)
from .tools import tool_def
from .ui import cyan, dim, green, red

FILE_TOOLS = {"write_file", "edit_file"}


def render_diff(name, args, max_lines=80):
    """Unified diff preview for file changes (colored for the terminal)."""
    try:
        p = Path(args.get("path", "")).expanduser()
        if name == "edit_file":
            if not p.exists():
                return ""
            old = p.read_text(errors="replace", encoding="utf-8")
            if old.count(args["old_str"]) != 1:
                return ""
            new = old.replace(args["old_str"], args["new_str"], 1)
        elif name == "write_file":
            old = p.read_text(errors="replace", encoding="utf-8") if p.exists() else ""
            new = args.get("content", "")
        else:
            return ""
        diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                         fromfile=str(p), tofile=str(p), lineterm="", n=3))
        if not diff:
            return dim("  (no changes)")
        out = []
        for line in diff[:max_lines]:
            if line.startswith("+") and not line.startswith("+++"):
                out.append("  " + green(line))
            elif line.startswith("-") and not line.startswith("---"):
                out.append("  " + red(line))
            elif line.startswith("@@"):
                out.append("  " + cyan(line))
            else:
                out.append("  " + dim(line))
        if len(diff) > max_lines:
            out.append(dim(f"  … {len(diff)-max_lines} more diff lines"))
        return "\n".join(out)
    except Exception:
        return ""


def plain_diff(name, args, max_lines=400):
    """Uncolored diff (for the GUI)."""
    try:
        p = Path(args.get("path", "")).expanduser()
        if name == "edit_file":
            if not p.exists():
                return ""
            old = p.read_text(errors="replace", encoding="utf-8")
            if old.count(args["old_str"]) != 1:
                return ""
            new = old.replace(args["old_str"], args["new_str"], 1)
        elif name == "write_file":
            old = p.read_text(errors="replace", encoding="utf-8") if p.exists() else ""
            new = args.get("content", "")
        else:
            return ""
        diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=str(p), tofile=str(p), lineterm="", n=3))
        return "\n".join(diff[:max_lines])
    except Exception:
        return ""


class Permissions:
    def __init__(self, cfg, ui=None):
        self.cfg = cfg
        self.ui = ui
        self.always = set()   # tool names approved for this session

    @property
    def mode(self):
        return self.cfg["mode"]

    def decide(self, name, args):
        """Pure decision helper: returns ('allow'|'deny'|'prompt', info dict)."""
        d = tool_def(name)
        safe = bool(d and d.get("safe"))
        info = {"danger": None, "outside": None, "deny": None, "sensitive": None}
        if self.mode == "plan" and not safe:
            return "deny", dict(info, reason="plan mode is read-only")
        if safe:
            return "allow", info
        cmd = args.get("command", "") if name == "bash" else ""
        if name == "bash":
            info["deny"] = command_denied(cmd, self.cfg.get("bash_deny", []))
            if info["deny"]:
                return "deny", dict(info, reason=f"'{info['deny']}' is on the deny list")
            info["danger"] = dangerous_command(cmd)
        if name in FILE_TOOLS:
            p = Path(args.get("path", ".")).expanduser()
            if not self.cfg.get("allow_outside_cwd") and not path_inside_cwd(p):
                info["outside"] = str(p)
            if sensitive_path(p):
                info["sensitive"] = p.name
        if info["danger"] or info["outside"] or info["sensitive"]:
            return "prompt", info
        if self.mode == "yolo" or name in self.always:
            return "allow", info
        if self.mode == "edits" and name in FILE_TOOLS:
            return "allow", info
        if name == "bash" and command_matches_prefix(cmd, self.cfg.get("bash_allow", [])):
            return "allow", info
        return "prompt", info

    def ask(self, name, args):
        verdict, info = self.decide(name, args)
        if verdict == "allow":
            return True
        if verdict == "deny":
            if self.ui:
                self.ui.notice(f"  blocked: {name} — {info.get('reason')}", "dim")
            if info.get("deny"):
                conscience.log("deny_list", command=args.get("command", "")[:300], detail=info["deny"])
            return False
        if not self.ui or not getattr(self.ui, "interactive", True):
            if info.get("danger"):
                conscience.log("danger_denied", command=args.get("command", "")[:300], detail=info["danger"] + " (non-interactive)")
            else:
                conscience.log("denied", tool=name, detail="non-interactive")
            return False
        req = {"name": name, "args": args, "describe": self.describe(name, args),
               "diff": render_diff(name, args) if name in FILE_TOOLS else "",
               "plain_diff": plain_diff(name, args) if name in FILE_TOOLS else "",
               "outside": info.get("outside"), "danger": info.get("danger"), "sensitive": info.get("sensitive"),
               "can_prefix": name == "bash" and not info.get("danger"),
               "prefix_word": (args.get("command", "").strip().split() or [""])[0] if name == "bash" else ""}
        ans = self.ui.ask_permission(req)
        if info.get("danger"):
            conscience.log("danger_allowed" if ans == "y" else "danger_denied",
                           command=args.get("command", "")[:300], detail=info["danger"])
        if info.get("outside") and ans in ("y", "a"):
            conscience.log("outside_cwd", path=info["outside"], tool=name)
        if ans == "n":
            if not info.get("danger"):
                conscience.log("denied", tool=name, detail=self.describe(name, args, plain=True)[:200])
            return False
        if ans == "a":
            self.always.add(name)
        elif ans == "p" and name == "bash":
            first = req["prefix_word"]
            if first:
                self.cfg.setdefault("bash_allow", []).append(first)
                try:
                    save_config(self.cfg)
                except Exception:
                    pass
                if self.ui:
                    self.ui.notice(f"  commands starting with `{first}` now auto-approved (saved)", "dim")
        return True

    @staticmethod
    def describe(name, args, plain=False):
        if name == "bash":
            return "\n  " + (("$ " + args.get("command", "")[:500]) if plain else cyan("$ " + args.get("command", "")[:500]))
        if name in FILE_TOOLS:
            return f"→ {args.get('path','?')}" if plain else dim(f"→ {args.get('path','?')}")
        if name == "web_fetch":
            return args.get("url", "") if plain else dim(args.get("url", ""))
        if name == "ship":
            return "commit + push" if plain else dim("commit + push")
        s = json.dumps(args)[:200]
        return s if plain else dim(s)
