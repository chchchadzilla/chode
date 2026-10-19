"""Slash commands (the REPL's control surface) and custom .md commands."""
import json
import time
from pathlib import Path

from . import VERSION, conscience, state
from .agent import build_system_prompt, compact_history, oneshot_ask
from .config import MODE_ICONS, MODES, PROVIDERS, save_config, set_config_path
from .llm import LLMError
from .memory import instructions_block
from .paths import GLOBAL_COMMANDS_DIR, GLOBAL_SKILLS_DIR, MEMORY_FILENAME, PROJECT_DIRNAME, CONFIG_FILE
from .session import SessionStore, session_summary
from .skills import discover_agents, discover_skills, install_skill, parse_frontmatter, strip_frontmatter
from .ui import THEMES, Spinner, accent, accent_bold, bold, cyan, dim, green, magenta, red, set_theme, yellow, hr


def discover_commands(cwd=None):
    cmds = {}
    cwd = Path(cwd or Path.cwd())
    for base in (GLOBAL_COMMANDS_DIR, cwd / PROJECT_DIRNAME / "commands", cwd / ".claude" / "commands"):
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.md")):
            text = f.read_text(errors="replace", encoding="utf-8")
            meta = parse_frontmatter(text)
            name = f.stem if f.parent == base else f"{f.parent.name}:{f.stem}"
            cmds[name] = {"description": meta.get("description", ""), "template": strip_frontmatter(text).strip(), "path": f}
    return cmds


HELP = """
{title}
  {h}Talk{r}        just type. @file attaches a file · !cmd runs a shell command · #note saves a note to {mem}
  {h}Modes{r}       /mode plan|ask|edits|yolo     /model [name]   /models   /provider [name] [model]   /sampling [edit]
  {h}Memory{r}      /remember <text> [--global]   /memories   /forget <id>   /memory   /init   /conscience   /ledger
  {h}ORDER{r}       /order   /about   /tidy   /backup [list|restore N]   /status   /diff   /git
  {h}Ship{r}        /ship [message] [--no-push]   /release vX.Y.Z   /banner [name]
  {h}Brain{r}       /index   /search <query>   /skills [add <dir|url>]   /agents   /mcp [reload]   /hooks   /plans
  {h}Session{r}     /undo   /resume   /compact   /clear   /export [file]   /cost   /config [key value]   /permissions
  {h}Apps{r}        /gui   /ride claude|codex|gemini   /import [path…] [--drives]   /doctor   /theme [color]   /intro   /help   /exit
  {h}Lifeline{r}    /fix (repair the model connection)   /lifeline (what CHODE falls back to)   /provider keep
"""


def help_text(custom_cmds):
    base = HELP.format(title=bold(f"CHODE v{VERSION} — commands"), h="\033[1m" if True else "", r="\033[0m", mem=MEMORY_FILENAME)
    if custom_cmds:
        base += f"\n{bold('Custom commands')} (from ~/.chode/commands, .chode/commands, .claude/commands)\n"
        for name, cmd in list(custom_cmds.items())[:40]:
            base += f"  /{name}  {dim(cmd['description'] or '')}\n"
    return base


def handle_slash(cmd, ctx):
    """ctx: the Repl. Returns (keep_running, message_to_send_or_None)."""
    parts = cmd.split(maxsplit=1)
    name = parts[0][1:].lower()
    rest_raw = parts[1] if len(parts) > 1 else ""
    rest = rest_raw.split()
    cfg = ctx.cfg
    client, history, ui = ctx.client, ctx.history, ctx.ui
    app = state.app()

    def rebuild():
        ctx.system_ref[0] = build_system_prompt(client, cfg)

    if name in ("exit", "quit", "q"):
        return False, None

    if name in ("help", "?"):
        print(help_text(ctx.custom_cmds))

    elif name == "mode":
        if rest and rest[0] in MODES:
            cfg["mode"] = rest[0]
            save_config(cfg)
            rebuild()
        elif rest:
            print(red(f"modes: {', '.join(MODES)}"))
        print(f"mode: {bold(cfg['mode'])} {MODE_ICONS[cfg['mode']]}")

    elif name == "model":
        if rest:
            from . import lifeline
            with Spinner("checking the name against the live model list"):
                new, note, verified = lifeline.verify_model(cfg, rest_raw.strip(), client)
            cfg["model"] = new
            save_config(cfg)
            if note:
                print(yellow(f"  ↳ {note}"))
            elif verified:
                print(green(f"  ✓ {new} is on {client.provider}'s model list"))
        print(f"model: {bold(client.model)}  (provider: {client.provider})")

    elif name == "models":
        try:
            with Spinner("fetching models"):
                models = client.list_models()
            for m in models[:100]:
                print("  " + m)
            if len(models) > 100:
                print(dim(f"  … and {len(models)-100} more"))
        except LLMError as e:
            print(red(str(e)))

    elif name == "provider":
        if rest and rest[0] == "keep":
            cfg.pop("_fallback_from", None)
            cfg.pop("_fallback_model", None)
            client.switched_from = None
            save_config(cfg)
            print(green(f"saved: {client.provider} / {client.model or '(default)'} is now your default"))
        elif rest:
            p = rest[0].lower()
            if p not in PROVIDERS:
                print(red(f"unknown provider. options: {', '.join(PROVIDERS)}"))
            else:
                cfg["provider"] = p
                cfg["model"] = ""
                cfg.pop("_fallback_from", None)
                cfg.pop("_fallback_model", None)
                client.switched_from = None
                client._plan = None
                if len(rest) > 1:
                    from . import lifeline
                    with Spinner("checking the model name"):
                        new, note, verified = lifeline.verify_model(cfg, " ".join(rest[1:]), client)
                    cfg["model"] = new
                    if note:
                        print(yellow(f"  ↳ {note}"))
                save_config(cfg)
        print(f"provider: {bold(client.provider)}  model: {bold(client.model or '(default)')}  url: {dim(client.base_url or '(cli)')}"
              + (yellow("  [session fallback — /provider keep to save]") if cfg.get("_fallback_from") else ""))

    elif name in ("sampling", "temperature", "tune"):
        from . import sampling
        out = sampling.handle(cfg, client, rest)
        if out:
            print(out)

    elif name in ("fix", "lifeline", "fallbacks"):
        from . import lifeline
        if name == "fix":
            print(dim("  🩹 running the connection doctor…"))
            out = lifeline.run_fixer(cfg, ui=ui)
            if out:
                print("  " + out.strip().replace("\n", "\n  "))
            client._plan = None
            rebuild()
        else:
            print(bold("  🪢 lifeline ladder") + dim("  (what CHODE will try, in order, if the current provider fails)"))
            for p, ok_, note in lifeline.status(cfg):
                print(f"  {green('✓') if ok_ else dim('·')} {p:<12} {dim(note)}")
            lad = lifeline.ladder(cfg)
            print("  order now: " + (" → ".join(f"{p}{('/' + m) if m else ''}" for p, m in lad) if lad else dim("(fallbacks off)")))
            print(dim("  /config fallbacks '[\"groq\",\"ollama\",\"pollinations\"]' to pin an order · /config fallbacks false to disable"))

    elif name == "skills":
        if rest and rest[0] == "add":
            if len(rest) < 2:
                print(red("usage: /skills add <dir|git-url> [name]"))
            else:
                print(install_skill(rest[1], rest[2] if len(rest) > 2 else ""))
                app.skills = discover_skills()
                rebuild()
        else:
            app.skills = discover_skills()
            if not app.skills:
                print(dim(f"no skills installed. Put folders with a SKILL.md in {GLOBAL_SKILLS_DIR} or ./{PROJECT_DIRNAME}/skills/, "
                          f"or use /skills add <dir|git-url>, or /import"))
            for s in app.skills.values():
                print(f"  {bold(s.name)}  {dim(s.description[:90])}\n    {dim(str(s.path))}")

    elif name == "agents":
        agents = discover_agents()
        if not agents:
            print(dim("no sub-agent personas. Drop markdown files in ~/.chode/agents/<name>.md (frontmatter: name, description) or /import them from Claude Code."))
        for n, ag in agents.items():
            print(f"  {bold(n)}  {dim(ag['description'][:90])}")

    elif name == "mcp":
        if rest and rest[0] == "reload":
            from .config import load_config
            from .mcp import McpManager
            if app.mcp:
                app.mcp.stop_all()
            cfg.update({k: v for k, v in load_config().items() if k == "mcp_servers"})
            app.mcp = McpManager(cfg)
            app.mcp.start_all()
        if not app.mcp or not app.mcp.servers:
            print(dim('no MCP servers configured. /import pulls them from Claude Code/Cursor/VS Code/Codex, or add to ~/.chode/config.json:\n'
                      '  "mcp_servers": {"fs": {"transport": "stdio", "command": "npx",\n'
                      '                   "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}}'))
        else:
            for s in app.mcp.servers.values():
                if s.error:
                    print(f"  {red('✗')} {bold(s.name)}  {dim(s.error)}")
                else:
                    print(f"  {green('✓')} {bold(s.name)}  {dim(f'{len(s.tools)} tools: ' + ', '.join(t['name'] for t in s.tools[:8]))}")

    elif name == "hooks":
        from .hooks import load_hooks
        hooks = load_hooks(cfg)
        total = sum(len(v) for v in hooks.values())
        if not total:
            print(dim("no hooks. Add to config: \"hooks\": {\"pre_tool\": [{\"match\": \"bash\", \"command\": \"...\"}]} or /import Claude Code hooks."))
        for ev, lst in hooks.items():
            for h in lst:
                print(f"  {bold(ev)}  {dim(h.get('match') or '*')}  {h['command'][:80]}")

    elif name == "undo":
        msg = app.checkpoints.undo()
        if msg:
            conscience.log("undo", detail=msg[:200])
        print(dim(msg) if msg else dim("nothing to undo"))

    elif name == "resume":
        sessions = SessionStore.list_sessions()
        if not sessions:
            print(dim("no saved sessions for this directory"))
        else:
            for i, s in enumerate(sessions[:10], 1):
                print(f"  {i}. {session_summary(s)}")
            try:
                choice = input(dim("  resume which? (number, empty to cancel) › ")).strip()
                if choice.isdigit() and 1 <= int(choice) <= len(sessions[:10]):
                    history.clear()
                    history.extend(SessionStore.load(sessions[int(choice) - 1]))
                    print(green(f"resumed session with {len(history)} messages"))
            except (EOFError, KeyboardInterrupt):
                pass

    elif name == "config":
        if len(rest) >= 2:
            value = rest_raw.split(maxsplit=1)[1]
            if rest[0] == "model":
                from .config import normalize_model
                value = normalize_model(cfg.get("provider", "anthropic"), value)
            set_config_path(cfg, rest[0], value)
            save_config(cfg)
            print(green("saved"))
        from .config import DEFAULT_CONFIG
        shown = {k: v for k, v in cfg.items() if k in DEFAULT_CONFIG}
        shown["api_keys"] = {k: "•••" for k in cfg.get("api_keys", {})}
        print(json.dumps(shown, indent=2))
        print(dim(f"config file: {CONFIG_FILE}"))

    elif name == "permissions":
        print(f"  mode: {bold(cfg['mode'])}   always (this session): {', '.join(sorted(ctx.perms.always)) or '-'}")
        print(f"  bash_allow: {dim(', '.join(cfg.get('bash_allow', [])) or '-')}")
        print(f"  bash_deny:  {dim(', '.join(cfg.get('bash_deny', [])) or '-')}")
        print(dim("  edit: /config bash_allow '[\"npm test\",\"pytest\"]'  or project .chode/permissions.json {\"allow\":[],\"deny\":[]}"))

    elif name == "cost":
        print(client.cost_line() + f"   calls: {client.calls}   context: {client.context_pct()}%")

    elif name == "clear":
        history.clear()
        print(dim("history cleared"))

    elif name == "compact":
        if history:
            compact_history(client, ctx.system_ref[0], history, ui)
        else:
            print(dim("nothing to compact"))

    elif name == "init":
        return True, (f"Explore this repository (list_dir, read key files like README/manifests, glob for source) and write a "
                      f"concise {MEMORY_FILENAME} at the repo root describing: what the project is, how to build/run/test it, "
                      f"code layout, and conventions. Under ~60 lines. If AGENTS.md or CLAUDE.md already exists, don't duplicate "
                      f"them — reference them and add only what's missing.")

    elif name == "memory":
        mem = instructions_block()
        print(mem if mem else dim(f"no {MEMORY_FILENAME} / AGENTS.md / CLAUDE.md found (cwd, ancestors, or ~/.chode/)"))

    elif name == "remember":
        if not rest_raw.strip():
            print(red("usage: /remember <one sentence> [--global] [--kind fact|preference|decision|lesson|todo]"))
        else:
            text = rest_raw
            scope = "global" if "--global" in text else "project"
            kind = "fact"
            for k in ("fact", "preference", "decision", "lesson", "todo"):
                if f"--kind {k}" in text or f"--{k}" in text:
                    kind = k
                    text = text.replace(f"--kind {k}", "").replace(f"--{k}", "")
            text = text.replace("--global", "").strip()
            e = app.memory_store().add(text, kind=kind, scope=scope, source="user")
            print(green(f"🧠 remembered [{kind}/{scope}] {e['text']}  (id {e['id']})") if e else red("nothing to remember"))

    elif name == "memories":
        store = app.memory_store()
        entries = store.all()
        if not entries:
            print(dim("no memories yet. /remember <text>, or just work — CHODE reflects at the end of each session."))
        for e in sorted(entries, key=lambda x: x.get("ts", 0))[-40:]:
            ts = time.strftime("%m-%d", time.localtime(e.get("ts", 0)))
            print(f"  {dim(e['id'])} {dim(ts)} {accent(e.get('kind','fact'))}{dim('/g') if e.get('scope')=='global' else ''}  {e['text'][:110]}")
        print(dim(f"  {len(entries)} memories · /forget <id> · files: ~/.chode/memory/"))

    elif name == "forget":
        if not rest:
            print(red("usage: /forget <id>"))
        else:
            print(green("forgotten") if app.memory_store().forget(rest[0]) else red("no such memory"))

    elif name == "conscience":
        print(conscience.load())
        print(dim(f"  edit it any time: {conscience.CONSCIENCE_FILE}"))

    elif name == "ledger":
        n = int(rest[0]) if rest and rest[0].isdigit() else 20
        events = conscience.tail(n)
        if not events:
            print(dim("ledger is empty — nothing risky has happened yet"))
        for e in events:
            print("  " + conscience.format_event(e))

    elif name == "status":
        from .order import status_line
        line, audit = status_line(cfg=cfg)
        print(f"  {bold(line)}")
        for c in audit["checks"]:
            print(f"  {green('✓') if c['ok'] else red('✗')} {c['label']}" + (dim('  ' + c['detail']) if c['detail'] else ''))

    elif name == "order":
        from .order import scaffold, about_prompt, audit
        res = scaffold(apply=True)
        for c in res["created"]:
            print(f"  {green('✓')} {c}")
        if not res["created"]:
            print(dim("  deterministic scaffolding already in place"))
        if res["needs_model"]:
            print(dim(f"  handing to the model: {', '.join(res['needs_model'])}"))
            return True, about_prompt(res["project"], audit())
        print(green("  repo is in ORDER 💪"))

    elif name == "about":
        from .order import detect_project
        return True, about_prompt_only(detect_project())

    elif name == "tidy":
        from .order import tidy_report
        tips = tidy_report()
        if not tips:
            print(green("  nothing stray at the root — tidy 🧹"))
        for f, t in tips:
            print(f"  {yellow('•')} {bold(f)}  {dim(t)}")

    elif name == "backup":
        from .order import backup, list_backups, restore_backup
        if rest and rest[0] == "list":
            for i, b in enumerate(list_backups(), 1):
                print(f"  {i}. {time.strftime('%Y-%m-%d %H:%M', time.localtime(b['ts']))}  {b['files']} files  {b['mb']} MB  {dim(b['note'])}")
            if not list_backups():
                print(dim("  no backups yet"))
        elif rest and rest[0] == "restore":
            bl = list_backups()
            idx = int(rest[1]) - 1 if len(rest) > 1 and rest[1].isdigit() else 0
            if not bl or idx >= len(bl):
                print(red("  no such backup"))
            else:
                dest = Path.cwd().parent / (Path.cwd().name + "-restored-" + time.strftime("%H%M%S"))
                print(green(f"  restored to {restore_backup(bl[idx]['path'], dest)}  (never overwrites your working tree)"))
        else:
            r = backup(cfg=cfg, note=rest_raw or "manual")
            print(green(f"  ✓ {r['files']} files ({r['mb']} MB) → {r['path']}") if r.get("ok") else yellow("  " + r.get("reason", "")))

    elif name == "ship":
        from .publish import ship
        push = "--no-push" not in rest
        force = "--force" in rest
        msg = " ".join(r for r in rest if not r.startswith("--")) or None
        with Spinner("shipping"):
            out = ship(cfg=cfg, message=msg, push=push, force=force,
                       ask_model=lambda p: oneshot_ask(client, p),
                       confirm=lambda q, default=True: _confirm(ui, q, default))
        print("  " + out.replace("\n", "\n  "))

    elif name == "release":
        from .publish import release
        if not rest:
            print(red("usage: /release v1.2.3"))
        else:
            with Spinner("releasing"):
                out = release(cfg=cfg, version=rest[0], ask_model=lambda p: oneshot_ask(client, p, max_tokens=1500),
                              draft="--draft" in rest)
            print("  " + out.replace("\n", "\n  "))

    elif name == "banner":
        from .banner import make_banner
        from .order import detect_project
        proj = detect_project()
        title = rest_raw.strip() or proj["name"]
        with Spinner("rendering banner"):
            res = make_banner(cfg, title, proj["description"] or "made with chode", Path("assets"), proj["description"])
        for k, v in res.items():
            print(f"  {green('✓') if not k.endswith('error') else yellow('⚠')} {k}: {v}")
        print(dim("  add to README: ![banner](assets/banner.png)"))

    elif name == "index":
        idx = app.rag_index()
        embed = client.embed if cfg.get("rag", {}).get("embeddings") else None
        with Spinner("indexing"):
            try:
                stats = idx.build(embed=embed, full="--full" in rest)
                print(green(f"  ✓ {stats['files']} files · {stats['chunks']} chunks · {stats['secs']:.1f}s"
                            + (" · embedded" if stats.get("embedded") else "")))
            except LLMError as e:
                print(red(f"  embeddings failed: {e}"))

    elif name == "search":
        from .rag import format_results
        if not rest_raw.strip():
            print(red("usage: /search <query>"))
        else:
            idx = app.rag_index()
            if not idx.chunks:
                with Spinner("indexing"):
                    idx.build()
            for r in idx.search(rest_raw, k=6):
                print(f"  {accent(r['path'])}:{r['start']}-{r['end']}  {dim(str(r['score']))}")
                print(dim("    " + r["snippet"].splitlines()[0][:110] if r["snippet"] else ""))

    elif name == "import":
        from .wizard import run_import
        drives = True if any(r in ("--drives", "--all-drives", "drives") for r in rest) else None
        paths = [r for r in rest if not r.startswith("--") and r != "drives"]
        run_import(cfg, paths=paths, drives=drives)
        app.skills = discover_skills()
        ctx.custom_cmds = discover_commands()
        rebuild()

    elif name == "plans":
        from .wizard import run_plans
        run_plans(cfg)

    elif name == "ride":
        from .plans import ride
        if not rest:
            print(red("usage: /ride claude|codex|gemini"))
        else:
            out = ride(rest[0], cfg, rest[1:])
            if out:
                print(yellow(out))

    elif name == "gui":
        print(dim("  launching the GUI in your browser — Ctrl-C there to come back"))
        from .gui import serve
        serve(cfg, repl=ctx)

    elif name == "doctor":
        from .doctor import run_doctor
        run_doctor(cfg)

    elif name == "diff":
        from .publish import git
        touched = app.touched_files
        rc, out = git(["diff", "--stat"] + ([] if "--all" in rest else []))
        print(out or dim("  no unstaged changes"))
        if touched:
            print(dim("  touched this session: " + ", ".join(Path(t).name for t in touched[:12])))

    elif name == "git":
        from .publish import git
        rc, out = git(["status", "-sb"])
        print(out)

    elif name == "theme":
        themes = list(THEMES)
        if rest and rest[0] in THEMES:
            cfg["theme"] = rest[0]
        else:
            cfg["theme"] = themes[(themes.index(cfg.get("theme", "magenta")) + 1) % len(themes)]
        set_theme(cfg)
        save_config(cfg)
        print("theme: " + accent_bold("■■■ " + cfg["theme"]))

    elif name in ("intro", "splash"):
        from .ui import collision_intro
        collision_intro(None)

    elif name == "export":
        path = Path(rest[0] if rest else f"chode-transcript-{time.strftime('%Y%m%d-%H%M%S')}.md")
        lines = ["# CHODE transcript", f"_{time.strftime('%Y-%m-%d %H:%M')} · {client.provider}/{client.model}_", ""]
        for m in history:
            if m["role"] == "user":
                lines += ["## You", m["content"], ""]
            elif m["role"] == "assistant" and m.get("content"):
                lines += ["## CHODE", m["content"], ""]
            elif m["role"] == "tool":
                lines += [f"<details><summary>tool: {m.get('name','?')}</summary>", "", "```", m["content"][:3000], "```", "</details>", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        print(dim(f"exported {len(history)} messages → {path}"))

    elif name == "commands":
        for n, c in ctx.custom_cmds.items():
            print(f"  /{n}  {dim(c['description'])}")
        if not ctx.custom_cmds:
            print(dim("  no custom commands. Drop markdown files in ~/.chode/commands/<name>.md ($ARGUMENTS is replaced)."))

    elif name in ctx.custom_cmds:
        return True, ctx.custom_cmds[name]["template"].replace("$ARGUMENTS", rest_raw)

    else:
        print(red(f"unknown command /{name} — try /help"))
    return True, None


def about_prompt_only(proj):
    return (f"Write ABOUT.md for this project ({proj['name']}, {proj['type']}) using the `repo-order` skill's ABOUT.md "
            "spec: origin story, what it does + who it's for, marketing copy (one-liner, 50 words, 150 words), 3 X posts, "
            "1 LinkedIn post, 1 Reddit post (title + body), 1 'Show HN' line, hashtags, and 'explain it to your mom'. "
            "Read the README and main code first so every claim is true. If it already exists, improve it, don't restart.")


def _confirm(ui, question, default=True):
    ans = ui.ask_user(question + (" [Y/n]" if default else " [y/N]"), "")
    if not ans:
        return default
    return ans.lower().startswith("y")


SLASH_NAMES = ["/help", "/mode", "/model", "/models", "/provider", "/skills", "/agents", "/mcp", "/hooks", "/undo", "/resume",
               "/config", "/permissions", "/cost", "/clear", "/compact", "/init", "/memory", "/remember", "/memories",
               "/forget", "/conscience", "/ledger", "/status", "/order", "/about", "/tidy", "/backup", "/ship", "/release",
               "/banner", "/index", "/search", "/import", "/plans", "/ride", "/gui", "/doctor", "/diff", "/git", "/theme",
               "/intro", "/export", "/commands", "/fix", "/lifeline", "/sampling", "/exit"]
