"""One-click import from every other coding harness ("the gulp").

Scans the usual homes of VS Code, Cursor, Claude Code, Codex, Antigravity, Gemini
CLI, Windsurf, Cline, Roo, Kilo, Continue, Copilot, OpenCode, Zed, Kiro, Aider,
Amp, Junie, OpenClaw and Hermes, and converts what it finds into CHODE gear:

  rules / instructions  → memory (CHODE.md sections, with provenance)
  SKILL.md folders      → skills
  commands / prompts    → slash commands
  agents / personas     → sub-agent personas
  mcpServers            → MCP servers
  permissions.allow     → bash_allow prefixes · deny → bash_deny
  hooks                 → hooks (Claude Code format works as-is)
  VS Code extensions    → report of what CHODE replaces

Looks in this machine's home + the current project by default; `chode import --drives` also searches other
mounted drives (D:, /Volumes/*, /media/*, /mnt/* …) for agent folders and SKILL.md skills, and
`chode import <folder>` takes any folder you point at (a skill, a skills folder, a copied ~/.claude, a project).
Nothing is written until you say so. Nothing is ever deleted from the source.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import save_config
from .paths import (GLOBAL_AGENTS_DIR, GLOBAL_COMMANDS_DIR, GLOBAL_MEMORY_FILE, GLOBAL_SKILLS_DIR, IS_WIN,
                    MEMORY_FILENAME, SKIP_DIRS)
from .security import redact_secrets
from .skills import discover_skills, parse_frontmatter, strip_frontmatter

HOME = Path.home()


def _vscode_user_dirs(home=None, external=False):
    """User dirs for VS Code family editors (Code, Insiders, Cursor, Windsurf, Antigravity, VSCodium).
    For a home on ANOTHER drive we can't trust env vars, so we try every platform layout under it."""
    home = Path(home or HOME)
    names = ["Code", "Code - Insiders", "Cursor", "Windsurf", "Antigravity", "VSCodium", "Trae"]
    bases = []
    if external:
        bases = [home / "AppData" / "Roaming", home / "Library" / "Application Support", home / ".config"]
    elif IS_WIN:
        bases = [Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))]
    elif sys.platform == "darwin":
        bases = [HOME / "Library" / "Application Support"]
    else:
        bases = [Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))]
    return [(n, base / n / "User") for base in bases for n in names]


# ---- where things live -------------------------------------------------------

def _user_sources(add, home, tag="", external=False):
    """Everything an agent keeps under a home directory (~ on this machine, or Users/<name> on another drive)."""
    home = Path(home)
    cfgdir = home / ".config"
    # Claude Code
    add(f"Claude Code{tag}", "rules", home / ".claude" / "CLAUDE.md")
    add(f"Claude Code{tag}", "skills_root", home / ".claude" / "skills")
    add(f"Claude Code{tag}", "commands_root", home / ".claude" / "commands")
    add(f"Claude Code{tag}", "agents_root", home / ".claude" / "agents")
    add(f"Claude Code{tag}", "settings_json", home / ".claude" / "settings.json")
    add(f"Claude Code{tag}", "mcp_json", home / ".claude.json")
    # Codex
    add(f"Codex{tag}", "toml_config", home / ".codex" / "config.toml")
    add(f"Codex{tag}", "rules", home / ".codex" / "AGENTS.md")
    add(f"Codex{tag}", "prompts_root", home / ".codex" / "prompts")
    add(f"Codex{tag}", "skills_root", home / ".codex" / "skills")
    # Gemini CLI / Antigravity
    add(f"Gemini CLI{tag}", "settings_json", home / ".gemini" / "settings.json")
    add(f"Gemini CLI{tag}", "rules", home / ".gemini" / "GEMINI.md")
    add(f"Gemini CLI{tag}", "gemini_commands", home / ".gemini" / "commands")
    add(f"Antigravity{tag}", "mcp_json", home / ".gemini" / "antigravity" / "mcp_config.json")
    add(f"Antigravity{tag}", "mcp_json", home / ".antigravity" / "mcp_config.json")
    add(f"Antigravity{tag}", "mcp_json", home / ".antigravity" / "mcp.json")
    add(f"Antigravity{tag}", "rules_dir", home / ".gemini" / "antigravity" / "rules")
    add(f"Antigravity{tag}", "extensions_dir", home / ".antigravity" / "extensions")
    # Cursor / Windsurf
    add(f"Cursor{tag}", "mcp_json", home / ".cursor" / "mcp.json")
    add(f"Cursor{tag}", "extensions_dir", home / ".cursor" / "extensions")
    add(f"Windsurf{tag}", "rules_dir", home / ".codeium" / "windsurf" / "memories")
    add(f"Windsurf{tag}", "mcp_json", home / ".codeium" / "windsurf" / "mcp_config.json")
    # Cline / Roo / Kilo (VS Code globalStorage) + VS Code family user settings
    for editor, udir in _vscode_user_dirs(home, external=external):
        gs = udir / "globalStorage"
        add(f"Cline ({editor}){tag}", "mcp_json", gs / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json")
        add(f"Roo Code ({editor}){tag}", "mcp_json", gs / "rooveterinaryinc.roo-cline" / "settings" / "mcp_settings.json")
        add(f"Kilo Code ({editor}){tag}", "mcp_json", gs / "kilocode.kilo-code" / "settings" / "mcp_settings.json")
        add(f"VS Code ({editor}){tag}", "vscode_mcp", udir / "mcp.json")
        add(f"VS Code ({editor}){tag}", "vscode_settings", udir / "settings.json")
        add(f"Copilot ({editor}){tag}", "prompts_root", udir / "prompts")
    add(f"Cline{tag}", "rules_dir", home / "Documents" / "Cline" / "Rules")
    add(f"Roo Code{tag}", "rules_dir", home / ".roo" / "rules")
    add(f"VS Code{tag}", "extensions_dir", home / ".vscode" / "extensions")
    add(f"VS Code{tag}", "extensions_dir", home / ".vscode-insiders" / "extensions")
    # Continue / OpenCode / Zed / Aider
    add(f"Continue{tag}", "continue_config", home / ".continue" / "config.json")
    add(f"Continue{tag}", "continue_config", home / ".continue" / "config.yaml")
    add(f"Continue{tag}", "rules_dir", home / ".continue" / "rules")
    add(f"OpenCode{tag}", "opencode_config", cfgdir / "opencode" / "opencode.json")
    add(f"OpenCode{tag}", "commands_root", cfgdir / "opencode" / "command")
    add(f"OpenCode{tag}", "agents_root", cfgdir / "opencode" / "agent")
    add(f"Zed{tag}", "zed_settings", cfgdir / "zed" / "settings.json")
    add(f"Aider{tag}", "aider_conf", home / ".aider.conf.yml")
    # OpenClaw / Hermes (legacy names too)
    for agent, root in (("OpenClaw", ".openclaw"), ("OpenClaw", ".config/openclaw"), ("OpenClaw", ".clawdbot"),
                        ("OpenClaw", ".moltbot"), ("Hermes", ".hermes"), ("Hermes", ".hermes-agent"),
                        ("Hermes", ".config/hermes")):
        add(f"{agent}{tag}", "skills_root", home / root / "skills")
        for cfgname in ("openclaw.json", "config.json", "hermes.json"):
            add(f"{agent}{tag}", "mcp_json", home / root / cfgname)


def _project_sources(add, cwd, tag=""):
    """Everything an agent keeps inside a project folder."""
    cwd = Path(cwd)
    add(f"Claude Code{tag}", "rules", cwd / "CLAUDE.md")
    add(f"Claude Code{tag}", "rules", cwd / ".claude" / "CLAUDE.md")
    add(f"Claude Code{tag}", "skills_root", cwd / ".claude" / "skills")
    add(f"Claude Code{tag}", "commands_root", cwd / ".claude" / "commands")
    add(f"Claude Code{tag}", "agents_root", cwd / ".claude" / "agents")
    add(f"Claude Code{tag}", "settings_json", cwd / ".claude" / "settings.json")
    add(f"Claude Code{tag}", "settings_json", cwd / ".claude" / "settings.local.json")
    add(f"Claude Code{tag}", "mcp_json", cwd / ".mcp.json")
    add(f"Codex{tag}", "rules", cwd / "AGENTS.md")
    add(f"Codex{tag}", "skills_root", cwd / ".codex" / "skills")
    add(f"Codex{tag}", "skills_root", cwd / ".agents" / "skills")
    add(f"Gemini CLI{tag}", "rules", cwd / "GEMINI.md")
    add(f"Gemini CLI{tag}", "settings_json", cwd / ".gemini" / "settings.json")
    add(f"Gemini CLI{tag}", "gemini_commands", cwd / ".gemini" / "commands")
    add(f"Antigravity{tag}", "rules_dir", cwd / ".agent" / "rules")
    add(f"Antigravity{tag}", "workflows_dir", cwd / ".agent" / "workflows")
    add(f"Cursor{tag}", "rules", cwd / ".cursorrules")
    add(f"Cursor{tag}", "rules_dir", cwd / ".cursor" / "rules")
    add(f"Cursor{tag}", "mcp_json", cwd / ".cursor" / "mcp.json")
    add(f"Windsurf{tag}", "rules", cwd / ".windsurfrules")
    add(f"Windsurf{tag}", "rules_dir", cwd / ".windsurf" / "rules")
    add(f"Cline{tag}", "rules", cwd / ".clinerules")
    add(f"Cline{tag}", "rules_dir", cwd / ".clinerules")
    add(f"Roo Code{tag}", "rules_dir", cwd / ".roo" / "rules")
    add(f"Kilo Code{tag}", "rules_dir", cwd / ".kilocode" / "rules")
    add(f"VS Code{tag}", "vscode_mcp", cwd / ".vscode" / "mcp.json")
    add(f"VS Code{tag}", "vscode_settings", cwd / ".vscode" / "settings.json")
    add(f"Copilot{tag}", "rules", cwd / ".github" / "copilot-instructions.md")
    add(f"Copilot{tag}", "rules_dir", cwd / ".github" / "instructions")
    add(f"Copilot{tag}", "prompts_root", cwd / ".github" / "prompts")
    add(f"Copilot{tag}", "agents_root", cwd / ".github" / "agents")
    add(f"Continue{tag}", "rules_dir", cwd / ".continue" / "rules")
    add(f"OpenCode{tag}", "opencode_config", cwd / "opencode.json")
    add(f"OpenCode{tag}", "commands_root", cwd / ".opencode" / "command")
    add(f"OpenCode{tag}", "agents_root", cwd / ".opencode" / "agent")
    add(f"Zed{tag}", "rules", cwd / ".rules")
    add(f"Kiro{tag}", "rules_dir", cwd / ".kiro" / "steering")
    add(f"Amp{tag}", "rules", cwd / "AGENT.md")
    add(f"Junie{tag}", "rules", cwd / ".junie" / "guidelines.md")
    add(f"Aider{tag}", "rules", cwd / "CONVENTIONS.md")
    add(f"Aider{tag}", "aider_conf", cwd / ".aider.conf.yml")


def sources(cwd=None, homes=None):
    """(agent, kind, path) candidates. kind ∈ rules|rules_dir|workflows_dir|skills_root|commands_root|prompts_root|
    gemini_commands|agents_root|mcp_json|settings_json|toml_config|vscode_mcp|vscode_settings|zed_settings|
    opencode_config|continue_config|aider_conf|extensions_dir.
    homes: [(home_dir, tag)] — default is this machine's ~; [] means project-level only."""
    cwd = Path(cwd or Path.cwd())
    S = []

    def add(agent, kind, p):
        p = Path(p).expanduser()
        try:
            if p.exists():
                S.append((agent, kind, p))
        except OSError:
            pass

    for home, tag in ([(HOME, "")] if homes is None else homes):
        _user_sources(add, home, tag, external=bool(tag))
    _project_sources(add, cwd)
    return S


# ---- other drives ------------------------------------------------------------
#
# "My skills live on the D: drive / on a USB stick / on the old laptop's disk." Scanning a whole drive is not
# free, so this is bounded: a shallow walk (depth ≤ 4), a time budget per drive, and a skip list of folders
# that never hold agent gear (Windows, Program Files, node_modules, …). Found = dirs that look like a home
# (contain .claude/.codex/.cursor/…) and stray folders of SKILL.md skills.

AGENT_MARKERS = (".claude", ".codex", ".gemini", ".cursor", ".codeium", ".continue", ".antigravity", ".roo",
                 ".openclaw", ".hermes", ".kilocode", ".claude.json", ".aider.conf.yml")
SKIP_WALK = set(SKIP_DIRS) | {"Windows", "Program Files", "Program Files (x86)", "ProgramData", "$RECYCLE.BIN",
                              "System Volume Information", "Recovery", "PerfLogs", "AppData", "Library", "Applications",
                              "System", "private", "proc", "sys", "dev", "run", "lost+found", "snap", "boot", "etc",
                              ".Trash", ".Trashes", ".Spotlight-V100", ".fseventsd", ".TemporaryItems", "Steam",
                              "steamapps", "Photos", "Pictures", "Music", "Movies", "Videos", "site-packages", ".npm",
                              ".cargo", ".rustup", ".gradle", ".m2", ".nuget", "Downloads"}
WALK_DEPTH = 4
WALK_BUDGET_S = 6.0


def volume_label(p):
    p = Path(p)
    if IS_WIN or re.match(r"^[A-Za-z]:[\\/]?$", str(p)):
        return (p.drive or str(p)).upper()
    return p.name or str(p)


def _same_or_under(a, b):
    try:
        a, b = Path(a).resolve(), Path(b).resolve()
        return a == b or b in a.parents
    except Exception:
        return False


def external_volumes():
    """Mounted drives other than the one your home is on: Windows drive letters, macOS /Volumes, Linux
    /media · /run/media · /mnt (which is also where WSL shows the Windows drives, /mnt/c …)."""
    found = []
    if IS_WIN:
        import string
        skip = {(os.environ.get("SystemDrive") or "C:").rstrip("\\/").upper(), HOME.drive.upper()}
        for letter in string.ascii_uppercase:
            d = f"{letter}:"
            if d in skip:
                continue
            p = Path(d + "\\")
            try:
                if p.exists() and next(p.iterdir(), None) is not None:
                    found.append(p)
            except Exception:
                continue
        return found
    cands = []
    if sys.platform == "darwin" and Path("/Volumes").is_dir():
        cands += list(Path("/Volumes").iterdir())
    for base in ("/media", "/run/media", "/mnt"):
        b = Path(base)
        if not b.is_dir():
            continue
        for p in b.iterdir():
            cands.append(p)
            if base in ("/media", "/run/media"):          # /media/<user>/<volume>
                try:
                    cands += [q for q in p.iterdir() if q.is_dir()]
                except Exception:
                    pass
    seen = set()
    for p in cands:
        try:
            if not p.is_dir():
                continue
            r = p.resolve()
            if r == Path("/") or r in seen or _same_or_under(HOME, r):
                continue
            if sys.platform == "darwin" and r == Path("/System/Volumes/Data"):
                continue
            if next(p.iterdir(), None) is None:
                continue
            seen.add(r)
            found.append(p)
        except Exception:
            continue
    return found


def _walk(root, max_depth=WALK_DEPTH, budget_s=WALK_BUDGET_S):
    """Bounded breadth-first walk yielding directories (root first)."""
    t0 = time.time()
    frontier = [(Path(root), 0)]
    while frontier:
        d, depth = frontier.pop(0)
        yield d
        if depth >= max_depth or time.time() - t0 > budget_s:
            continue
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if not e.is_dir(follow_symlinks=False) or e.name in SKIP_WALK:
                            continue
                        if e.name.startswith(".") and e.name not in AGENT_MARKERS:
                            continue
                        frontier.append((Path(e.path), depth + 1))
                    except OSError:
                        continue
        except OSError:
            continue


def looks_like_home(d):
    d = Path(d)
    try:
        return any((d / m).exists() for m in AGENT_MARKERS)
    except OSError:
        return False


def _is_skills_root(d):
    try:
        return any(c.is_dir() and (c / "SKILL.md").is_file() for c in Path(d).iterdir())
    except OSError:
        return False


def find_on_volume(vol, max_depth=WALK_DEPTH, budget_s=WALK_BUDGET_S):
    """→ (homes, skill_roots) found on a drive: dirs that look like a home (contain .claude/.codex/…) and stray
    skill folders (any dir with child/SKILL.md) that aren't already inside one of those homes."""
    vol = Path(vol)
    homes, roots = [], []
    for d in _walk(vol, max_depth, budget_s):
        if looks_like_home(d):
            homes.append(d)
        elif _is_skills_root(d):
            roots.append(d)
    roots = [r for r in roots if not any(_same_or_under(r, h) for h in homes)]   # a home's own skills are scanned as that agent's
    return homes, roots


# ---- item model --------------------------------------------------------------

class Item:
    def __init__(self, kind, name, agent, payload, note="", dup=False, src=""):
        self.kind = kind          # memory | skill | command | agent | mcp | allow | deny | hook | extension | setting
        self.name = name
        self.agent = agent
        self.payload = payload
        self.note = note
        self.dup = dup
        self.src = str(src)

    def __repr__(self):
        return f"<{self.kind} {self.name} from {self.agent}>"


def _read(p, limit=200_000):
    try:
        return Path(p).read_text(errors="replace", encoding="utf-8")[:limit]
    except Exception:
        return ""


def _json(p):
    try:
        txt = _read(p)
        txt = re.sub(r"^\s*//.*$", "", txt, flags=re.M)  # tolerate JSONC comments
        txt = re.sub(r",(\s*[}\]])", r"\1", txt)
        return json.loads(txt)
    except Exception:
        return None


def _kebab(s):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "imported"


# ---- extractors --------------------------------------------------------------

def mcp_from_obj(data):
    """Find mcpServers / servers / context_servers / mcp blocks in any JSON structure."""
    found = {}
    if not isinstance(data, (dict, list)):
        return found

    def conv(name, spec):
        if not isinstance(spec, dict) or spec.get("disabled") is True:
            return
        if spec.get("command"):
            found[name] = {"transport": "stdio", "command": spec["command"], "args": list(spec.get("args", [])),
                           "env": dict(spec.get("env", {}) or {})}
        elif spec.get("url") or spec.get("serverUrl"):
            found[name] = {"transport": "http", "url": spec.get("url") or spec.get("serverUrl"),
                           "headers": dict(spec.get("headers", {}) or {})}

    def walk(node):
        if isinstance(node, dict):
            for key in ("mcpServers", "servers", "context_servers", "mcp_servers"):
                if isinstance(node.get(key), dict):
                    for name, spec in node[key].items():
                        conv(name, spec)
            if isinstance(node.get("mcp"), dict):
                for name, spec in node["mcp"].items():
                    if isinstance(spec, dict):
                        s = dict(spec)
                        if s.get("type") == "local" and isinstance(s.get("command"), list) and s["command"]:
                            s = {"command": s["command"][0], "args": s["command"][1:], "env": s.get("environment", {})}
                        elif s.get("type") == "remote":
                            s = {"url": s.get("url"), "headers": s.get("headers", {})}
                        conv(name, s)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
    return found


def _parse_toml(text):
    """tomllib on 3.11+, else a tiny parser good enough for codex config.toml tables."""
    try:
        import tomllib
        return tomllib.loads(text)
    except Exception:
        pass
    data = {}
    cur = data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(.+?)\]$", line)
        if m:
            cur = data
            for part in m.group(1).split("."):
                cur = cur.setdefault(part.strip().strip('"'), {})
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip().strip('"'), v.strip()
            try:
                cur[k] = json.loads(v)
            except Exception:
                cur[k] = v.strip('"')
    return data


def _codex_items(path, cfg):
    items = []
    data = _parse_toml(_read(path))
    servers = (data or {}).get("mcp_servers") or {}
    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        conv = None
        if spec.get("command"):
            conv = {"transport": "stdio", "command": spec["command"], "args": list(spec.get("args", [])),
                    "env": dict(spec.get("env", {}) or {})}
        elif spec.get("url"):
            conv = {"transport": "http", "url": spec["url"], "headers": {}}
        if conv:
            items.append(Item("mcp", name, "Codex", conv, conv.get("command") or conv.get("url", ""),
                              dup=name in cfg.get("mcp_servers", {}), src=path))
    model = (data or {}).get("model")
    if model:
        items.append(Item("setting", "codex model", "Codex", {"note": f"Codex uses model {model}"},
                          f"{model} (use codex-plan provider to ride your ChatGPT plan)", src=path))
    return items


def _claude_settings_items(path, cfg, agent="Claude Code"):
    items = []
    data = _json(path) or {}
    perms = data.get("permissions") or {}
    for rule in perms.get("allow", []) or []:
        m = re.match(r"Bash\((.+)\)", str(rule))
        if m:
            pfx = re.sub(r"[:\s]\*$", "", m.group(1)).strip()
            if pfx and pfx != "*":
                items.append(Item("allow", pfx, agent, pfx, "auto-approve bash prefix",
                                  dup=pfx in cfg.get("bash_allow", []), src=path))
    for rule in perms.get("deny", []) or []:
        m = re.match(r"Bash\((.+)\)", str(rule))
        if m:
            pfx = re.sub(r"[:\s]\*$", "", m.group(1)).strip()
            if pfx:
                items.append(Item("deny", pfx, agent, pfx, "always refuse", dup=pfx in cfg.get("bash_deny", []), src=path))
    hooks = data.get("hooks")
    if isinstance(hooks, dict) and hooks:
        n = sum(len(v) for v in hooks.values() if isinstance(v, list))
        items.append(Item("hook", f"{n} hook group(s)", agent, hooks, "lifecycle hooks (format compatible)",
                          dup=bool(cfg.get("hooks")), src=path))
    for name, spec in mcp_from_obj(data).items():
        items.append(Item("mcp", name, agent, spec, spec.get("command") or spec.get("url", ""),
                          dup=name in cfg.get("mcp_servers", {}), src=path))
    return items


def _rules_items(agent, path, cwd):
    """Instruction file → memory section. Project files go to ./CHODE.md, global to ~/.chode/CHODE.md."""
    text = _read(path).strip()
    if not text or len(text) < 20:
        return []
    text = strip_frontmatter(text) if path.suffix in (".mdc", ".md") else text
    scope = "project" if str(path).startswith(str(Path(cwd).resolve())) else "global"
    target = Path(cwd) / MEMORY_FILENAME if scope == "project" else GLOBAL_MEMORY_FILE
    marker = f"<!-- imported from {path} -->"
    dup = target.exists() and marker in _read(target)
    name = path.name if path.name not in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", "AGENT.md") else f"{path.name} ({path.parent.name})"
    return [Item("memory", name, agent, {"text": text, "target": str(target), "marker": marker, "scope": scope},
                 f"{len(text)} chars → {('./' if scope == 'project' else '~/.chode/') + MEMORY_FILENAME}", dup=dup, src=path)]


def _rules_dir_items(agent, d, cwd):
    items = []
    for f in sorted(Path(d).rglob("*")):
        if f.is_file() and f.suffix.lower() in (".md", ".mdc", ".txt", "") and f.stat().st_size < 200_000:
            items += _rules_items(agent, f, cwd)
    return items[:40]


def _skill_items(agent, root, existing, only=None):
    items = []
    root = Path(root)
    try:
        if GLOBAL_SKILLS_DIR.resolve() == root.resolve():
            return items
        children = sorted(root.iterdir())
    except OSError:
        return items
    for d in children:
        if only is not None and d.resolve() != Path(only).resolve():
            continue
        f = d / "SKILL.md"
        if d.is_dir() and f.exists():
            meta = parse_frontmatter(_read(f))
            name = meta.get("name", d.name)
            items.append(Item("skill", name, agent, {"src": str(d)}, meta.get("description", "")[:70],
                              dup=name in existing, src=d))
    return items


def _command_items(agent, root, cfg):
    items = []
    root = Path(root)
    existing = {f.stem for f in GLOBAL_COMMANDS_DIR.glob("*.md")} if GLOBAL_COMMANDS_DIR.is_dir() else set()
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix == ".md" or f.name.endswith(".prompt.md"):
            name = _kebab(f.name.replace(".prompt.md", "").replace(".md", ""))
            text = _read(f)
            meta = parse_frontmatter(text)
            body = strip_frontmatter(text).strip()
            if not body:
                continue
            desc = meta.get("description", "")
            items.append(Item("command", name, agent, {"description": desc, "template": body}, desc[:60] or body[:60],
                              dup=name in existing, src=f))
        elif f.suffix == ".toml":  # Gemini CLI commands: prompt = "..."
            data = _parse_toml(_read(f))
            prompt = (data or {}).get("prompt")
            if prompt:
                name = _kebab(f.stem)
                tpl = str(prompt).replace("{{args}}", "$ARGUMENTS")
                items.append(Item("command", name, agent, {"description": (data or {}).get("description", ""), "template": tpl},
                                  (data or {}).get("description", "")[:60], dup=name in existing, src=f))
    return items[:60]


def _agent_items(agent, root):
    items = []
    existing = {f.stem for f in GLOBAL_AGENTS_DIR.glob("*.md")} if GLOBAL_AGENTS_DIR.is_dir() else set()
    for f in sorted(Path(root).glob("*.md")):
        text = _read(f)
        meta = parse_frontmatter(text)
        name = _kebab(meta.get("name", f.stem))
        body = strip_frontmatter(text).strip()
        if body:
            items.append(Item("agent", name, agent, {"text": text if text.startswith("---") else
                              f"---\nname: {name}\ndescription: {meta.get('description','')}\n---\n{body}"},
                              meta.get("description", "")[:60], dup=name in existing, src=f))
    return items[:40]


def _vscode_settings_items(agent, path, cfg):
    items = []
    data = _json(path) or {}
    for name, spec in mcp_from_obj(data).items():
        items.append(Item("mcp", name, agent, spec, spec.get("command") or spec.get("url", ""),
                          dup=name in cfg.get("mcp_servers", {}), src=path))
    instr = data.get("github.copilot.chat.codeGeneration.instructions")
    if isinstance(instr, list):
        texts = [i.get("text") for i in instr if isinstance(i, dict) and i.get("text")]
        if texts:
            text = "\n".join(f"- {t}" for t in texts)
            items.append(Item("memory", "copilot codeGeneration.instructions", agent,
                              {"text": text, "target": str(GLOBAL_MEMORY_FILE), "marker": f"<!-- imported from {path} -->",
                               "scope": "global"}, f"{len(texts)} instruction(s)", src=path))
    return items


KNOWN_AI_EXTENSIONS = {
    "saoudrizwan.claude-dev": "Cline", "rooveterinaryinc.roo-cline": "Roo Code", "kilocode.kilo-code": "Kilo Code",
    "continue.continue": "Continue", "github.copilot": "GitHub Copilot", "github.copilot-chat": "Copilot Chat",
    "anthropic.claude-code": "Claude Code", "openai.chatgpt": "Codex / ChatGPT", "google.geminicodeassist": "Gemini Code Assist",
    "sourcegraph.cody-ai": "Cody", "codeium.codeium": "Codeium", "tabnine.tabnine-vscode": "Tabnine",
    "amazonwebservices.amazon-q-vscode": "Amazon Q", "augment.vscode-augment": "Augment", "supermaven.supermaven": "Supermaven",
    "blackboxapp.blackbox": "Blackbox", "bito.bito": "Bito", "qodo.qodo-gen": "Qodo", "windsurf.windsurf": "Windsurf",
}


def _extension_items(agent, d):
    names = []
    try:
        for e in Path(d).iterdir():
            if e.is_dir():
                m = re.match(r"^([a-z0-9\-]+\.[a-z0-9\-]+)-\d", e.name, re.I)
                if m:
                    names.append(m.group(1).lower())
    except Exception:
        return []
    ai = [(n, KNOWN_AI_EXTENSIONS[n]) for n in sorted(set(names)) if n in KNOWN_AI_EXTENSIONS]
    if not ai:
        return []
    return [Item("extension", f"{len(ai)} AI extension(s)", agent, ai,
                 ", ".join(label for _, label in ai)[:70], src=d)]


def _continue_items(path, cfg):
    items = []
    data = _json(path)
    if data is None and path.suffix in (".yaml", ".yml"):
        txt = _read(path)
        # tiny YAML scrape for rules: and mcpServers (name/command/args)
        for m in re.finditer(r"^\s*-\s*name:\s*(.+)\n\s*command:\s*(.+)\n(?:\s*args:\s*\[(.*)\])?", txt, re.M):
            name, cmd, args = m.group(1).strip().strip('"'), m.group(2).strip().strip('"'), m.group(3) or ""
            items.append(Item("mcp", _kebab(name), "Continue", {"transport": "stdio", "command": cmd,
                              "args": [a.strip().strip('"\'') for a in args.split(",") if a.strip()]}, cmd,
                              dup=_kebab(name) in cfg.get("mcp_servers", {}), src=path))
        rules = re.findall(r"^rules:\n((?:\s+-\s.+\n?)+)", txt, re.M)
        if rules:
            text = re.sub(r"^\s+-\s", "- ", rules[0], flags=re.M)
            items.append(Item("memory", "Continue rules", "Continue", {"text": text, "target": str(GLOBAL_MEMORY_FILE),
                              "marker": f"<!-- imported from {path} -->", "scope": "global"}, "rules", src=path))
        return items
    data = data or {}
    for name, spec in mcp_from_obj(data).items():
        items.append(Item("mcp", name, "Continue", spec, spec.get("command") or spec.get("url", ""),
                          dup=name in cfg.get("mcp_servers", {}), src=path))
    sysmsg = data.get("systemMessage")
    if sysmsg:
        items.append(Item("memory", "Continue systemMessage", "Continue", {"text": sysmsg, "target": str(GLOBAL_MEMORY_FILE),
                          "marker": f"<!-- imported from {path} -->", "scope": "global"}, sysmsg[:60], src=path))
    for cc in data.get("customCommands", []) or []:
        if isinstance(cc, dict) and cc.get("name") and cc.get("prompt"):
            items.append(Item("command", _kebab(cc["name"]), "Continue",
                              {"description": cc.get("description", ""), "template": cc["prompt"].replace("{{{ input }}}", "$ARGUMENTS")},
                              cc.get("description", "")[:60], src=path))
    return items


def _aider_items(path):
    txt = _read(path)
    items = []
    m = re.search(r"^model:\s*(.+)$", txt, re.M)
    if m:
        items.append(Item("setting", "aider model", "Aider", {"note": f"Aider uses {m.group(1).strip()}"}, m.group(1).strip(), src=path))
    reads = re.findall(r"^read:\s*(.+)$", txt, re.M)
    for r in reads:
        p = Path(path).parent / r.strip()
        if p.exists():
            items += _rules_items("Aider", p, Path(path).parent)
    return items


# ---- scan --------------------------------------------------------------------

def classify_path(p):
    """What is this folder someone pointed us at? skill · skills_root · home · project"""
    p = Path(p)
    if (p / "SKILL.md").is_file():
        return "skill"
    if looks_like_home(p):
        return "home"
    if _is_skills_root(p):
        return "skills_root"
    return "project"


def scan(cfg, cwd=None, paths=(), volumes=()):
    """Everything importable. paths: folders the user named (a skill, a skills folder, a copied ~/.claude,
    a project). volumes: other drives to search (see external_volumes / find_on_volume)."""
    cwd = Path(cwd or Path.cwd()).resolve()
    existing_skills = set(discover_skills(cwd))
    homes = [(HOME, "")]
    skill_roots = []          # (agent_label, root_dir, only_this_child_or_None)
    extra_projects = []       # (project_dir, tag)
    for vol in volumes or ():
        tag = f" @ {volume_label(vol)}"
        try:
            vh, vr = find_on_volume(vol)
        except Exception:
            continue
        homes += [(h, tag) for h in vh]
        skill_roots += [(f"skills folder{tag}", r, None) for r in vr]
    for raw in paths or ():
        p = Path(str(raw)).expanduser()
        try:
            if not p.exists():
                continue
            p = p.resolve()
        except OSError:
            continue
        tag = f" @ {p.name or volume_label(p)}"
        what = classify_path(p)
        if what == "skill":
            skill_roots.append((f"folder{tag}", p.parent, p))
        elif what == "home":
            homes.append((p, tag))
        elif what == "skills_root":
            skill_roots.append((f"folder{tag}", p, None))
        else:
            extra_projects.append((p, tag))
            try:                                    # a plain folder: look inside it (bounded) for homes and skill folders
                ph, pr = find_on_volume(p, max_depth=3, budget_s=3.0)
            except Exception:
                ph, pr = [], []
            homes += [(h, tag) for h in ph if h.resolve() != p]
            skill_roots += [(f"folder{tag}", r, None) for r in pr]
    items = []
    seen_src = set()
    src = sources(cwd, homes=homes)
    for proj, tag in extra_projects:
        def _add(agent, kind, p):
            p = Path(p)
            if p.exists():
                src.append((agent, kind, p))
        _project_sources(_add, proj, tag)
    for agent, kind, path in src:
        key = (kind, str(path))
        if key in seen_src:
            continue
        seen_src.add(key)
        try:
            if kind == "rules":
                items += _rules_items(agent, path, cwd)
            elif kind == "rules_dir" or kind == "workflows_dir":
                items += _rules_dir_items(agent, path, cwd)
            elif kind == "skills_root":
                items += _skill_items(agent, path, existing_skills)
            elif kind in ("commands_root", "prompts_root", "gemini_commands"):
                items += _command_items(agent, path, cfg)
            elif kind == "agents_root":
                items += _agent_items(agent, path)
            elif kind == "mcp_json":
                for name, spec in mcp_from_obj(_json(path)).items():
                    items.append(Item("mcp", name, agent, spec, spec.get("command") or spec.get("url", ""),
                                      dup=name in cfg.get("mcp_servers", {}), src=path))
            elif kind == "settings_json" and agent.startswith("Claude Code"):
                items += _claude_settings_items(path, cfg, agent)
            elif kind == "settings_json":
                for name, spec in mcp_from_obj(_json(path)).items():
                    items.append(Item("mcp", name, agent, spec, spec.get("command") or spec.get("url", ""),
                                      dup=name in cfg.get("mcp_servers", {}), src=path))
            elif kind == "toml_config":
                items += _codex_items(path, cfg)
            elif kind in ("vscode_mcp", "vscode_settings", "zed_settings", "opencode_config"):
                items += _vscode_settings_items(agent, path, cfg)
            elif kind == "extensions_dir":
                items += _extension_items(agent, path)
            elif kind == "continue_config":
                items += _continue_items(path, cfg)
            elif kind == "aider_conf":
                items += _aider_items(path)
        except Exception:
            continue
    for agent, root, only in skill_roots:                 # stray skill folders from other drives / named paths
        key = ("skills_root", str(root), str(only or ""))
        if key in seen_src:
            continue
        seen_src.add(key)
        try:
            items += _skill_items(agent, root, existing_skills, only=only)
        except Exception:
            continue
    # dedupe by (kind, name) keeping first — skills from different places keep their source so you can see both
    out, seen = [], set()
    for it in items:
        k = (it.kind, it.name, it.src if it.kind in ("memory", "skill") else "")
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


# ---- apply -------------------------------------------------------------------

def apply(items, cfg, cwd=None, overwrite=False):
    cwd = Path(cwd or Path.cwd())
    report = []
    cfg_changed = False
    for it in items:
        try:
            if it.kind == "memory":
                target = Path(it.payload["target"])
                existing = _read(target) if target.exists() else ""
                if it.payload["marker"] in existing and not overwrite:
                    report.append(f"= memory {it.name} already imported")
                    continue
                text, n = redact_secrets(it.payload["text"])
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "a", encoding="utf-8") as f:
                    if not existing:
                        f.write(f"# {MEMORY_FILENAME}\n\n")
                    f.write(f"\n\n## Imported from {it.agent}: {Path(it.src).name}\n{it.payload['marker']}\n{text.strip()}\n")
                report.append(f"✓ memory {it.name} → {target}" + (f" ({n} secrets stripped)" if n else ""))
            elif it.kind == "skill":
                dest = GLOBAL_SKILLS_DIR / _kebab(it.name)
                if dest.exists():
                    if not overwrite:
                        report.append(f"= skill {it.name} exists")
                        continue
                    shutil.rmtree(dest)
                shutil.copytree(it.payload["src"], dest)
                report.append(f"✓ skill {it.name} → {dest}")
            elif it.kind == "command":
                GLOBAL_COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
                dest = GLOBAL_COMMANDS_DIR / f"{_kebab(it.name)}.md"
                if dest.exists() and not overwrite:
                    report.append(f"= command /{it.name} exists")
                    continue
                desc = (it.payload.get("description") or "").replace("\n", " ")
                dest.write_text(f"---\ndescription: {desc}\n---\n{it.payload['template']}\n", encoding="utf-8")
                report.append(f"✓ command /{_kebab(it.name)}")
            elif it.kind == "agent":
                GLOBAL_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
                dest = GLOBAL_AGENTS_DIR / f"{_kebab(it.name)}.md"
                if dest.exists() and not overwrite:
                    report.append(f"= agent {it.name} exists")
                    continue
                dest.write_text(it.payload["text"], encoding="utf-8")
                report.append(f"✓ agent persona {it.name}")
            elif it.kind == "mcp":
                servers = cfg.setdefault("mcp_servers", {})
                if it.name in servers and not overwrite:
                    report.append(f"= mcp {it.name} already configured")
                    continue
                servers[it.name] = it.payload
                cfg_changed = True
                report.append(f"✓ mcp {it.name}")
            elif it.kind == "allow":
                lst = cfg.setdefault("bash_allow", [])
                if it.payload not in lst:
                    lst.append(it.payload); cfg_changed = True
                report.append(f"✓ allow `{it.payload}`")
            elif it.kind == "deny":
                lst = cfg.setdefault("bash_deny", [])
                if it.payload not in lst:
                    lst.append(it.payload); cfg_changed = True
                report.append(f"✓ deny `{it.payload}`")
            elif it.kind == "hook":
                hooks = cfg.setdefault("hooks", {})
                for ev, entries in it.payload.items():
                    hooks.setdefault(ev, [])
                    for e in entries if isinstance(entries, list) else []:
                        if e not in hooks[ev]:
                            hooks[ev].append(e)
                cfg_changed = True
                report.append(f"✓ hooks imported ({it.name})")
            elif it.kind == "extension":
                labels = ", ".join(l for _, l in it.payload)
                report.append(f"ℹ {it.agent}: {labels} — CHODE covers these; their rules/MCP configs were scanned above")
            elif it.kind == "setting":
                report.append(f"ℹ {it.payload.get('note')}")
        except Exception as e:
            report.append(f"✗ {it.kind} {it.name}: {str(e)[:120]}")
    if cfg_changed:
        save_config(cfg)
        report.append("✓ config saved (/mcp reload or restart to connect new MCP servers)")
    return report


def vscode_extension_list():
    """Ask the `code` CLI for installed extensions (best effort)."""
    for exe in ("code", "code-insiders", "cursor", "windsurf"):
        path = shutil.which(exe)
        if not path:
            continue
        try:
            r = subprocess.run([path, "--list-extensions"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                return exe, [l.strip().lower() for l in r.stdout.splitlines() if l.strip()]
        except Exception:
            continue
    return None, []
