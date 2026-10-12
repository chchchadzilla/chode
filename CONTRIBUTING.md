# Contributing to CHODE

Thanks for helping. The bar is "would I want to use this at the end of the day." Keep it simple:

1. **Fork and branch** from `main`.
2. **Dev install:** `pip install -e ".[dev]"` then `pytest -q`. Tests run offline; keep it that way
   (scripted mock LLM in `tests/mock_server.py`, mock MCP in `tests/mock_mcp.py`).
3. **No new hard dependencies.** `requests` is the only one. Optional extras must degrade gracefully.
4. **Python 3.9+.** CI runs 3.9 / 3.12 / 3.13 on Linux, macOS and Windows.
5. **Safety stays honest.** Anything that writes, runs, or sends goes through `permissions.py`, logs
   to the ledger when risky, and is undoable where possible.
6. **Keep the TUI and the Deck in parity.** If you add a UI event, implement it in both `ui.TerminalUI`
   and `gui.WebUI`.
7. Open a pull request that says *why*. `/ship` writes a decent commit message if you ask it to.

Ideas that would be welcome: more importer sources, more image backends, a `--watch` mode, LSP-based
symbol search for the index, localized README translations, and better Windows terminal rendering.

No contribution is too small. Typos count. Don't be a chode.
