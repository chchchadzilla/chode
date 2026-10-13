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

Nothing is written until you say so. Nothing is ever deleted from the source.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import save_config
from .paths import (GLOBAL_AGENTS_DIR, GLOBAL_COMMANDS_DIR, GLOBAL_MEMORY_FILE, GLOBAL_SKILLS_DIR, IS_WIN,
                    MEMORY_FILENAME, SKIP_DIRS)
from .security import redact_secrets
from .skills import discover_skills, parse_frontmatter, strip_frontmatter

HOME = Path.home()


def _vscode_user_dirs():
    """User dirs for VS Code family editors (Code, Insiders, Cursor, Windsurf, Antigravity, VSCodium)."""
    if IS_WIN:
        base = Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))
        names = ["Code", "Code - Insiders", "Cursor", "Windsurf", "Antigravity", "VSCodium", "Trae"]
        return [(n, base / n / "User") for n in names]
    if sys.platform == "darwin":
        base = HOME / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
    names = ["Code", "Code - Insiders", "Cursor", "Windsurf", "Antigravity", "VSCodium", "Trae"]
    return [(n, base / n / "User") for n in names]


# ---- where things live -------------------------------------------------------

def sources(cwd=None):
    """Yields (agent, kind, path) candidates. kind ∈ rules|skills_root|commands_root|agents_root|
    mcp_json|settings_json|toml_config|prompts_root|extensions_dir|hooks_json"""
    cwd = Path(cwd or Path.cwd())
    S = []

    def add(agent, kind, p):
        p = Path(p).expanduser()
        if p.exists():
            S.append((agent, kind, p))

    # Claude Code
    add("Claude Code", "rules", HOME / ".claude" / "CLAUDE.md")
    add("Claude Code", "skills_root", HOME / ".claude" / "skills")
    add("Claude Code", "commands_root", HOME / ".claude" / "commands")
    add("Claude Code", "agents_root", HOME / ".claude" / "agents")
    add("Claude Code", "settings_json", HOME / ".claude" / "settings.json")
    add("Claude Code", "mcp_json", HOME / ".claude.json")
    add("Claude Code", "rules", cwd / "CLAUDE.md")
    add("Claude Code", "rules", cwd / ".claude" / "CLAUDE.md")
    add("Claude Code", "skills_root", cwd / ".claude" / "skills")
    add("Claude Code", "commands_root", cwd / ".claude" / "commands")
    add("Claude Code", "agents_root", cwd / ".claude" / "agents")
    add("Claude Code", "settings_json", cwd / ".claude" / "settings.json")
    add("Claude Code", "settings_json", cwd / ".claude" / "settings.local.json")
    add("Claude Code", "mcp_json", cwd / ".mcp.json")
    # Codex
    add("Codex", "toml_config", HOME / ".codex" / "config.toml")
    add("Codex", "rules", HOME / ".codex" / "AGENTS.md")
    add("Codex", "prompts_root", HOME / ".codex" / "prompts")
    add("Codex", "skills_root", HOME / ".codex" / "skills")
    add("Codex", "rules", cwd / "AGENTS.md")
    add("Codex", "skills_root", cwd / ".codex" / "skills")
    add("Codex", "skills_root", cwd / ".agents" / "skills")
    # Gemini CLI / Antigravity
    add("Gemini CLI", "settings_json", HOME / ".gemini" / "settings.json")
    add("Gemini CLI", "rules", HOME / ".gemini" / "GEMINI.md")
    add("Gemini CLI", "gemini_commands", HOME / ".gemini" / "commands")
    add("Gemini CLI", "rules", cwd / "GEMINI.md")
    add("Gemini CLI", "settings_json", cwd / ".gemini" / "settings.json")
    add("Gemini CLI", "gemini_commands", cwd / ".gemini" / "commands")
    add("Antigravity", "mcp_json", HOME / ".gemini" / "antigravity" / "mcp_config.json")
    add("Antigravity", "mcp_json", HOME / ".antigravity" / "mcp_config.json")
    add("Antigravity", "mcp_json", HOME / ".antigravity" / "mcp.json")
    add("Antigravity", "rules_dir", HOME / ".gemini" / "antigravity" / "rules")
    add("Antigravity", "rules_dir", cwd / ".agent" / "rules")
    add("Antigravity", "workflows_dir", cwd / ".agent" / "workflows")
    add("Antigravity", "extensions_dir", HOME / ".antigravity" / "extensions")
    # Cursor
    add("Cursor", "rules", cwd / ".cursorrules")
    add("Cursor", "rules_dir", cwd / ".cursor" / "rules")
    add("Cursor", "mcp_json", HOME / ".cursor" / "mcp.json")
    add("Cursor", "mcp_json", cwd / ".cursor" / "mcp.json")
    add("Cursor", "extensions_dir", HOME / ".cursor" / "extensions")
    # Windsurf
    add("Windsurf", "rules", cwd / ".windsurfrules")
    add("Windsurf", "rules_dir", cwd / ".windsurf" / "rules")
    add("Windsurf", "rules_dir", HOME / ".codeium" / "windsurf" / "memories")
    add("Windsurf", "mcp_json", HOME / ".codeium" / "windsurf" / "mcp_config.json")
    # Cline / Roo / Kilo (VS Code globalStorage)
    for editor, udir in _vscode_user_dirs():
        gs = udir / "globalStorage"
        add(f"Cline ({editor})", "mcp_json", gs / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json")
        add(f"Roo Code ({editor})", "mcp_json", gs / "rooveterinaryinc.roo-cline" / "settings" / "mcp_settings.json")
        add(f"Kilo Code ({editor})", "mcp_json", gs / "kilocode.kilo-code" / "settings" / "mcp_settings.json")
        add(f"VS Code ({editor})", "vscode_mcp", udir / "mcp.json")
        add(f"VS Code ({editor})", "vscode_settings", udir / "settings.json")
        add(f"Copilot ({editor})", "prompts_root", udir / "prompts")
    add("Cline", "rules", cwd / ".clinerules")
    add("Cline", "rules_dir", cwd / ".clinerules")
    add("Cline", "rules_dir", HOME / "Documents" / "Cline" / "Rules")
    add("Roo Code", "rules_dir", cwd / ".roo" / "rules")
    add("Roo Code", "rules_dir", HOME / ".roo" / "rules")
    add("Kilo Code", "rules_dir", cwd / ".kilocode" / "rules")
    # VS Code workspace
    add("VS Code", "vscode_mcp", cwd / ".vscode" / "mcp.json")
    add("VS Code", "vscode_settings", cwd / ".vscode" / "settings.json")
    add("VS Code", "extensions_dir", HOME / ".vscode" / "extensions")
    add("VS Code", "extensions_dir", HOME / ".vscode-insiders" / "extensions")
    # GitHub Copilot
    add("Copilot", "rules", cwd / ".github" / "copilot-instructions.md")
    add("Copilot", "rules_dir", cwd / ".github" / "instructions")
    add("Copilot", "prompts_root", cwd / ".github" / "prompts")
    add("Copilot", "agents_root", cwd / ".github" / "agents")
    # Continue
    add("Continue", "continue_config", HOME / ".continue" / "config.json")
    add("Continue", "continue_config", HOME / ".continue" / "config.yaml")
    add("Continue", "rules_dir", HOME / ".continue" / "rules")
    add("Continue", "rules_dir", cwd / ".continue" / "rules")
    # OpenCode
    add("OpenCode", "opencode_config", HOME / ".config" / "opencode" / "opencode.json")
    add("OpenCode", "opencode_config", cwd / "opencode.json")
    add("OpenCode", "commands_root", HOME / ".config" / "opencode" / "command")
    add("OpenCode", "agents_root", HOME / ".config" / "opencode" / "agent")
    add("OpenCode", "commands_root", cwd / ".opencode" / "command")
    add("OpenCode", "agents_root", cwd / ".opencode" / "agent")
    # Zed
    add("Zed", "zed_settings", HOME / ".config" / "zed" / "settings.json")
    add("Zed", "rules", cwd / ".rules")
    # Kiro / Amp / Junie / Aider
    add("Kiro", "rules_dir", cwd / ".kiro" / "steering")
    add("Amp", "rules", cwd / "AGENT.md")
    add("Junie", "rules", cwd / ".junie" / "guidelines.md")
    add("Aider", "rules", cwd / "CONVENTIONS.md")
    add("Aider", "aider_conf", cwd / ".aider.conf.yml")
    add("Aider", "aider_conf", HOME / ".aider.conf.yml")
    # OpenClaw / Hermes (legacy names too)
    for agent, root in (("OpenClaw", "~/.openclaw"), ("OpenClaw", "~/.config/openclaw"), ("OpenClaw", "~/.clawdbot"),
                        ("OpenClaw", "~/.moltbot"), ("Hermes", "~/.hermes"), ("Hermes", "~/.hermes-agent"),
                        ("Hermes", "~/.config/hermes")):
        add(agent, "skills_root", Path(root).expanduser() / "skills")
        for cfgname in ("openclaw.json", "config.json", "hermes.json"):
            add(agent, "mcp_json", Path(root).expanduser() / cfgname)
    return S


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


def _claude_settings_items(path, cfg):
    items = []
    data = _json(path) or {}
    perms = data.get("permissions") or {}
    for rule in perms.get("allow", []) or []:
        m = re.match(r"Bash\((.+)\)", str(rule))
        if m:
            pfx = re.sub(r"[:\s]\*$", "", m.group(1)).strip()
            if pfx and pfx != "*":
                items.append(Item("allow", pfx, "Claude Code", pfx, "auto-approve bash prefix",
                                  dup=pfx in cfg.get("bash_allow", []), src=path))
    for rule in perms.get("deny", []) or []:
        m = re.match(r"Bash\((.+)\)", str(rule))
        if m:
            pfx = re.sub(r"[:\s]\*$", "", m.group(1)).strip()
            if pfx:
                items.append(Item("deny", pfx, "Claude Code", pfx, "always refuse", dup=pfx in cfg.get("bash_deny", []), src=path))
    hooks = data.get("hooks")
    if isinstance(hooks, dict) and hooks:
        n = sum(len(v) for v in hooks.values() if isinstance(v, list))
        items.append(Item("hook", f"{n} hook group(s)", "Claude Code", hooks, "lifecycle hooks (format compatible)",
                          dup=bool(cfg.get("hooks")), src=path))
    for name, spec in mcp_from_obj(data).items():
        items.append(Item("mcp", name, "Claude Code", spec, spec.get("command") or spec.get("url", ""),
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


def _skill_items(agent, root, existing):
    items = []
    root = Path(root)
    if GLOBAL_SKILLS_DIR.resolve() == root.resolve():
        return items
    for d in sorted(root.iterdir()):
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

def scan(cfg, cwd=None):
    cwd = Path(cwd or Path.cwd()).resolve()
    existing_skills = set(discover_skills(cwd))
    items = []
    seen_src = set()
    for agent, kind, path in sources(cwd):
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
            elif kind == "settings_json" and agent == "Claude Code":
                items += _claude_settings_items(path, cfg)
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
    # dedupe by (kind, name) keeping first
    out, seen = [], set()
    for it in items:
        k = (it.kind, it.name, it.src if it.kind == "memory" else "")
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
