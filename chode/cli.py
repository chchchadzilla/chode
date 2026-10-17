"""Command-line entry point: `chode [command] [args] [flags]`."""
import argparse
import os
import shutil
import sys
from pathlib import Path

from . import VERSION, TAGLINE
from .config import MODES, PROVIDERS, load_config
from .paths import GLOBAL_SKILLS_DIR, PROJECT_DIRNAME, ensure_home
from .ui import bold, collision_intro, dim, red, set_theme, static_banner, yesno

COMMANDS = ("chat", "menu", "setup", "doctor", "health", "import", "migrate", "plans", "ride", "order", "backup",
            "index", "search", "banner", "ship", "release", "gui", "mcp-serve", "skills", "memory", "ledger",
            "conscience", "about", "version", "fix", "lifeline")

EPILOG = f"""commands:
  chat            talk to CHODE (default when piping or with -p)
  menu            the launcher (default on a terminal)
  setup           guided config: plan or key, model, mode, ORDER options
  import          one-click import of skills/rules/commands/MCP/hooks from every other coding agent
  plans           detect Claude/Codex/Gemini CLIs and ride your subscription
  ride <cli>      open claude|codex|gemini with CHODE's tools + memory mounted
  order [fix]     audit this repo's ORDER; `fix` scaffolds + has the model write README/ABOUT/tests
  backup [list|restore N]   snapshot the project to ~/.chode/backups
  index · search <q>        build / query the local codebase index
  banner [name]   generate banner.svg/.png + icon.svg into ./assets
  ship [msg]      secret-scan, commit (model-written message), push
  release vX.Y.Z  bump, changelog, tag, push, GitHub release
  gui             the Deck — same brain, in your browser
  mcp-serve       run CHODE as an MCP server (what the Plan Bridge uses)
  fix             the connection doctor: finds a model that answers and fixes the config for you
  lifeline        show what CHODE can fall back to on this machine (keys · local servers · free)
  skills [add|remove] · memory [export|clear] · ledger · conscience · doctor · health

{TAGLINE}."""


def run_skills_cli(cfg, argv):
    from .skills import discover_skills, install_skill
    if argv and argv[0] == "add":
        if len(argv) < 2:
            print(red("usage: chode skills add <dir|git-url> [name]"))
            return
        print(install_skill(argv[1], argv[2] if len(argv) > 2 else ""))
        return
    if argv and argv[0] == "remove":
        if len(argv) < 2:
            print(red("usage: chode skills remove <name>"))
            return
        s = discover_skills().get(argv[1])
        if not s:
            print(red(f"no skill named '{argv[1]}'"))
        elif GLOBAL_SKILLS_DIR.resolve() not in s.path.resolve().parents:
            print(red(f"'{argv[1]}' is a project skill — remove {s.path} yourself"))
        elif yesno(f"delete {s.path}?", False):
            shutil.rmtree(s.path)
            print(dim("removed"))
        return
    skills = discover_skills()
    if not skills:
        print(dim(f"  no skills installed. try: chode import · chode skills add <dir|git-url>\n"
                  f"  skill folders live in {GLOBAL_SKILLS_DIR} and ./{PROJECT_DIRNAME}/skills/"))
    for s in skills.values():
        print(f"  {bold(s.name)}  {dim(s.description[:90])}\n    {dim(str(s.path))}")


def run_memory_cli(cfg, argv):
    from .memory import MemoryStore
    import time
    store = MemoryStore(cfg)
    if argv and argv[0] == "export":
        out = Path(argv[1]) if len(argv) > 1 else Path("CHODE-memory.md")
        out.write_text(store.export_markdown(), encoding="utf-8")
        print(dim(f"exported → {out}"))
        return
    if argv and argv[0] == "clear":
        scope = argv[1] if len(argv) > 1 else "project"
        if yesno(f"clear {scope} memory?", False):
            store.clear(scope)
            print(dim("cleared"))
        return
    if argv and argv[0] == "add":
        e = store.add(" ".join(argv[1:]), source="user")
        print(dim(f"remembered {e['id']}") if e else red("nothing to add"))
        return
    entries = store.all()
    if not entries:
        print(dim("no memories yet"))
    for e in sorted(entries, key=lambda x: x.get("ts", 0))[-60:]:
        print(f"  {e['id']} {time.strftime('%m-%d', time.localtime(e.get('ts', 0)))} [{e.get('kind')}/{e.get('scope')}] {e['text'][:110]}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chode", description=f"CHODE v{VERSION} — {TAGLINE}",
                                 epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", help="what to run (default: menu on a TTY, chat otherwise)")
    ap.add_argument("cmd_args", nargs="*", help="arguments for the command")
    ap.add_argument("-p", "--print", dest="oneshot", metavar="PROMPT", help="run one prompt non-interactively and exit")
    ap.add_argument("-c", "--continue", dest="cont", action="store_true", help="continue the most recent session in this directory")
    ap.add_argument("--provider", choices=list(PROVIDERS))
    ap.add_argument("--model")
    ap.add_argument("--mode", choices=list(MODES), help="permission mode for this run")
    ap.add_argument("--yolo", action="store_true", help="shortcut for --mode yolo")
    ap.add_argument("--no-mcp", action="store_true", help="don't start MCP servers")
    ap.add_argument("--no-intro", action="store_true", help="skip the intro animation")
    ap.add_argument("--cwd", help="run in this directory")
    ap.add_argument("--port", type=int, help="gui port")
    ap.add_argument("--version", action="version", version=f"CHODE {VERSION}")
    args = ap.parse_args(argv)

    if args.cwd:
        os.chdir(args.cwd)
    ensure_home()
    from .skills import ensure_builtin_skills
    ensure_builtin_skills()
    cfg = load_config()
    set_theme(cfg)
    if args.provider:
        cfg["provider"] = args.provider
        cfg["model"] = ""
    if args.model:
        cfg["model"] = args.model
    if args.yolo:
        cfg["mode"] = "yolo"
    elif args.mode:
        cfg["mode"] = args.mode
    if args.no_intro:
        cfg["intro"] = False

    cmd = args.command
    if cmd and cmd not in COMMANDS:
        # `chode "fix the tests"` → treat as a one-shot prompt
        args.oneshot = " ".join([cmd] + args.cmd_args)
        cmd = "chat"
    if not cmd:
        if args.oneshot or args.cont:
            cmd = "chat"
        elif sys.stdout.isatty() and sys.stdin.isatty() and not cfg.get("skip_menu"):
            cmd = "menu"
        else:
            cmd = "chat"

    if cmd == "mcp-serve":
        from .mcp_server import serve
        mode = cfg["mode"]
        if "--mode" in args.cmd_args:
            i = args.cmd_args.index("--mode")
            if i + 1 < len(args.cmd_args):
                mode = args.cmd_args[i + 1]
        serve(mode=mode)
        return

    if cmd == "chat":
        from .repl import start_chat
        oneshot = args.oneshot
        if oneshot and not sys.stdin.isatty():
            piped = sys.stdin.read().strip()
            if piped:
                oneshot += "\n\n[piped input]\n" + piped[:30000]
        if not oneshot:
            collision_intro(cfg)
        start_chat(cfg, args, cont=args.cont, oneshot=oneshot)
    elif cmd == "menu":
        from .menu import run_menu
        collision_intro(cfg)
        run_menu(cfg, args)
    elif cmd == "setup":
        from .wizard import run_wizard
        from .repl import start_chat
        static_banner()
        run_wizard(cfg)
        if sys.stdin.isatty() and yesno("start coding now?", True):
            start_chat(cfg, args)
    elif cmd == "doctor":
        from .doctor import run_doctor
        run_doctor(cfg)
    elif cmd == "health":
        from .doctor import run_health
        sys.exit(0 if run_health(cfg) else 1)
    elif cmd in ("import", "migrate"):
        from .wizard import run_import
        run_import(cfg, auto_yes="--yes" in args.cmd_args or "-y" in args.cmd_args)
    elif cmd == "plans":
        from .wizard import run_plans
        run_plans(cfg)
    elif cmd == "ride":
        from .plans import ride
        if not args.cmd_args:
            print(red("usage: chode ride claude|codex|gemini [extra args for that cli]"))
            return
        out = ride(args.cmd_args[0], cfg, args.cmd_args[1:])
        if out:
            print(red(str(out)))
    elif cmd == "order":
        from .wizard import run_order_cli
        run_order_cli(cfg, args.cmd_args)
    elif cmd == "backup":
        from .wizard import run_backup_cli
        run_backup_cli(cfg, args.cmd_args)
    elif cmd == "index":
        from .rag import Index
        from .ui import Spinner
        from .llm import LLMClient
        idx = Index(cfg=cfg)
        idx.load()
        embed = LLMClient(cfg).embed if cfg.get("rag", {}).get("embeddings") else None
        with Spinner("indexing"):
            stats = idx.build(embed=embed, full="--full" in args.cmd_args)
        print(f"  indexed {stats['files']} files · {stats['chunks']} chunks · {stats['secs']:.1f}s" + (" · embedded" if stats.get("embedded") else ""))
    elif cmd == "search":
        from .rag import Index, format_results
        idx = Index(cfg=cfg)
        if not idx.load() or not idx.chunks:
            idx.build()
        print(format_results(idx.search(" ".join(args.cmd_args), k=6)))
    elif cmd == "banner":
        from .banner import make_banner
        from .order import detect_project
        proj = detect_project()
        title = " ".join(args.cmd_args) or proj["name"]
        res = make_banner(cfg, title, proj["description"] or TAGLINE, Path("assets"), proj["description"])
        for k, v in res.items():
            print(f"  {k}: {v}")
    elif cmd == "ship":
        from .publish import ship
        from .llm import LLMClient
        from .agent import oneshot_ask
        from . import state
        from .ui import TerminalUI
        state.set_app(state.App(cfg, ui=TerminalUI()))
        client = LLMClient(cfg)
        msg = " ".join(a for a in args.cmd_args if not a.startswith("--")) or None
        print(ship(cfg=cfg, message=msg, push="--no-push" not in args.cmd_args, force="--force" in args.cmd_args,
                   ask_model=lambda p: oneshot_ask(client, p), confirm=lambda q, default=True: yesno(q, default)))
    elif cmd == "release":
        from .publish import release
        from .llm import LLMClient
        from .agent import oneshot_ask
        if not args.cmd_args:
            print(red("usage: chode release v1.2.3"))
            return
        client = LLMClient(cfg)
        print(release(cfg=cfg, version=args.cmd_args[0], ask_model=lambda p: oneshot_ask(client, p, max_tokens=1500),
                      draft="--draft" in args.cmd_args))
    elif cmd == "gui":
        from .gui import serve
        if args.port:
            cfg.setdefault("gui", {})["port"] = args.port
        serve(cfg)
    elif cmd == "skills":
        run_skills_cli(cfg, args.cmd_args)
    elif cmd == "memory":
        run_memory_cli(cfg, args.cmd_args)
    elif cmd == "ledger":
        from . import conscience
        n = int(args.cmd_args[0]) if args.cmd_args and args.cmd_args[0].isdigit() else 30
        for e in conscience.tail(n):
            print("  " + conscience.format_event(e))
    elif cmd == "conscience":
        from . import conscience
        print(conscience.load())
    elif cmd == "about":
        from .repl import start_chat
        from .commands import about_prompt_only
        from .order import detect_project
        start_chat(cfg, args, oneshot=about_prompt_only(detect_project()))
    elif cmd == "version":
        print(f"CHODE {VERSION} — {TAGLINE}")
    elif cmd == "fix":
        from . import lifeline, state
        from .ui import TerminalUI
        ui = TerminalUI()
        state.set_app(state.App(cfg, ui=ui))
        print(bold("\n  🩹 CHODE connection doctor\n"))
        for p, ok_, note in lifeline.status(cfg):
            print(f"  {'✓' if ok_ else '·'} {p:<12} {dim(note)}")
        print()
        out = lifeline.run_fixer(cfg, ui=ui)
        print("\n  " + (out or "").strip().replace("\n", "\n  ") + "\n")
    elif cmd == "lifeline":
        from . import lifeline
        print(bold("\n  🪢 lifeline — what can answer on this machine\n"))
        for p, ok_, note in lifeline.status(cfg):
            print(f"  {'✓' if ok_ else '·'} {p:<12} {dim(note)}")
        lad = lifeline.ladder(cfg)
        print("\n  fallback order: " + (" → ".join(f"{p}{('/' + m) if m else ''}" for p, m in lad) if lad else "(fallbacks off)") + "\n")


if __name__ == "__main__":
    main()
