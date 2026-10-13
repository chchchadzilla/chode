# Memory, conscience and the ledger

## Instruction files (read natively)

Looked up from the working directory up to the repo root, nearest copy of each name wins,
in this precedence: `CHODE.md`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `AGENT.md`, `CONVENTIONS.md`,
`.cursorrules`, `.windsurfrules`, `.clinerules`, `.github/copilot-instructions.md`,
`.junie/guidelines.md`. Plus `~/.chode/CHODE.md` (global). `/memory` shows what's loaded.
`#note` appends to `./CHODE.md`. `/init` has the model write one.

## Episodic memory

Files: `~/.chode/memory/<project-hash>.jsonl` and `global.jsonl`. Entry:
`{"id", "ts", "kind", "text", "tags", "source", "project", "hits"}` with kind ∈ fact · preference ·
decision · lesson · todo.

Sources: you (`/remember`, `#note`, `chode memory add`), the model (`remember` tool), end-of-session
reflection (the model is asked for ≤5 JSON items worth keeping; only runs after ≥3 user turns, not
in one-shot mode, not for plan providers).

Recall: at session start CHODE scores memories by token overlap with the project name + instruction
files + your first message (identifier-aware tokenizer), kind weight (preferences > lessons >
decisions > facts), recency and past hits; the top `memory.inject` plus all global preferences and the
four newest project entries are injected under "Things you remember". The `recall` tool searches on
demand. Near-duplicates are merged; stores are capped at `memory.max_entries`.

`chode memory export` writes a markdown dump; `chode memory clear [project|global]` wipes a scope.

## Conscience

`~/.chode/CONSCIENCE.md` is seeded with CHODE's principles and injected into every system prompt.
After a session that had ledger events, the model is asked for one ≤25-word lesson; it's appended
under `## Learned` with a date (bounded to 60 lines, deduped). Edit the file freely — it's yours.

## Ledger

`~/.chode/ledger.jsonl`. Events: `danger_allowed`, `danger_denied`, `deny_list`, `outside_cwd`,
`denied`, `undo`, `redacted`, `secret_in_commit`, `injection`, `hook_block`, `sensitive_read`,
`force`, `plan_bridge`, `mcp_denied`. `/ledger [n]`, `chode ledger [n]`.
