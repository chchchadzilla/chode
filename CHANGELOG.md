# Changelog

All notable changes to CHODE are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

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
