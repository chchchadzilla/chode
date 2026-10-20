"""Skills: SKILL.md folders with progressive disclosure (same format as Claude
Code / Codex / OpenClaw — so skills are portable in every direction)."""
import shutil
import subprocess
from pathlib import Path

from .paths import GLOBAL_SKILLS_DIR, GLOBAL_AGENTS_DIR, PROJECT_DIRNAME


def parse_frontmatter(text):
    """Minimal YAML frontmatter parser: flat `key: value` lines only."""
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line and not line.startswith(" "):
                    k, _, v = line.partition(":")
                    meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta


def strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


class Skill:
    def __init__(self, name, description, path):
        self.name = name
        self.description = description
        self.path = path  # directory containing SKILL.md

    def body(self):
        return (self.path / "SKILL.md").read_text(errors="replace", encoding="utf-8")


def skill_roots(cwd=None):
    cwd = Path(cwd or Path.cwd())
    return [GLOBAL_SKILLS_DIR, cwd / PROJECT_DIRNAME / "skills",
            # zero-friction: read other agents' project skills in place
            cwd / ".claude" / "skills", cwd / ".codex" / "skills", cwd / ".agents" / "skills"]


def discover_skills(cwd=None):
    """Project skills shadow global ones with the same name."""
    skills = {}
    for base in skill_roots(cwd):
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            f = d / "SKILL.md"
            if not (d.is_dir() and f.exists()):
                continue
            try:
                text = f.read_text(errors="replace", encoding="utf-8")
            except Exception:
                continue
            meta = parse_frontmatter(text)
            name = meta.get("name", d.name).strip()
            desc = meta.get("description", "")
            if not desc:
                for line in strip_frontmatter(text).splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "---")):
                        desc = line[:200]
                        break
            skills[name] = Skill(name, desc or "(no description)", d)
    return skills


def skills_index_prompt(skills):
    if not skills:
        return ""
    lines = [f"- {s.name}: {s.description[:220]}" for s in skills.values()]
    return ("Skills available (folders of instructions/scripts for specific task types). "
            "When a task matches a skill's description, call the `skill` tool with its name "
            "BEFORE attempting the task, then follow its instructions:\n" + "\n".join(lines))


def install_skill(source, name=""):
    GLOBAL_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(source).expanduser()
    if src.is_dir():
        if not (src / "SKILL.md").exists():
            return f"error: {src} has no SKILL.md"
        dest = GLOBAL_SKILLS_DIR / (name or src.name)
        if dest.exists():
            return f"error: skill '{dest.name}' already exists ({dest})"
        shutil.copytree(src, dest)
        return f"installed skill '{dest.name}' → {dest}"
    if source.startswith(("http://", "https://", "git@")):
        dest = GLOBAL_SKILLS_DIR / (name or Path(source).stem.replace(".git", ""))
        if dest.exists():
            return f"error: skill '{dest.name}' already exists ({dest})"
        r = subprocess.run(["git", "clone", "--depth", "1", source, str(dest)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return f"git clone failed: {r.stderr.strip()[:300]}"
        return f"installed skill '{dest.name}' → {dest}"
    return f"error: {source} is neither a directory nor a git URL"


# --------------------------------------------------------------------------
# Agents (named personas for spawn_agent): ~/.chode/agents/<name>.md
# --------------------------------------------------------------------------

def discover_agents(cwd=None):
    agents = {}
    cwd = Path(cwd or Path.cwd())
    for base in (GLOBAL_AGENTS_DIR, cwd / PROJECT_DIRNAME / "agents", cwd / ".claude" / "agents"):
        if not base.is_dir():
            continue
        for f in sorted(base.glob("*.md")):
            try:
                text = f.read_text(errors="replace", encoding="utf-8")
            except Exception:
                continue
            meta = parse_frontmatter(text)
            name = meta.get("name", f.stem)
            agents[name] = {"name": name, "description": meta.get("description", ""),
                            "prompt": strip_frontmatter(text).strip(), "path": f,
                            "model": meta.get("model", ""), "tools": meta.get("tools", "")}
    return agents


# --------------------------------------------------------------------------
# Built-in skills (materialized into ~/.chode/skills on first run)
# --------------------------------------------------------------------------

SKILL_PORTER_MD = """---
name: skill-porter
description: Convert skills, plugins, prompts, or agent instructions from ANY other AI agent (Claude Code, Codex, Cursor rules, AGENTS.md, GPT instructions, OpenClaw, Hermes, raw prompt files) into proper CHODE skills
---
# Skill Porter — rewrite anything into a CHODE skill

Use this when the user points you at a skill/plugin/prompt from another agent and wants
it working in CHODE. `chode import` copies already-compatible SKILL.md folders;
THIS skill is for everything else — different formats, different tool names, loose
prompt files, or skills that need adaptation.

## Procedure

1. **Read the source.** `list_dir` + `read_file` everything the user pointed at.
   Recognize the format:
   - `SKILL.md` folder (Claude Code / Codex / OpenClaw / Hermes) → mostly compatible; fix frontmatter + tool names
   - `.cursorrules`, `.cursor/rules/*.mdc`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` → instruction files; extract the reusable technique
   - GPT / character / agent JSON exports → pull the instructions field
   - plugin folders with scripts → keep the scripts, write a SKILL.md that explains when/how to run them

2. **Rewrite tool references** using this mapping (CHODE's tools on the right):

   | other agents say | CHODE tool |
   |---|---|
   | Read / read / view / open_file / cat | read_file |
   | Write / create / save_file / put | write_file |
   | Edit / StrReplace / str_replace / patch / modify | edit_file |
   | Bash / Shell / exec / execute_command / run / terminal / cmd | bash |
   | Glob / find_files / file_search | glob |
   | Grep / Search / code_search / ripgrep | grep |
   | WebFetch / browse / fetch_url / http_get / browser | web_fetch |
   | TodoWrite / plan / task_list / update_plan | set_todos |
   | Skill / load_skill / use_skill | skill |
   | Task / Agent / spawn / subagent | spawn_agent |
   | memory / save_memory / remember | remember / recall |
   | codebase_search / semantic_search | search_codebase |
   | AskUserQuestion / ask | ask_user |

   Remove references to capabilities CHODE doesn't have (screenshots, GUI browsing,
   memory APIs other than remember/recall) — rewrite those steps to use bash/web_fetch
   equivalents or note them as manual steps for the user.

3. **Write the CHODE version.** Destination: `{SKILLS_DIR}/<kebab-case-name>/SKILL.md`
   - Frontmatter MUST have `name:` (kebab-case, matches the folder) and a single-sentence
     `description:` that says WHEN to use it — the model only sees the description until
     the skill is loaded, so make it a good trigger.
   - Keep the body focused: procedure steps, commands, edge cases. Cut agent-specific
     fluff ("as an AI assistant...").
   - Copy any helper scripts/data files into the same folder with `bash` (`cp -r`, or
     `Copy-Item -Recurse` on Windows) and reference them by relative path in the body.

4. **Verify.** Run `skill` with the new name to confirm it loads, then tell the user
   it's installed and suggest they check with `/skills`.

## Rules
- One skill per folder. Never overwrite an existing skill without asking.
- If the source is huge, distill — a skill is a playbook, not an archive.
- If the source contains secrets (API keys, tokens), strip them and tell the user.
"""

REPO_ORDER_MD = """---
name: repo-order
description: Put a repository in ORDER — proper folder layout, README, ABOUT.md with story + marketing copy + social posts, CHANGELOG, LICENSE, docs/, tests/, CI — without being asked for each piece
---
# Repo ORDER — make any project look like someone loves it

CHODE's ORDER standard: every repo gets **O**rganized, **R**ecorded, **D**ocumented,
**E**xported, **R**eleased. The deterministic parts (.gitignore, LICENSE, CHANGELOG
skeleton, folder scaffolding) are done by `chode order`. YOU do the parts that need
judgment and taste.

## Procedure
1. `bash`: `chode order --json` (or call the `order_status` tool) to see what is missing.
2. Read the existing README/manifest/entry points so you describe the *real* project.
3. Fill the gaps, in this priority:
   - **README.md** — what it is in one sentence, a 30-second quickstart a beginner can
     follow, features, configuration, contributing, license. Badges at the top.
   - **ABOUT.md** — (a) origin story: why this exists, told like a human; (b) what it does
     and who it's for; (c) marketing copy: a one-liner, a 50-word blurb, a 150-word blurb;
     (d) social posts: 3 tweets/X posts, 1 LinkedIn post, 1 Reddit post (title + body),
     1 Hacker News "Show HN" title + comment; (e) hashtags; (f) a "how to pronounce /
     explain it to your mom" section. Be specific to THIS project, never generic.
   - **CHANGELOG.md** — Keep a Changelog format; seed from git log if history exists.
   - **docs/** — at least docs/README.md pointing at the important docs.
   - **tests/** — if there are none, add a smoke test that imports/runs the entry point.
   - **CI** — a minimal GitHub Actions workflow that runs the tests.
4. Never overwrite a file that already has real content; extend it. Never invent facts
   about the project — if you don't know the author's motivation, ask one question.
5. Finish with a 5-line summary of what you added and what's still missing.
"""


CONNECTION_DOCTOR_MD = """---
name: connection-doctor
description: Fix "can't connect to the model" problems — wrong model name, bad or missing API key, dead local server, rate limits — by listing models, reading the provider's docs, switching provider, and testing until something answers
---
# Connection doctor

Use this when the user says CHODE can't reach its model, a model name was rejected, a key fails,
or they "can't figure out which model to pick". The goal is a WORKING provider+model, verified by
`test_connection`, in as few steps as possible. Be kind; assume the user is new.

## Procedure
1. `test_connection` with no arguments. If it says OK, you're done — explain what works.
2. Read the error kind:
   - **not_found** → `list_models` for that provider. Pick the closest name (prefer the newest version and models that
     support tool calling), `set_config model <name>`, test again. If the list is empty or odd, `web_fetch` the docs URL
     for that provider (below) and read the model names from there.
   - **auth** → the key is missing or wrong. Do NOT ask the user to paste a key into chat. Say exactly which env var or
     `chode setup` step fixes it, then switch to a provider that already works (a local server, another key, or the
     keyless `pollinations` rung) so they can keep working: `set_config provider <name>` → `test_connection`.
   - **network** → for ollama/lmstudio/local: say how to start the server (`ollama serve`, `ollama pull qwen2.5-coder:7b`).
     You may run `ollama list` / `ollama pull <small model>` via bash if ollama is installed. For cloud providers:
     proxy/VPN/base URL; verify with `list_models`.
   - **rate_limit** → explain the quota in one line and fall back to another provider for now.
   - **bad_request** → read the message. If it names a request setting (`temperature`, `top_p`, `top_k`, `max_tokens`),
     CHODE already drops it for that model and remembers that — just `test_connection` again; you can also
     `set_config sampling.temperature default`. Otherwise it's usually a model without tool-calling support, or a wrong
     base URL: pick a different model / fix `base_urls.<provider>`.
   - A model name like `anthropic/opus-5.5` or `Opus 5.5` is a human spelling: `set_config model <name>` normalizes it
     (→ `claude-opus-5-5`) and checks it against the live list; read what it returns.
3. Prefer free when switching: a running Ollama model → `pollinations` (keyless) → a free-tier key the user already has.
4. After every change run `test_connection`. Stop at the first OK.
5. Finish with three short lines: what works now, what was wrong, how to upgrade later (`chode setup`).

## Docs by provider (fetch with web_fetch when the model list isn't enough)
- anthropic: https://docs.anthropic.com/en/docs/about-claude/models/overview
- openai: https://platform.openai.com/docs/models
- gemini: https://ai.google.dev/gemini-api/docs/models
- xai: https://docs.x.ai/docs/models
- groq: https://console.groq.com/docs/models
- openrouter (free models): https://openrouter.ai/models?q=free
- mistral: https://docs.mistral.ai/getting-started/models/models_overview/
- deepseek: https://api-docs.deepseek.com/quick_start/pricing
- cerebras: https://inference-docs.cerebras.ai/models/overview
- ollama (tool-capable models): https://ollama.com/search?c=tools
- pollinations: https://github.com/pollinations/pollinations/blob/master/APIDOCS.md

## Rules
- Never read, print or ask for API keys. Never change anything except provider / model / base_urls / fallbacks / sampling.*.
- Never run shell commands other than `ollama list`, `ollama ps`, `ollama pull <model>`.
- Fewer words, more `test_connection`.
"""


def ensure_builtin_skills():
    """Install the built-in skills; refresh one when CHODE's bundled text changed and the user hasn't edited it
    (a `.builtin` sidecar holds the hash of what CHODE last wrote)."""
    import hashlib
    for name, text in (("skill-porter", SKILL_PORTER_MD), ("repo-order", REPO_ORDER_MD),
                       ("connection-doctor", CONNECTION_DOCTOR_MD)):
        try:
            dest = GLOBAL_SKILLS_DIR / name
            body = text.replace("{SKILLS_DIR}", str(GLOBAL_SKILLS_DIR))
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            skill_file, sidecar = dest / "SKILL.md", dest / ".builtin"
            if skill_file.exists():
                current = skill_file.read_text(encoding="utf-8", errors="replace")
                if current == body:
                    if not sidecar.exists():
                        sidecar.write_text(digest, encoding="utf-8")
                    continue
                last_written = sidecar.read_text(encoding="utf-8").strip() if sidecar.exists() else None
                user_edited = last_written is not None and hashlib.sha256(current.encode("utf-8")).hexdigest() != last_written
                # pre-1.0.2 installs have no sidecar: treat our own unedited 1.0.1 doctor text as refreshable
                legacy_ours = last_written is None and name == "connection-doctor" and "# Connection doctor" in current and "sampling" not in current
                if user_edited or (last_written is None and not legacy_ours):
                    continue
            dest.mkdir(parents=True, exist_ok=True)
            skill_file.write_text(body, encoding="utf-8")
            sidecar.write_text(digest, encoding="utf-8")
        except Exception:
            pass
