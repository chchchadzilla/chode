# CHODE.md — project memory for CHODE itself

CHODE reads this file at the start of every session in this repo (so do Claude Code,
Codex and friends, via `chode import` or by renaming it AGENTS.md).

## What this is
A local-first, provider-agnostic agentic coding harness. Python ≥ 3.9, one dependency (`requests`),
everything else stdlib. Package lives in `chode/`; entry point `chode.cli:main`.

## Build / run / test
- Dev install: `pip install -e ".[dev]"`
- Run: `chode` (menu) · `chode -p "…"` (one-shot) · `chode gui` (browser) · `python -m chode`
- Tests: `pytest -q` — fully offline. `tests/mock_server.py` is a scripted OpenAI-style LLM
  (streaming + non-streaming); `tests/mock_mcp.py` is a one-tool MCP server. `tests/conftest.py`
  points `CHODE_HOME`/`HOME` at a temp dir — never touch the real `~/.chode` from tests.
- Brand assets: `python scripts/make_brand.py` regenerates `assets/`.

## Layout (one module per concern)
`cli` (argparse) → `menu` / `repl` (Repl class: boot, turns, wrap-up) → `commands` (slash commands) →
`agent` (system prompt, loop, sub-agents) → `tools` (definitions + executors) → `permissions`.
`llm` (Anthropic/OpenAI/Azure/plan; streaming) · `plans` (Plan Bridge, `chode ride`) ·
`mcp` (client) / `mcp_server` (CHODE as server) · `memory` · `conscience` (ledger) · `order` ·
`publish` · `rag` · `importer` · `hooks` · `skills` · `banner` · `gui` · `ui` · `config` · `paths` ·
`security` · `session` · `state` (the App singleton) · `wizard` · `doctor`.

## Conventions
- No new hard dependencies. Optional ones (Pillow) must degrade gracefully.
- Python 3.9 compatible: no `match`, no `X | Y` unions at runtime, no `tomllib` without fallback.
- Every file write goes through `App.checkpoints.before_modify` so `/undo` works.
- Every risky decision logs to `conscience.log(...)`.
- Tool executors return strings; the loop redacts secrets before anything reaches a model.
- UI code never prints from inside tools — go through `state.app().ui`.
- Keep the TUI and the Deck (GUI) at feature parity: both implement the `TerminalUI` interface.
- Commit messages: Conventional Commits. `/ship` writes them.
