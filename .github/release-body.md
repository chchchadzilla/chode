**CHODE 1.0.2 — code thicc like a tuna can.** 🥫

> 1.0.2 is the "it still didn't work" release, built from a real first run: `HTTP 400 from anthropic: "temperature is deprecated for this model."`, a saved model of `anthropic/opus-5.5`, and a useless "tip: run chode import" afterwards. Now: **model names are normalized and checked against the live list the moment you set them**, **settings a model won't take are dropped, retried and remembered per model**, **`/sampling` lets you set temperature / top_p / top_k globally, per provider or per model**, **every failure prints the whole "what do I do now" answer**, and **`chode import --drives` finds your skills on other drives**.

The coding harness that works with any AI, rides the subscription you already pay for, imports your gear from every other coding agent in one click, remembers you between sessions, and keeps every repo in ORDER.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/chchchadzilla/chode/main/install.sh | sh   # mac / linux
irm https://raw.githubusercontent.com/chchchadzilla/chode/main/install.ps1 | iex         # windows
pipx install git+https://github.com/chchchadzilla/chode                                 # anywhere (or the wheel below)
chode setup && chode import --drives
```

## What's new in 1.0.2

- 🔤 **Model names fix themselves** — `anthropic/opus-5.5`, `Opus 5.5`, `gpt5 mini` → `claude-opus-5-5`, `gpt-5-mini`; then verified against the provider's live model list on `/model`, `/provider`, in the wizard and via `chode --model`. Typos resolve to the closest real id, out loud.
- 🎚 **Sampling that respects the model** — Claude 4.7+/5.x reject `temperature`; CHODE knows, learns the rest from the 400, drops the setting, retries, remembers it per model. `/sampling` shows what's sent and sets temperature / top_p / top_k globally, per provider or per model (OpenRouter and Ollama models that take them still get them).
- 🧭 **The failure block** — what happened · what CHODE already did · do this now (specific to the error) · three free ways to be coding in 2 minutes · `/fix`. No more one-line tips.
- 💾 **Import from other drives** — `chode import --drives` scans D:, E:, `/Volumes/*`, `/media/*`, `/mnt/*` (incl. WSL) for agent folders and SKILL.md skills; `chode import <folder>` takes any folder.
- 🐛 Sub-command flags (`--yes`, `--full`, `--no-push`, `--draft`, `--json`) work again.

## Since 1.0.0

- 🪢 **The lifeline** (1.0.1) — retries with backoff, classified errors with hints, model auto-correction, a fallback ladder ending in a free keyless model, a startup guarantee, `chode fix`.
- 💳 **Plan Bridge** — `claude-plan` / `codex-plan` / `gemini-plan` drive the official CLIs with CHODE mounted as an MCP server.
- 🥤 **The Gulp** — one-click import from 20+ agents. 📐 **ORDER** — audit, scaffold, ABOUT.md, backups. 🧠 **Persistent memory**. 🪞 **Conscience + ledger**. 🔎 **Local RAG**. 🚀 **Ship & release**. 🖥 **The Deck** GUI. 🎨 **Banners**. 🪝 Hooks, sub-agents, streaming TUI, hardened security.
- 📦 `pip`/`pipx` installable, `chode` command, 86 offline tests.

Full details in [CHANGELOG.md](https://github.com/chchchadzilla/chode/blob/main/CHANGELOG.md). Wheels and sdists are attached below.
