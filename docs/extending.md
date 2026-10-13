# Extending CHODE

## Skills (`SKILL.md` folders)

Portable with Claude Code / Codex / OpenClaw. Live in `~/.chode/skills/<name>/`, `./.chode/skills/`,
and are also read in place from `./.claude/skills/`, `./.codex/skills/`, `./.agents/skills/`.

```
---
name: deploy
description: Ship this service to production safely (use when the user says deploy/release/ship)
---
# Deploy
1. run the tests …
```

The model sees only the description until it calls the `skill` tool — make it a good trigger.
Install: `/skills add <dir|git-url> [name]`, `chode skills add …`, or `chode import`.
Built-ins: `skill-porter` (convert anything into a skill), `repo-order` (ORDER).

## Custom slash commands

`~/.chode/commands/<name>.md` (or `./.chode/commands/`, `./.claude/commands/`):

```
---
description: review a file for bugs
---
Review $ARGUMENTS for bugs and suggest fixes. Be specific.
```

## Sub-agent personas

`~/.chode/agents/<name>.md` (or `./.chode/agents/`, `./.claude/agents/`), frontmatter `name`,
`description`, optional `model`. The model calls `spawn_agent(task, agent="name")`. Depth-limited by
`agents.max_depth`; `read_only: true` runs the sub-agent in plan mode.

## Hooks

```json
"hooks": {
  "session_start": [{"command": "git fetch -q"}],
  "user_prompt":   [{"command": "python scripts/lint_prompt.py"}],
  "pre_tool":      [{"match": "bash|write_file", "command": "python scripts/guard.py", "timeout": 20}],
  "post_tool":     [{"match": "edit_file", "command": "npx prettier --write \"$CHODE_FILE\""}],
  "session_end":   [{"command": "say done"}]
}
```

Claude Code's format (`PreToolUse` + `matcher` + `hooks[].command`) is accepted unchanged, and
matchers may use Claude tool names (`Bash`, `Edit`, `Write`, `Read`, …).

Protocol: JSON on stdin (`event`, `tool`/`tool_name`, `args`/`tool_input`, `tool_output`, `cwd`,
`session_id`, `prompt`); env `CHODE_EVENT`, `CHODE_TOOL`, `CHODE_CWD`, `CHODE_FILE`. Exit 2 blocks
(stderr = reason). Exit 0 with JSON `{"decision": "block", "reason": …}` blocks;
`{"additionalContext": …}` is appended to the model's context. Project hooks: `./.chode/hooks.json`.

## MCP

Client: `config.json → mcp_servers` (stdio or http), `./.chode/mcp.json`, or `chode import`.
Tools appear as `mcp__<server>__<tool>` and are never auto-approved outside `yolo`/`always`.
Server: `chode mcp-serve` (see [plan-bridge.md](plan-bridge.md)).

## Tools (for contributors)

Add a dict to `chode/tools.py → TOOLS` (`name`, `description`, `input_schema`, `safe`) and an executor
in `TOOL_EXECUTORS`. `safe: True` means read-only / no side effects; everything else goes through
permissions. Write files via `app.checkpoints.before_modify(path)` first. Return a string.
