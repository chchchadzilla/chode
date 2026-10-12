# The Gulp — `chode import`

One command. One confirm. Everything you set up in other coding agents comes along; nothing is
removed from them.

```
chode import            # interactive: numbered list, pick all / new / 1,3-5
chode import --yes      # everything you don't already have
/import                 # same, inside a session
```

## What is scanned

| agent | user-level | project-level |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md`, `skills/`, `commands/`, `agents/`, `settings.json`, `~/.claude.json` | `CLAUDE.md`, `.claude/{CLAUDE.md,skills,commands,agents,settings.json,settings.local.json}`, `.mcp.json` |
| Codex | `~/.codex/config.toml`, `AGENTS.md`, `prompts/`, `skills/` | `AGENTS.md`, `.codex/skills`, `.agents/skills` |
| Gemini CLI | `~/.gemini/settings.json`, `GEMINI.md`, `commands/*.toml` | `GEMINI.md`, `.gemini/settings.json`, `.gemini/commands` |
| Antigravity | `~/.gemini/antigravity/{mcp_config.json,rules}`, `~/.antigravity/{mcp_config.json,mcp.json,extensions}` | `.agent/rules/`, `.agent/workflows/` |
| Cursor | `~/.cursor/mcp.json`, `~/.cursor/extensions` | `.cursorrules`, `.cursor/rules/*.mdc`, `.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/{mcp_config.json,memories}` | `.windsurfrules`, `.windsurf/rules` |
| VS Code family (Code, Insiders, Cursor, Windsurf, Antigravity, VSCodium, Trae) | `User/mcp.json`, `User/settings.json` (Copilot instructions), `User/prompts/`, `~/.vscode/extensions` | `.vscode/mcp.json`, `.vscode/settings.json` |
| Cline / Roo / Kilo | `globalStorage/*/settings/*mcp_settings.json`, `~/Documents/Cline/Rules`, `~/.roo/rules` | `.clinerules`, `.roo/rules`, `.kilocode/rules` |
| Copilot | | `.github/copilot-instructions.md`, `.github/instructions/`, `.github/prompts/`, `.github/agents/` |
| Continue | `~/.continue/config.{json,yaml}`, `rules/` | `.continue/rules` |
| OpenCode | `~/.config/opencode/{opencode.json,command,agent}` | `opencode.json`, `.opencode/{command,agent}` |
| Zed | `~/.config/zed/settings.json` (`context_servers`) | `.rules` |
| Kiro · Amp · Junie · Aider | `~/.aider.conf.yml` | `.kiro/steering`, `AGENT.md`, `.junie/guidelines.md`, `CONVENTIONS.md`, `.aider.conf.yml` |
| OpenClaw · Hermes | `~/.openclaw`, `~/.config/openclaw`, `~/.clawdbot`, `~/.moltbot`, `~/.hermes`, … (skills + configs) | |

## What it becomes

| found | becomes | where |
|---|---|---|
| rules / instruction files | a section in `CHODE.md` with a provenance marker (project files → `./CHODE.md`, global → `~/.chode/CHODE.md`) | memory |
| `SKILL.md` folders | skills (copied) | `~/.chode/skills/<name>/` |
| `commands/*.md`, `prompts/*.md`, `*.prompt.md`, Gemini `*.toml` (`prompt = …`, `{{args}}` → `$ARGUMENTS`) | slash commands | `~/.chode/commands/<name>.md` |
| `agents/*.md` | sub-agent personas | `~/.chode/agents/<name>.md` |
| `mcpServers` / `servers` / `context_servers` / `mcp_servers` (TOML) / OpenCode `mcp` | MCP servers (stdio + http) | `config.json → mcp_servers` |
| Claude `permissions.allow: ["Bash(npm test:*)"]` | `bash_allow` prefix `npm test` | config |
| `permissions.deny` | `bash_deny` | config |
| Claude `hooks` | hooks, format kept as-is | config |
| Copilot `codeGeneration.instructions` | memory | `~/.chode/CHODE.md` |
| installed AI extensions | a report line ("CHODE covers these") | — |
| Codex / Aider `model` | a note | — |

Secret-looking strings inside rule files are replaced with `[REDACTED-SECRET]` on import.
Importing twice is a no-op (`= already imported`).

## Not compatible? Use the porter

For formats the scanner doesn't know, the built-in **skill-porter** skill teaches the model to rewrite
any prompt/plugin/skill into a CHODE skill with the tool names mapped: "convert ~/old-agent/stuff into
a chode skill".
