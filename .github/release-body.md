**CHODE 1.0.1 — code thicc like a tuna can.** 🥫

> 1.0.1 adds **the lifeline**: retries with backoff, classified errors with plain-English hints, model-name auto-correction, a fallback ladder that ends in a free keyless model, a startup guarantee, and `chode fix` — a connection doctor that repairs your config on whatever model answers. No API key? `chode setup → "Just make it work (free)"`.

The coding harness that works with any AI, rides the subscription you already pay for, imports your gear from every other coding agent in one click, remembers you between sessions, and keeps every repo in ORDER.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/chchchadzilla/chode/main/install.sh | sh   # mac / linux
irm https://raw.githubusercontent.com/chchchadzilla/chode/main/install.ps1 | iex         # windows
pipx install git+https://github.com/chchchadzilla/chode                                 # anywhere (or the wheel below)
chode setup && chode import
```

## What's new (everything — this is the 1.0)

- 💳 **Plan Bridge** — `claude-plan` / `codex-plan` / `gemini-plan` providers drive the official CLIs with CHODE mounted as an MCP server: your plan is the brain, CHODE's tools, permissions and memory are the hands. `chode ride claude|codex|gemini` for the interactive handoff. `chode mcp-serve` exposes CHODE to any MCP client.
- 🥤 **The Gulp** (`chode import`) — one-click import from 20+ agents: Claude Code, Codex, Gemini CLI, Antigravity, Cursor, Windsurf, VS Code family, Cline, Roo, Kilo, Continue, Copilot, OpenCode, Zed, Kiro, Amp, Junie, Aider, OpenClaw, Hermes. Rules → memory, SKILL.md → skills, commands → slash commands, agents → personas, mcpServers → MCP, permissions → allow/deny, hooks → hooks.
- 📐 **ORDER** — 17-check audit scored 0–100, deterministic scaffold (LICENSE, .gitignore, CHANGELOG, docs, CI, CONTRIBUTING, SECURITY), model-written README/ABOUT.md (story + marketing copy + social posts)/tests, rotating backups, tidy report.
- 🧠 **Persistent memory** — native CHODE.md/AGENTS.md/CLAUDE.md/GEMINI.md/.cursorrules; episodic memory with relevance recall and end-of-session reflection; `remember`/`recall` tools.
- 🪞 **Conscience + ledger** — a living CONSCIENCE.md the agent honors and amends; every risky moment logged.
- 🔎 **Local RAG** — stdlib BM25 index (+ optional embeddings), `search_codebase` tool.
- 🚀 **Ship & release** — `/ship` (secret scan, model-written commit, push, repo creation), autocommit, `/release`, Hugging Face uploads.
- 🖥 **The Deck** — zero-dependency browser GUI with streaming, diffs, permission cards, ORDER and memory panels.
- 🎨 **Banners** — `chode banner` generates collision-style banner + icon for any repo (image APIs when available).
- 🪝 Hooks (Claude Code format compatible), sub-agents with personas, streaming TUI with live markdown, status line, `@file` completion, `/diff`, `/git`, hardened security (chained-command allow-listing, deny lists, SSRF guard, injection detection, secret-safe commits).
- 📦 Proper package: `pip`/`pipx` installable, `chode` command, CI on 3 OSes × 3 Pythons, 60 offline tests.

Full details in [CHANGELOG.md](https://github.com/chchchadzilla/chode/blob/main/CHANGELOG.md). Wheels and sdists are attached below.
