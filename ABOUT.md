# ABOUT CHODE

*This file exists because CHODE makes one for every repo it touches. It seemed rude not to have one for itself.*

## The story

It started as **Chad Code**: one Python file, one dependency, a terminal, and the conviction that a coding agent shouldn't care which AI company you like this month. Claude, GPT, Gemini, Grok, DeepSeek, a Llama on your laptop — same loop, same tools, same you.

Then someone else shipped a thing called "chadcode." Fine. The name was changed to the only thing left that sounded right when CHAD and CODE smash together at speed.

CHODE 1.0 is what happens when you ask: *what are people actually switching coding agents for?* Not the model — the model is a config key. They switch for the little things: the rules file they already wrote, the slash commands they already made, the MCP servers they already wired up, the subscription they already pay for, and the fact that every new tool makes them set all of it up again. So CHODE eats all of it (`chode import`), rides whatever plan you have (`claude-plan`, `codex-plan`, `gemini-plan`), remembers what you told it last Tuesday, and — this is the part nobody else does — refuses to leave your repo a mess. README, ABOUT, LICENSE, CHANGELOG, tests, CI, backups, clean commits. Every repo. Without being asked.

The tagline is "code thicc like a tuna can." Thicc is dense, solid, and surprisingly elegant for something you can buy at a gas station. That's the bar.

## What it does, who it's for

CHODE is an agentic coding harness: you describe what you want, it reads your code, edits files, runs commands, writes docs, commits and pushes, asking permission along the way. It runs in your terminal or in a local browser GUI.

- **Never coded?** `chode` → Setup → pick a free local model or the plan you already pay for → type "make me a website for my bakery." It explains like you're smart but new.
- **Code all day?** Streaming TUI, local RAG over your repo, hooks, skills, sub-agents, MCP in both directions, a permission model that respects chained commands, and `/ship` that writes the commit message so you don't have to.
- **Teams?** Project-level config, permissions and hooks in `.chode/`; `AGENTS.md`/`CLAUDE.md` read natively; `chode mcp-serve` so any other agent can use CHODE's memory and ORDER tools.

## Marketing copy

**One-liner:** CHODE is the coding agent that works with any AI, rides the subscription you already pay for, imports your setup from every other tool in one click, and keeps every repo in order.

**50 words:** CHODE is a local-first AI coding harness. It talks to Claude, GPT, Gemini, Grok, DeepSeek or a free model on your laptop — or rides your existing Claude Max / ChatGPT Pro / Gemini Ultra plan. One command imports your rules, skills and MCP servers from every other agent. And it keeps your repos documented, backed up and shipped.

**150 words:** Every coding agent wants to be your only coding agent. CHODE doesn't. It's a single Python package with one dependency that runs the same agent loop against any model — frontier APIs, your existing subscription via the vendor's own CLI, or a free local model — and imports everything you've already set up elsewhere: Claude Code skills and hooks, Cursor rules, Codex config, VS Code MCP servers, Gemini commands, Copilot instructions. Twenty-plus tools, one `chode import`.

Then it does the thing nobody else does: it keeps your project in ORDER. Every repo gets a real README, an ABOUT.md with the story and ready-to-post marketing copy, a license, changelog, tests, CI, rotating backups and clean conventional commits — automatically. It remembers your preferences between sessions, keeps a ledger of every risky moment, and holds itself to a conscience file it updates from experience. Safety without a nanny. Elegance where none should belong. Code thicc like a tuna can.

## Social posts

**X / Twitter**

1. I was tired of re-doing my setup every time a new coding agent dropped. So I built one that eats all the others' configs in one command and rides whatever AI plan you already pay for. CHODE 1.0. code thicc like a tuna can. 🥫 github.com/chchchadzilla/chode
2. Your coding agent should leave your repo *better* than it found it. CHODE audits every project (README, ABOUT, license, tests, CI, secrets, backups), scores it 0–100, and fixes the gaps without being asked. "flat" → "tuna can." 📐
3. No API key? No problem. CHODE drives the `claude` / `codex` / `gemini` CLIs with itself mounted as an MCP server, so your Max/Pro/Ultra plan is the brain and CHODE's tools, memory and safety rails are the hands. 💳 Free local models work too.

**LinkedIn**

Shipping CHODE 1.0 today — an open-source, local-first coding agent built around one idea: the model is a config key, not a religion.

It runs the same agent loop on Claude, GPT, Gemini, Grok, DeepSeek or a free local model, and it can ride the subscription you already pay for instead of a second API bill. `chode import` pulls your rules, skills, commands, MCP servers, permissions and hooks out of Claude Code, Codex, Cursor, VS Code, Gemini CLI and a dozen others in one confirm.

The part I'm proudest of is ORDER: every repo gets a real README, an ABOUT.md with marketing copy, a license, changelog, tests, CI, backups and clean commits — automatically. Plus persistent memory, a risk ledger, and a conscience file the agent updates from experience.

Python, one dependency, MIT. Feedback welcome. 🔗 github.com/chchchadzilla/chode

**Reddit** (r/programming, r/LocalLLaMA, r/ClaudeAI)

*Title:* I built a coding agent that imports your setup from every other coding agent and keeps your repos in order (open source, 1 dependency)

*Body:* Hey all. CHODE started as a single-file "works with any model" coding CLI. 1.0 adds the stuff I actually wanted: `chode import` scans Claude Code, Codex, Cursor, VS Code, Gemini CLI, Antigravity, Windsurf, Cline, Continue, Copilot, OpenCode, Zed, etc. and converts rules → memory, SKILL.md → skills, commands → slash commands, mcpServers → MCP, permissions → allow/deny lists, hooks → hooks. A "Plan Bridge" that uses the official `claude`/`codex`/`gemini` CLIs so your subscription pays instead of an API key (CHODE mounts itself as an MCP server so its permissions/memory still apply). Persistent memory with end-of-session reflection. A local BM25 index so it reads less of your repo. And ORDER: it audits and scaffolds README/ABOUT/LICENSE/CHANGELOG/tests/CI/backups for every project, scored 0–100. Zero-dep browser GUI too. Works fully offline with Ollama. MIT, Python 3.9+, ~60 tests. Roast it: github.com/chchchadzilla/chode

**Show HN**

Show HN: CHODE – a coding agent that imports your config from every other agent and keeps repos in order

Comment: Built this because every agent makes you redo your rules/skills/MCP setup, and none of them care what state they leave your repo in. One dependency (requests), everything else stdlib — including the browser GUI and the BM25 index. Happy to answer questions about the Plan Bridge (riding Claude/Codex/Gemini subscriptions via their CLIs + MCP) or the permission model.

**Hashtags:** #opensource #ai #codingagent #python #claude #openai #gemini #ollama #localllm #devtools #mcp #buildinpublic

## Explain it to your mom

"You know how you can type a question to an AI and it answers? This one can also *do* things on the computer — write the program, test it, fix it, and put it online — and it asks me before anything risky. It works with whichever AI I'm already paying for, remembers what I told it last time, and keeps the project folder tidy so I don't have to. It's called CHODE because two words crashed into each other. Yes, I know. Yes, on purpose."
