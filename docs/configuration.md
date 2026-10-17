# Configuration

Precedence (later wins): built-in defaults → `~/.chode/config.json` → `./.chode/config.json`.
Also merged from the project: `./.chode/mcp.json` (`{"mcpServers": {...}}` or a bare map),
`./.chode/permissions.json` (`{"allow": [...], "deny": [...]}`), `./.chode/hooks.json`.

Set `CHODE_HOME` to relocate `~/.chode` (tests do this).

| key | default | meaning |
|---|---|---|
| `provider` | `anthropic` | see README providers table; `*-plan` providers use the vendor CLI |
| `model` | `""` | empty = provider default; Anthropic aliases `opus`/`sonnet`/`haiku`/`fable` |
| `max_tokens` / `temperature` | 8192 / 0.2 | |
| `stream` | true | stream tokens (falls back automatically if a server ignores it) |
| `base_urls.<provider>` | | override endpoint (Azure needs the deployment URL) |
| `api_keys.<provider>` | | keys (env vars take priority); file is chmod 600 |
| `mode` | `ask` | `plan` / `ask` / `edits` / `yolo` |
| `bash_allow` | git status, git diff, ls, … | command prefixes auto-approved (every chained segment must match) |
| `bash_deny` | `[]` | prefixes always refused |
| `redact_secrets` | true | scrub secret-looking strings from tool output |
| `allow_outside_cwd` | false | writes outside the working dir (and temp) prompt |
| `allow_private_urls` | true | `web_fetch` may hit localhost/LAN (cloud metadata always blocked) |
| `auto_compact_tokens` | 120000 | summarize history past this context size (0 = off) |
| `mcp_servers` | `{}` | `{"name": {"transport": "stdio", "command": "…", "args": [], "env": {}}}` or `{"url": "…", "headers": {}}`; `"disabled": true` to keep but skip |
| `hooks` | `{}` | see [extending.md](extending.md) |
| `name` / `theme` / `intro` / `skip_menu` / `shell` | | personalization; `shell` = `auto`/`powershell`/`cmd` on Windows |
| `memory.auto_reflect` | true | ask the model what to remember at session end |
| `memory.inject` | 12 | how many memories to recall into the system prompt |
| `memory.max_entries` | 2000 | per scope |
| `conscience.reflect` | true | amend CONSCIENCE.md after sessions with incidents |
| `order.auto_check` | true | ORDER status at session start + in the system prompt |
| `order.auto_backup_hours` | 24 | 0 = off |
| `order.backup_keep` / `order.backup_max_mb` | 10 / 200 | rotation; skip huge projects |
| `rag.auto_index` | true | build/refresh the index in the background at session start |
| `rag.embeddings` | false | dense vectors via `/embeddings` (OpenAI-style providers only) |
| `rag.embedding_model` | `""` | default `text-embedding-3-small` (OpenAI) / `nomic-embed-text` (Ollama) |
| `rag.max_files` | 4000 | |
| `publish.autocommit` | `off` | `turn` (local commit after each change) / `session` (on quit) |
| `publish.remote` | `origin` | |
| `publish.huggingface_repo` | `""` | `user/repo` to upload on `/ship` (needs `hf` CLI) |
| `publish.sign_off` | `""` | truthy → `--signoff` |
| `plans.claude|codex|gemini|custom` | templates | `command`, `model_flag`, `resume_flag` with `{prompt} {model} {resume} {mcp_config} {system} {cwd}` |
| `gui.port` / `gui.open_browser` | 7331 / true | |
| `banner.image_provider` | `auto` | `openai` / `gemini` / `xai` / `auto` |
| `agents.subagent_model` / `agents.max_depth` | `""` / 2 | |
| `fallbacks` | `"auto"` | lifeline ladder: `"auto"`, a list of `"provider"` / `"provider:model"`, or `false` (see [lifeline.md](lifeline.md)) |
| `retries` | 3 | per-request retries for network errors / 429 / 5xx (exponential backoff, Retry-After honored) |
| `last_known_good` | `{}` | written automatically when a provider answers; tried first when the default can't |

## Environment variables

`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`,
`GROQ_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`, `TOGETHER_API_KEY`, `CEREBRAS_API_KEY`,
`MOONSHOT_API_KEY`, `PERPLEXITY_API_KEY`, `AZURE_OPENAI_API_KEY`, `GITHUB_TOKEN`/`GH_TOKEN` (repo
creation without `gh`), `CHODE_HOME`, `CHODE_NO_INTRO`, `CHODE_NO_SPLASH`, `CHODE_SPLASH`,
`CHODE_BANNER_FONT`, `NO_COLOR`.
