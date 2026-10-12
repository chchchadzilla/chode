# Plan Bridge

Ride the AI subscription you already pay for. No API key. No second bill.

## How it works

1. You pick `claude-plan`, `codex-plan` or `gemini-plan` (`chode setup` → "Subscription I already
   pay for", or `/provider claude-plan`).
2. For each turn, CHODE renders a command from the template in `config.json → plans.<name>.command`
   and runs the vendor CLI in non-interactive mode. Default templates:

   ```
   claude -p {prompt} --output-format json --tools "" --strict-mcp-config --mcp-config {mcp_config} --allowedTools mcp__chode__* {model} {resume}
   codex exec --json --skip-git-repo-check {model} {prompt}        (+ -c mcp_servers.chode.… overrides)
   gemini -p {prompt} --output-format json {model} {resume}
   ```
   `{prompt}` is substituted token-wise (never through a shell), so quotes and newlines are safe.
3. `{mcp_config}` points at a temp file that registers **CHODE itself** (`python -m chode mcp-serve`)
   as an MCP server. With Claude's built-in tools disabled (`--tools ""`), the model thinks on your plan
   and acts through CHODE's tools: guarded `bash`, `write_file`, `edit_file`, `search_codebase`,
   `remember`, `order_status`, `backup`, `ship`, …
4. CHODE parses the JSON result (text, session id, usage), streams the text into your TUI/GUI, and
   resumes the vendor session next turn (`{resume}` → `--resume <id>`) when the CLI supports it;
   otherwise it packs a compact transcript into the prompt.

Mode mapping: `plan` → read-only server, `ask`/`edits` → edits lane, `yolo` → yolo (+ Claude
`--permission-mode bypassPermissions`, Codex `--dangerously-bypass-approvals-and-sandbox`).

Cost shows as "covered by your subscription". Each run is logged to the ledger as `plan_bridge`.

## What you give up / keep

- Give up: interactive prompts *inside* the vendor process. CHODE's MCP server prompts on the
  controlling terminal when there is one; otherwise it refuses what the mode doesn't allow and tells
  the model why.
- Keep: memory, ORDER, ledger, conscience, hooks, skills (via the system context), secret redaction,
  dangerous-command guard, the Deck.

## `chode ride`

The reverse direction: open the vendor's own TUI with CHODE mounted.

```
chode ride claude      # claude --mcp-config <chode> --append-system-prompt "<memory + conscience>"
chode ride codex       # codex -c mcp_servers.chode.command=… (+ a marked block in AGENTS.md)
chode ride gemini      # writes mcpServers.chode into ./.gemini/settings.json (+ GEMINI.md block)
```

## CHODE as an MCP server (for anything else)

```json
{"mcpServers": {"chode": {"command": "python", "args": ["-m", "chode", "mcp-serve", "--mode", "edits"]}}}
```

Drop that into Cursor, VS Code, Claude Desktop, Zed… Set `CHODE_MCP_CWD` to pin the working directory.

## Custom CLIs

```json
"plans": {"custom": {"command": "mycli --prompt {prompt} --json", "model_flag": "--model {model}", "resume_flag": ""}}
```
Then `/provider custom-plan`. Output is parsed as JSON (`result`/`response`/`content`) when possible,
else used verbatim.

## Installing the CLIs

- Claude Code: `npm i -g @anthropic-ai/claude-code` → `claude` → log in with your Pro/Max account
- Codex: `npm i -g @openai/codex` → `codex login`
- Gemini CLI: `npm i -g @google/gemini-cli` → `gemini` → sign in with Google
- Grok: no agent CLI with subscription login exists yet; use the `xai` provider with an API key.

`chode plans` / `chode doctor` show what's detected.
