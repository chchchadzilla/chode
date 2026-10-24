# Changelog

All notable changes to CHODE are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- **Plan Bridge on Windows.** npm installs `claude`/`codex`/`gemini` as `.cmd` shims; CHODE's multi-line prompt went
  through `cmd.exe` and died with "The syntax of the command is incorrect." CHODE now reads the shim and runs the real
  program (`bin\claude.exe`, or `node <script>`) directly — for the bridge, sign-in, and `/ride`.
- **Signed-out Claude Code is an error, not an answer.** `claude -p` reports "Not logged in · Please run /login" as an
  `is_error` result; CHODE used to show that as the model's reply, so nothing fixed it. It is now an `auth` error.

### Added
- **Sign-in when it's needed.** The first time a plan CLI says it's signed out, CHODE opens its sign-in
  (`claude auth login` / `codex login` / `gemini`) — inline in the terminal, or in its own window from the GUI —
  waits, and retries the message. Once per session; after that it's a clear `[auth]` error with what to do.
- **`/login [claude|codex|gemini]`** — sign a plan CLI in on demand (terminal or GUI).
- **`/fix` / `chode fix` handle plan providers.** They check sign-in status, open the sign-in, and verify the provider
  answers, instead of "fixing" with a ping that passed on the error text. They no longer switch you off your plan.

## [1.0.2] - 2026-10-19

The "it still didn't work" release — from a real first-run failure: `HTTP 400 from anthropic: "temperature is
deprecated for this model."`, a saved model name of `anthropic/opus-5.5`, and a trailing "tip: run chode import".

### Added
- **Model names, normalized and verified.** `config.normalize_model` turns human spellings into API ids
  (`anthropic/opus-5.5` / `Opus 5.5` → `claude-opus-5-5`, `gpt5 mini` → `gpt-5-mini`, `models/gemini-2.5-flash` →
  `gemini-2.5-flash`; OpenRouter ids untouched) — applied on config load, `/model`, `/provider p m`, `/config model`,
  `chode --model`, the wizard and the fixer. `lifeline.verify_model` then checks the name against the provider's **live**
  model list the moment it is set and announces the correction (`'mock-l' isn't a model local knows → using 'mock-1'`);
  it never replaces a totally unrelated name.
- **Parameter self-healing.** A 400 that names a request setting (`temperature`, `top_p`, `top_k`, `max_tokens` …) drops
  it (or renames `max_tokens` → `max_completion_tokens`), retries, and remembers it **per model** (`param_quirks`).
  Known cases are gated up front: Claude 4.7+/5.x and OpenAI reasoning models get no sampling params; Claude ≤ 4.6,
  OpenRouter, Ollama, Groq, Gemini … do.
- **`/sampling`** (also `chode sampling`, launcher menu → *Tuning*, an optional wizard step): see exactly what is sent to
  the current model and why anything is withheld; set temperature / top_p / top_k **globally, per provider or per
  model** (`sampling.overrides`); `default` = let the provider decide; `edit` opens a submenu; `reset`, `forget`.
  A per-model override deliberately bypasses the gate and clears a remembered rejection.
- **The failure block.** Every connection failure (wizard test, `chode health`, in-session) now prints
  `lifeline.what_now`: *what happened* · *what CHODE already did* · *do this now* (specific per error kind: keys page +
  env var + key prefix for `auth`; the corrected name for `not_found`; the setting to flip for a rejected parameter;
  `ollama serve` for a dead local server; proxy/base-URL for `network`) · *three free ways out for this machine* ·
  `/fix` / `chode fix`. `PROVIDER_KEYS` (where to get a key) and `KEY_PREFIXES` added. The import tip only prints after
  a successful test.
- **Import from other drives and any folder.** `chode import --drives` / `/import --drives` (or yes when asked) walks
  every other mounted drive — Windows drive letters, `/Volumes/*`, `/media/*`, `/run/media/*/*`, `/mnt/*` incl. WSL's
  `/mnt/c` — bounded (depth ≤ 4, seconds per drive, system/media folders skipped) for agent homes (`.claude`, `.codex`,
  `.cursor` … under any `Users/<name>`) and stray `SKILL.md` folders, labelled `Claude Code @ E:` / `skills folder @ E:`.
  `chode import <folder…>` / `/import <folder>` takes a skill, a skills folder, a copied `~/.claude` or a project.
- Mock server: `reject_params`. 15 new tests (86 total).

### Fixed
- Command flags after a sub-command (`chode import --yes`, `chode index --full`, `chode ship --no-push`,
  `chode release --draft`, `chode order --json`) were rejected by argparse; they now reach the command.
- `bad_request` hint for a rejected parameter no longer says "try another model".
- The fixer's `set_config` accepts `sampling.*`; Claude Code settings found on other drives keep their drive label.

## [1.0.1] - 2026-10-17

### Added
- **The lifeline.** CHODE no longer dies on a connection error:
  - requests retry on network errors, 429 and 5xx with exponential backoff (`Retry-After` honored); bad keys
    and unknown models are not retried;
  - every failure is classified (`auth` · `not_found` · `rate_limit` · `overloaded` · `network` · `bad_request`)
    and carries a one-sentence hint plus the provider's docs URL;
  - rejected model names are auto-corrected against the provider's live model list (`sonnet`/`opus`/`haiku`
    mean "the newest you have"; retired ids resolve to their newest sibling), then the provider's known-good list;
  - a **fallback ladder** (`fallbacks: "auto"`): other keys → local servers that are actually running → the
    keyless free rung; every switch is announced and session-only (`/provider keep` saves it);
    `last_known_good` is remembered automatically;
  - a **startup guarantee**: a provider that can't possibly answer (no key, server down) is swapped at boot;
  - **`chode fix` / `/fix`**: the connection doctor — a small agent on whatever rung answers, with
    `list_models`, `test_connection`, `set_config` (never API keys) and `web_fetch` for the docs, following the
    built-in `connection-doctor` skill;
  - `chode lifeline` / `/lifeline`: what can answer on this machine and in what order;
  - new providers: `pollinations` (free, keyless, community-run) and `huggingface` (free tier);
  - setup wizard: **"Just make it work (free)"** and **"Free key, 2 minutes"** (opens the signup page for
    Gemini / Groq / OpenRouter / Mistral / Cerebras / Hugging Face); failed connection test offers the doctor;
  - every connection error in a session prints a numbered playbook of free ways out.
- Mock server gained `fail_with`, `valid_models`, `models`, `retry_after` and an Ollama-style `/api/tags`; 11 new tests.

### Changed
- A session fallback is never persisted as the default; `save_config` keeps the user's chosen provider.
- Tests isolate the config file per test.

## [1.0.0] - 2026-10-12

The thicc release. CHODE grows from a single 2,900-line file into a proper package with
twelve new feature areas, a test suite, CI, a browser GUI and a real brand.

### Added
- **Plan Bridge** — `claude-plan`, `codex-plan`, `gemini-plan`, `custom-plan` providers that drive the
  official vendor CLIs in non-interactive mode with CHODE mounted as an MCP server, so your existing
  subscription is the brain and CHODE's tools/permissions/memory are the hands. `chode ride <cli>` for
  the interactive handoff. Command templates live in config so flag changes are a one-line fix.
- **CHODE as an MCP server** (`chode mcp-serve`) — any MCP client (Claude Code, Codex, Gemini CLI,
  Cursor, VS Code) can use CHODE's guarded file/shell tools, search, memory, ORDER, backups and ship.
  Asks permission on the controlling terminal when one is attached.
- **The Gulp** (`chode import` / `/import`) — one-click import from 20+ agents (Claude Code, Codex,
  Gemini CLI, Antigravity, Cursor, Windsurf, VS Code family, Cline, Roo, Kilo, Continue, Copilot,
  OpenCode, Zed, Kiro, Amp, Junie, Aider, OpenClaw, Hermes): rules → memory, SKILL.md → skills,
  commands/prompts (md + Gemini toml) → slash commands, agents → personas, mcpServers (every known
  format incl. Codex TOML and OpenCode) → MCP, permissions → allow/deny, hooks → hooks, VS Code AI
  extensions → report. Secrets stripped on import. Idempotent.
- **Persistent memory** — native reading of CHODE.md / AGENTS.md / CLAUDE.md / GEMINI.md /
  .cursorrules / CONVENTIONS.md / copilot-instructions; episodic memory store (facts, preferences,
  decisions, lessons, todos; project + global) with relevance recall into the system prompt;
  `remember`/`recall` tools; `/remember`, `/memories`, `/forget`; end-of-session reflection;
  `chode memory export|clear|add`.
- **Conscience + ledger** — `~/.chode/CONSCIENCE.md` (seeded, injected, self-amended with dated
  lessons after sessions with incidents) and `~/.chode/ledger.jsonl` recording dangerous commands,
  denials, undos, redactions, out-of-tree writes, deny-list hits, injection attempts, bridge runs.
  `/conscience`, `/ledger`, `chode ledger`.
- **ORDER** — 17-check weighted repo audit with a 0–100 "thiccness" score; deterministic scaffold
  (.gitignore per language, MIT LICENSE, CHANGELOG, docs/, CI workflow, CONTRIBUTING, SECURITY,
  git init) that never overwrites; model-driven README/ABOUT.md/tests via the built-in `repo-order`
  skill; `ABOUT.md` spec with story + marketing copy + social posts; rotating tar.gz backups with
  auto-backup; tidy report; `order_status`/`backup` tools; `/order`, `/about`, `/status`, `/tidy`,
  `/backup`, `chode order [fix]`, `chode backup`.
- **Local RAG** — stdlib BM25 index over line chunks (`.chode/index.json`), optional dense embeddings
  via OpenAI-compatible `/embeddings` (hybrid scoring), incremental by mtime, auto-built in the
  background, `search_codebase` tool, `/search`, `/index`, `chode index|search`.
- **Publish** — `/ship` (stage → secret scan → model-written conventional commit → push → create the
  GitHub repo via `gh` or token if missing → optional Hugging Face upload), `autocommit` off|turn|session,
  `/release vX.Y.Z` (version bump across pyproject/package.json/Cargo/__init__, changelog, tag,
  push, GitHub release), `ship` tool.
- **The Deck** — zero-dependency browser GUI (`chode gui`, `/gui`): SSE streaming chat, tool cards,
  diff previews, permission/question cards, mode switch, cost/context, ORDER score, todos, memory
  sidebar. Localhost + per-launch token.
- **Banner generator** — `chode banner` / `/banner` / `generate_image` tool: collision-style SVG and
  PNG banners + icon for any repo; uses OpenAI / Gemini / xAI image APIs when a key exists.
- **Hooks** — `session_start`, `user_prompt`, `pre_tool`, `post_tool`, `session_end`; Claude Code
  hook JSON format accepted as-is (matchers, exit-2 block, `additionalContext`).
- **Sub-agents** — `spawn_agent` tool with depth limit, read-only option, named personas from
  `~/.chode/agents/*.md` (also `.claude/agents`), `agents.subagent_model`.
- **Streaming** for Anthropic and OpenAI-style APIs (graceful fallback when a server ignores
  `stream`), live markdown styling, status line, `@dir` listings, `@file` tab completion, `/diff`,
  `/git`, `/permissions`, `/hooks`, `/agents`, `/commands`, `ask_user` tool, `chode "prompt"` one-shot.
- **Security** — chained-command prefix matching (every segment must be allowed), `bash_deny`,
  project `.chode/permissions.json`, cloud-metadata SSRF guard, prompt-injection detection on fetched
  pages, sensitive-path warnings, config `chmod 600`, secret scan before every commit, ~15 more
  dangerous-command patterns (git reset --hard, cloud deletes, package publishing, DROP TABLE…).
- Packaging: `pyproject.toml`, `pip install`/`pipx` support, `chode` console script, `python -m chode`,
  `install.sh` / `install.ps1`. Opt-in GitHub Actions workflows (3 OSes × 3 Pythons CI, and a release
  builder) — started manually from the Actions tab, never on push, so they cost nothing by default.
- Tests: 60 offline tests (scripted mock LLM with streaming, mock MCP server, CHODE-as-MCP, GUI).
- Docs: rebuilt README, ABOUT.md, CONTRIBUTING, SECURITY, CHODE.md, docs/.

### Changed
- Repository restructured from `chode.py` into the `chode/` package (`cli`, `repl`, `commands`,
  `agent`, `tools`, `permissions`, `llm`, `mcp`, `ui`, `config`, `paths`, `security`, `session`,
  `skills`, `state` + the new modules above). Launchers (`chode-launcher.py`, `chode-start`,
  `chode-start.bat`) now call the package.
- Default Anthropic model is the latest Sonnet; `opus`/`sonnet`/`haiku`/`fable` aliases.
- Setup wizard leads with "how should CHODE think?" (subscription / API key / local & free).
- Menu gained Deck, Import, Plans and ORDER entries.
- Intro animation ends in a dust burst (matching the banner).

### Removed
- `generate_album_cover.py` and unrelated site assets (one contained a hard-coded API key fragment;
  rotate it if it was real).
- The personal portfolio page under `site/`.

### Security
- See "Security" under Added. Also: MCP tool results and GUI payloads pass through the redactor.

## [0.5.0] - 2026
- Cross-platform release: universal Python launcher, Windows PowerShell/cmd shells, MIT license, docs.

## [0.4.0] - 2025
- Single-file Chad Code: agentic loop, skills, MCP client, sessions, permission modes, splash video.
