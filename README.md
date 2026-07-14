# chad code — run commands, edit files and build things with "chode" CLI 💪 (v0.4.0)

**your own ai coding assistant that runs in a terminal — works with basically every ai provider on earth, or a model running 100% on your own computer.**

it reads your code, edits files, runs commands, fixes bugs, and asks permission before it touches anything. think "claude code," except *you* pick the brain: anthropic, openai, google, xai, deepseek, a free openrouter model, or a local model that never sends a byte off your machine.

and yes — when you launch, the commands and helper tools use **chode** to control **chad code**. *thicc like a tuna can.*

---

## 🟢 setup in 5 minutes (never used a terminal? start here)

### step 1 — get python

chad code needs python 3.9 or newer.

- **windows:** install from [python.org/downloads](https://python.org/downloads). **important:** on the first installer screen, check the box that says **"add python.exe to path"**. then click install.
- **macos:** open the **terminal** app and type `python3 --version`. if it shows a version number, you're done. if not, install from python.org.
- **linux:** you almost certainly have it. `python3 --version` to confirm.

### step 2 — open a terminal

- **windows:** press the windows key + r, type `cmd`, press enter. (windows terminal / command prompt (cmd.exe) or powershell all work. windows terminal looks nicer.)
- **macos:** press cmd+space, type `terminal`, press enter.
- **linux:** you know where it is.

### step 3 — install the one dependency

copy-paste this into the terminal and press enter:

```
pip install requests
```

(if that says "pip is not recognized" on windows, try `py -m pip install requests`.)

### step 4 — put the files somewhere

make a folder (e.g. `chad-code`), and put these files in it:
`chode.py` · `chode_splash.py` · `chode-start` (mac/linux) · `chode-start.bat` (windows) · `readme.md`

### step 5 — run it

in the terminal, go to that folder and start chode -- to change folders (or 'directories'), you type "cd", a space, then the location you want to go. if you're switching drive letters, you put a '/d' before the location. wherever you put those files is your 'path/to/chad-code':

```
cd path/to/chode-code        (windows example:  cd c:\users\you\chode-code <-- then press enter if you saved those files to "d:\chode-code" you would write 'cd /d d:\chode-code')
python3 chode.py             (windows:          python chode.py   or   py chode.py)
```

you'll see the intro animation, then a **menu**. use **↑ ↓ arrow keys** and **enter**. pick **setup wizard** — it walks you through everything: it asks your name, your favorite color, which ai provider you want, your api key (typed invisibly, that's normal), which model, and how cautious chode should be. it even tests the connection at the end.

**that's it. pick "start coding" and tell it what you want.**

---

## 🔑 "which provider should i pick and where do i get a key?"

| you want | pick | get a key at | free? |
|---|---|---|---|
| the good stuff | `anthropic` | console.anthropic.com | lmao no u gotta pay |
| chatgpt's models | `openai` | platform.openai.com | slightly less lmao but u still gotta pay |
| grok | `xai` | console.x.ai | not really lmao but it costs money |
| google gemini | `gemini` | aistudio.google.com | free tier - not much! but a little! |
| **free cloud models** | `openrouter` | openrouter.ai/keys | **yes** — pick a `:free` model - look for the longest context window (look through the models page at openrouter.ai) |
| very cheap + very good | `deepseek` | platform.deepseek.com | staggeringly cheap for the quality |
| very fast | `groq` which is not elon's grok it's different it's with a q or `cerebras` | console.groq.com / cloud.cerebras.ai | free tiers sometimes |
| kimi k2 | `moonshot` | platform.moonshot.ai | paid but almost free like deepseek and really good |
| mistral / together / perplexity / azure | `mistral` `together` `perplexity` `azure` | their sites | varies and is a lil complicated especially azure |
| **no internet, no key, fully private** | `ollama` | install from ollama.com, then `ollama pull qwen3-coder` | **yes 100%** but you can't have a potato computer |
| lm studio | `lmstudio` | lmstudio.ai (start its local server) | yes but you can't use a potato to launch it |
| any other local server | `local` | llama.cpp, vllm, litellm, jan, kobold… | yes but tbh if ur using llama.cpp ur not even reading this lmao |

the wizard stores your key for you, or you can use environment variables (`anthropic_api_key`, `openai_api_key`, `gemini_api_key`, `openrouter_api_key`, etc.) — env vars always win.

**cheapest possible start:** get a free openrouter key → wizard → provider `openrouter` → model `qwen/qwen3-coder:free`. openrouter free models become free once you've spent $10 with them. it's so incredibly worth it i can't stress it enough. just spend the $10. the amount of free calls you get in return makes this stupid to not do.

---

## 🎬 the splash screen (optional, extremely important)

want an .mp4 to play when you launch, then fade into the cli? do this:

1. save your video as `splash.mp4` inside `~/.chode/` (windows: `c:\users\*insert your windows username here*\.chode\`)-- u can also just set `chad_splash` to any path.
2. install **ffmpeg** (this is what renders the video *inside your terminal* as art):
   - windows: `winget install ffmpeg` — or grab it from ffmpeg.org
   - macos: `brew install ffmpeg`
   - linux: `sudo apt install ffmpeg`
3. launch with the start file instead of chode.py:
   - mac/linux: `./chode-start`
   - windows: double-click `chode-start.bat` (or run it in the terminal)

video plays in the terminal at ~14fps in full color with audio, fades to black, and the chode collision takes over. skip it anytime with `chode_no_splash=1`.

*(no ffmpeg? lmao okay, weirdo... but that's fine ig bc it just falls back to mpv's terminal mode, then to a plain ffplay window, then skips silently. use windows terminal bc the old conhost console is rough on colors.)*

---

## 🧭 the menu & commands

plain `chode.py` opens the animated menu (arrow keys, enter, `q`, or number keys to jump). everything's also a direct command:

```
python3 chode.py chat        straight into chatting (skip the menu)
python3 chode.py setup       the wizard again, anytime
python3 chode.py doctor      checks everything and tells you how to fix it
python3 chode.py health      quick live test: is the ai reachable? exit code 0/1
python3 chode.py migrate     steal your skills back from other agents (see below)
python3 chode.py skills      list / add / remove skills
python3 chode.py -p "..."    one-shot: ask, get answer, exit
python3 chode.py -c          continue your last conversation in this folder
```

**something broke on your chode? or worse-- in your chode? easy bro just run `doctor` and it'll check ur chode. 20+ chode-checks, actually, and tells you the exact fix for each.**

### while chode-ing

| type | it does |
|---|---|
| `/help` | everything below that u can do in-app |
| `/mode` | how careful ur chode is: `plan` (look, but don't touch) / `ask` (do it but run it by me) / `edits` (i'll just handle it bro it's cool / `yolo` (not askin u shit) |
| `/model`, `/models`, `/provider` | switch brains mid-conversation, history carries over |
| `/undo` | revert chode's last file change (keep pressing to go further back-- it goes for a while bro like a while a while) |
| `/theme` | cycle your accent color which doesn't do anything but like i dunno i thought it was cool |
| `/export` | save the whole conversation as a markdown file (always wanted it, now i do. score one for the chodester) |
| `/skills`, `/mcp`, `/resume`, `/compact`, `/cost`, `/init`, `/memory`, `/banner` | the rest of the commands. just like openclaw w/clawhub `openclaw skills install mimic-my-writing`, just replace `openclaw` with `/` see? isn't that easier? i'm sayin, man |
| `@somefile.py` | attach a file to your message because sometimes you wanna show your shit off to ur clanker |
| `!ls` | run a command yourself, output becomes context |
| `#never use tabs` | permanently remember a note (goes in `CHODE.md`) |

---

## 🎓 skills (teach ur chode things)

a skill is just a folder with a `skill.md` file — instructions chad code loads *only when relevant*, so 50 skills cost almost nothing. they live in `~/.chode/skills/` (global) or `./.chode/skills/` (per-project).

```markdown
---
name: deploy-to-prod
description: how we deploy this app to production safely
---
# deploy procedure
1. run the tests: `npm test`
2. ...
```

- `/skills` lists them, `chode skills add <folder-or-git-url>` installs one.
- **`chode migrate`** scans your machine for skills and mcp configs from **openclaw** (incl. legacy clawdbot/moltbot), **hermes**, **claude code**, **cursor**, and **windsurf**, and imports whatever you pick. optional deep-scan finds strays anywhere in your home folder.
- **skill-porter** (built-in, installs itself on first run): for stuff `migrate` *can't* copy directly — a cursor rules file, an agents.md, a gpt's instructions, a plugin in some other format — just tell chode: *"port ~/.openclaw/plugins/whatever into a chode skill"*. it reads the source, translates other agents' tool names to chode's, writes proper frontmatter, copies helper scripts, and verifies the result loads.

---

## 🔌 mcp servers (give ur chode magic superpowers so u can have a super secret magical ninja chode)

chode speaks hella fluent model context protocol — the same plugin system claude code uses. add servers to `~/.chode/config.json` (or per-project `.chode/mcp.json`):

```json
"mcp_servers": {
  "fs": { "transport": "stdio", "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "."] }
}
```

`/mcp` shows status. their tools go through the same permission prompts as everything else. on windows, `npx`/`node` `.cmd` shims are resolved automatically. (most mcp servers need node.js — `doctor` checks your chode for it.)

---

## 🛡 safety (the stuff protecting you from a confused robot)

- **permission prompts with diff previews** — before any file change you see the exact colored diff; before any command you see the command. `y`/`n`/`a`(lways)/`p`(allowlist this command prefix forever).
- **dangerous-command guard** — `sudo`, `rm -rf /`, `format c:`, `del /s`, `remove-item -recurse` near system folders, registry deletes, `curl | sh`, `iwr | iex`, defender tampering, force-pushes… all require you to literally type `yes` — **even in yolo mode**. unix *and* windows patterns. your best safety is your trigger finger you feel me
- **secret redaction** — before tool output is sent to any ai provider, it's scrubbed by chode for things shaped like api keys (openai/anthropic/github/aws/slack/google keys, jwts, private-key blocks). `cat .env` chode will not donate your keys to a free cloud model. basically chode tries its hardest to make sure you're not a chode.
- **write sandbox** — writing outside your project folder always triggers a warning.
- **`/undo`** — chode snapshots every file before touching it. so if u f up some s, ur not really f'd in the b at all.
- **plan mode** — `/mode plan` makes chode physically unable to change anything.
- **prompt-injection hardening** — web pages and file contents are marked as untrusted data; chode is instructed to ignore instructions hiding inside them and snitch to you.

paranoid setup for untrusted code: `python3 chode.py --mode plan --provider ollama`. nothing leaves the machine, nothing gets written.

---

## 🪟 windows notes

- colors/animations need ansi support — chad enables it automatically; **windows terminal** recommended over the legacy console.
- chad's shell tool uses **powershell** by default (falls back to cmd). change with `/config shell cmd` if you prefer.
- use `python` or `py` instead of `python3` in all the commands above.
- the launcher is `chode-start.bat`; everything else is identical.

## ⚙️ config reference (`~/.chode/config.json`)

```json
{
  "provider": "openrouter", "model": "qwen/qwen3-coder:free",
  "mode": "ask", "name": "dave", "theme": "cyan",
  "max_tokens": 8192, "temperature": 0.2,
  "bash_allow": ["git status", "git diff", "git log", "ls", "pwd", "cat"],
  "redact_secrets": true, "allow_outside_cwd": false,
  "auto_compact_tokens": 120000, "shell": "auto",
  "intro": true, "skip_menu": false,
  "base_urls": {}, "api_keys": {}, "mcp_servers": {},
  "azure_api_version": "2024-06-01"
}
```

## 🆘 troubleshooting

| symptom | fix |
|---|---|
| `python3 is not recognized` (windows) | use `python` or `py`; reinstall python with "add to path" checked |
| `no module named requests` | `pip install requests` (windows: `py -m pip install requests`) |
| weird characters like `[35m` everywhere | your terminal doesn't do ansi — use windows terminal, or set `no_color=1` |
| "could not connect to http://localhost:11434" | your local model server isn't running (`ollama serve`) |
| http 401 | bad/missing api key — rerun `chode setup` |
| model never uses tools (local model) | that model can't do tool-calling; try qwen3-coder, qwen2.5-coder 14b+, or llama 3.3 |
| animation looks broken | terminal under 76 columns falls back to static — make it wider |
| anything else | `python3 chode.py doctor` — seriously, it knows |

## 🧪 test without spending a cent

`mock_server.py` is a fake ai (port 8080) and `mock_mcp.py` a fake mcp server:

```
python3 mock_server.py &
python3 chode.py --provider local --model test --yolo -p "make hello file"
```

---

*chad code: one python file, one dependency, sixteen providers, zero excuses. certified girthy.*
