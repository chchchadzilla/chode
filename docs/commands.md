# Commands

## Input shortcuts

| type | effect |
|---|---|
| `@path/to/file` | attach the file's contents to your message (`@dir/` attaches a listing). Tab completes. |
| `!command` | run a shell command yourself; its output becomes context for your next message |
| `#some note` | append a note to `./CHODE.md` (and to episodic memory) |
| line ending in `\` | continue on the next line |
| `/name args` | slash command (tab completes) |

## Slash commands

### Modes & brains
| command | |
|---|---|
| `/mode [plan\|ask\|edits\|yolo]` | show/set permission mode |
| `/model [name]` | show/set model (`opus`/`sonnet`/`haiku`/`fable` aliases for Anthropic) |
| `/models` | list the provider's models |
| `/provider [name] [model]` | switch provider (and optionally model) |
| `/plans` | detect installed plan CLIs; offer to switch |
| `/ride claude\|codex\|gemini [args]` | open the vendor TUI with CHODE mounted via MCP |

### Memory & mindfulness
| command | |
|---|---|
| `/remember <text> [--global] [--kind fact\|preference\|decision\|lesson\|todo]` | save a memory |
| `/memories` | list memories (newest last) |
| `/forget <id>` | delete one |
| `/memory` | show the instruction files currently loaded |
| `/init` | have the model write a `CHODE.md` for this repo |
| `/conscience` | print CONSCIENCE.md |
| `/ledger [n]` | last n risky events |

### ORDER
| command | |
|---|---|
| `/status` | ORDER score + checks |
| `/order` | scaffold the essentials, then hand README/ABOUT/tests to the model |
| `/about` | write/improve ABOUT.md |
| `/tidy` | stray-file report |
| `/backup [note]` · `/backup list` · `/backup restore N` | snapshots (restore goes to a sibling folder, never your tree) |

### Publish
| command | |
|---|---|
| `/ship [message] [--no-push] [--force]` | stage, secret-scan, commit, push (creates the GitHub repo if needed) |
| `/release vX.Y.Z [--draft]` | bump, changelog, tag, push, GitHub release |
| `/banner [name]` | banner.svg/.png + icon.svg into ./assets |

### Brain & gear
| command | |
|---|---|
| `/index [--full]` | (re)build the local codebase index |
| `/search <query>` | query it |
| `/skills [add <dir\|git-url> [name]]` | list / install skills |
| `/agents` | list sub-agent personas |
| `/mcp [reload]` | MCP server status |
| `/hooks` | list hooks |
| `/permissions` | mode, session always-list, allow/deny lists |
| `/commands` | list custom commands |
| `/import` | the gulp |

### Session
| command | |
|---|---|
| `/undo` | revert CHODE's last file change (repeat to go further back) |
| `/diff` | `git diff --stat` + files touched this session |
| `/git` | `git status -sb` |
| `/cost` | tokens, est. cost, context % |
| `/compact` | summarize history |
| `/clear` | wipe history |
| `/resume` | pick a previous session in this directory |
| `/export [file]` | transcript → markdown |
| `/config [key value]` | view/set config (dotted keys, JSON values ok) |
| `/theme [color]` | cycle/set accent |
| `/gui` | open the Deck for this session |
| `/doctor` | environment audit |
| `/intro` | replay the collision |
| `/exit` | quit (also Ctrl-D) |

### Custom commands
Any `*.md` in `~/.chode/commands/`, `./.chode/commands/` or `./.claude/commands/` is `/<stem>`.
Optional frontmatter `description:`. `$ARGUMENTS` is replaced by what you typed after the command.
Subfolders become `/<folder>:<name>`.

## CLI

```
chode [command] [args] [-p PROMPT] [-c] [--provider P] [--model M] [--mode MODE] [--yolo]
      [--no-mcp] [--no-intro] [--cwd DIR] [--port N] [--version]
```

| command | |
|---|---|
| *(none)* | menu on a terminal; chat when piped |
| `chat` / `-p "…"` / `chode "…"` | chat / one-shot (stdin is appended when piped) |
| `-c` | continue the last session in this directory |
| `menu` · `setup` · `doctor` · `health` | |
| `import [--yes]` (alias `migrate`) | the gulp; `--yes` imports everything new |
| `plans` · `ride <cli> [args]` | Plan Bridge |
| `order [fix\|--json]` · `backup [list\|restore N\|note]` | ORDER |
| `index [--full]` · `search <q>` | RAG |
| `banner [name]` · `ship [msg] [--no-push] [--force]` · `release vX.Y.Z [--draft]` | publish |
| `gui [--port N]` | the Deck |
| `mcp-serve [--mode M]` | run CHODE as an MCP server on stdio |
| `skills [add\|remove …]` · `memory [export\|clear\|add …]` · `ledger [n]` · `conscience` · `about` · `version` | |

Exit code of `chode health` is 0 when healthy, 1 otherwise (handy in scripts).
