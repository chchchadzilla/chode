"""The launch menu (arrow keys where possible, numbers everywhere)."""
import sys
import time

from . import VERSION
from .config import PROVIDERS, resolve_model
from .paths import CONFIG_FILE, IS_WIN
from .ui import FONT_H, accent, accent_bold, bold, dim, greeting, quip, static_banner, yellow

MENU_ITEMS = [
    ("🚀", "Start coding",        "jump into the chat",                                   "start"),
    ("⏪", "Resume last session", "pick up where you left off",                           "resume"),
    ("🖥", "Open the Deck (GUI)",  "the same brain, in your browser",                      "gui"),
    ("🧙", "Setup",               "provider · plan · key · model · vibes",                "setup"),
    ("🥤", "Import (the gulp)",   "pull skills/rules/MCP from Claude Code, Cursor, Codex, VS Code…", "import"),
    ("💳", "Plans",               "ride the subscription you already pay for",            "plans"),
    ("📐", "ORDER",               "audit & scaffold this repo",                           "order"),
    ("🩺", "Doctor",              "audit your environment & config",                      "doctor"),
    ("❤️", "Health check",        "live ping: endpoint · model · MCP",                    "health"),
    ("🎓", "Skills",              "see what CHODE knows",                                 "skills"),
    ("👋", "Quit",                "later, legend",                                        "quit"),
]


def _getch():
    if IS_WIN:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(ch2, "")
        if ch in ("\r", "\n", " "):
            return "enter"
        if ch in ("\x1b", "q", "Q", "\x03"):
            return "quit"
        return ch
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            nxt = sys.stdin.read(1)
            if nxt == "[":
                return {"A": "up", "B": "down"}.get(sys.stdin.read(1), "")
            return "quit"
        if ch in ("\r", "\n", " "):
            return "enter"
        if ch in ("q", "Q", "\x03", "\x04"):
            return "quit"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _dispatch(action, cfg, args):
    from .repl import start_chat
    if action == "start":
        start_chat(cfg, args); return True
    if action == "resume":
        start_chat(cfg, args, cont=True); return True
    if action == "gui":
        from .gui import serve
        serve(cfg); return True
    if action == "setup":
        from .wizard import run_wizard
        run_wizard(cfg)
    elif action == "import":
        from .wizard import run_import
        run_import(cfg)
    elif action == "plans":
        from .wizard import run_plans
        run_plans(cfg)
    elif action == "order":
        from .wizard import run_order_cli
        run_order_cli(cfg, [])
    elif action == "doctor":
        from .doctor import run_doctor
        run_doctor(cfg)
    elif action == "health":
        from .doctor import run_health
        run_health(cfg)
    elif action == "skills":
        from .cli import run_skills_cli
        run_skills_cli(cfg, [])
        print()
    return False


def _menu_numbered(cfg, args):
    first_run = not CONFIG_FILE.exists()
    while True:
        print(bold("  CHODE") + dim(f"  v{VERSION} · {cfg['provider']} · {resolve_model(cfg)} · mode {cfg['mode']}"))
        if first_run:
            print(yellow("  first run detected — start with Setup (4)"))
        print()
        for i, (icon, label, desc, _) in enumerate(MENU_ITEMS, 1):
            print(f"    {bold(f'{i:2d}.')} {icon} {label:<22} {dim(desc)}")
        print()
        try:
            choice = input(f"  {dim('pick ›')} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(dim("\n  bye 👋"))
            return
        if choice == "":
            choice = "1"
        if choice in ("q", "quit", "exit", str(len(MENU_ITEMS))):
            print(dim("  bye 👋"))
            return
        if choice.isdigit() and 1 <= int(choice) <= len(MENU_ITEMS):
            action = MENU_ITEMS[int(choice) - 1][3]
        else:
            action = next((a for _, l, _, a in MENU_ITEMS if l.lower().startswith(choice)), "")
        if not action:
            continue
        if _dispatch(action, cfg, args):
            return
        first_run = not CONFIG_FILE.exists()


def _menu_row(item, selected, width=56):
    icon, label, desc, _ = item
    if selected:
        bar = f" ❯ {icon} {label}"
        pad = " " * max(1, width - len(f" > {label}") - 4)
        return accent_bold(bar) + dim(pad) + accent("◀")
    return dim(f"   {icon} ") + label


def _draw_menu(sel, top_row, cfg, first=False, q=""):
    lines = [""]
    lines.append("  " + accent(greeting(cfg)))
    lines.append("  " + dim("─" * 58))
    for i, item in enumerate(MENU_ITEMS):
        lines.append("  " + _menu_row(item, i == sel))
    lines.append("  " + dim("─" * 58))
    lines.append("  " + dim(MENU_ITEMS[sel][2]))
    lines.append("  " + dim(f"↑↓ move · Enter select · 1-{len(MENU_ITEMS)} jump · q quit") + "   " + dim("« " + q + " »"))
    sys.stdout.write(f"\033[{top_row}H")
    for l in lines:
        if first:
            time.sleep(0.018)
        sys.stdout.write("\033[K" + l + "\n")
        if first:
            sys.stdout.flush()
    sys.stdout.flush()


def _menu_fancy(cfg, args):
    q = quip()
    sys.stdout.write("\033[2J\033[H")
    static_banner()
    top_row = FONT_H + 4
    sel = 0
    sys.stdout.write("\033[?25l")
    try:
        _draw_menu(sel, top_row, cfg, first=True, q=q)
        while True:
            key = _getch()
            moved = False
            if key == "up":
                sel = (sel - 1) % len(MENU_ITEMS); moved = True
            elif key == "down":
                sel = (sel + 1) % len(MENU_ITEMS); moved = True
            elif key and key.isdigit() and 1 <= int(key) <= len(MENU_ITEMS):
                sel = int(key) - 1
                key = "enter"
            if moved:
                _draw_menu(sel, top_row, cfg, q=q)
                continue
            if key == "quit":
                print(dim("\n  later, legend 👋"))
                return
            if key != "enter":
                continue
            action = MENU_ITEMS[sel][3]
            sys.stdout.write("\033[?25h\033[2J\033[H")
            if action == "quit":
                print(dim("  later, legend 👋"))
                return
            if _dispatch(action, cfg, args):
                return
            print(dim("  press any key to return to the menu…"))
            _getch()
            sys.stdout.write("\033[2J\033[H\033[?25l")
            static_banner()
            q = quip()
            _draw_menu(sel, top_row, cfg, q=q)
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def run_menu(cfg, args):
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            return _menu_fancy(cfg, args)
        except Exception:
            sys.stdout.write("\033[?25h")
    return _menu_numbered(cfg, args)
