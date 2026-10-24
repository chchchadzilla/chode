"""Terminal UI: colors, theme, spinner, streaming markdown-lite renderer, the
CHAD × CODE collision intro, menus/prompts, and the TerminalUI adapter the agent
loop talks to (the GUI implements the same interface in gui.py)."""
import os
import random
import re
import shutil
import sys
import threading
import time

from . import TAGLINE, VERSION
from .paths import IS_WIN


def enable_vt():
    """Turn on ANSI escape processing in the Windows console and ensure UTF-8 output."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and getattr(stream, "encoding", None) and stream.encoding.lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    if not IS_WIN:
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        for std in (-11, -12):
            h = k32.GetStdHandle(std)
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        os.system("")


enable_vt()


def _supports_color():
    try:
        return sys.stdout.isatty() and os.environ.get("TERM") != "dumb" and not os.environ.get("NO_COLOR")
    except Exception:
        return False


USE_COLOR = _supports_color()


def c(code, text):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else str(text)


def bold(t):      return c("1", t)
def dim(t):       return c("2", t)
def italic(t):    return c("3", t)
def underline(t): return c("4", t)
def red(t):       return c("31", t)
def green(t):     return c("32", t)
def yellow(t):    return c("33", t)
def blue(t):      return c("34", t)
def magenta(t):   return c("35", t)
def cyan(t):      return c("36", t)
def white(t):     return c("97", t)


THEMES = {"magenta": "35", "cyan": "36", "green": "32", "yellow": "33", "blue": "34", "red": "31", "white": "97"}
_ACCENT = ["35"]


def set_theme(cfg):
    _ACCENT[0] = THEMES.get((cfg or {}).get("theme", "magenta"), "35")


def accent(t):      return c(_ACCENT[0], t)
def accent_bold(t): return c("1;" + _ACCENT[0], t)
def prefix():       return accent_bold("chode")


def term_width(default=80):
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


def hr(ch="─", width=None):
    return dim(ch * (width or min(term_width() - 2, 72)))


def set_title(text):
    if USE_COLOR:
        try:
            sys.stdout.write(f"\033]0;{text}\007")
            sys.stdout.flush()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Spinner
# --------------------------------------------------------------------------

class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    current = None   # the spinning one, so an interactive step (a CLI sign-in) can silence it

    @classmethod
    def stop_current(cls):
        if cls.current:
            cls.current.stop()

    def __init__(self, label="thinking"):
        self.label = label
        self._stop = threading.Event()
        self._thread = None
        self.t0 = None
        self._active = False

    def __enter__(self):
        if not sys.stdout.isatty():
            return self
        self.t0 = time.time()
        self._active = True
        Spinner.current = self
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r{dim(f'{frame} {self.label}… ({time.time()-self.t0:.0f}s)')}  ")
            sys.stdout.flush()
            i += 1
            time.sleep(0.1)

    def stop(self):
        if self._thread and self._active:
            self._stop.set()
            self._thread.join()
            self._active = False
            sys.stdout.write("\r" + " " * min(term_width(), 90) + "\r")
            sys.stdout.flush()

    def __exit__(self, *exc):
        self.stop()


# --------------------------------------------------------------------------
# Streaming markdown-lite renderer
# --------------------------------------------------------------------------

_HEADING_RX = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RX = re.compile(r"^(\s*)([-*•]|\d+[.)])\s+(.*)$")
_INLINE_CODE_RX = re.compile(r"`([^`\n]+)`")
_BOLD_RX = re.compile(r"\*\*([^*\n]+)\*\*")


def style_line(line, in_code=False):
    """Style one complete markdown line for the terminal."""
    if not USE_COLOR:
        return line
    if in_code:
        return dim(line)
    stripped = line.strip()
    if stripped.startswith("```"):
        return dim(line)
    m = _HEADING_RX.match(line)
    if m:
        return accent_bold(m.group(2))
    m = _BULLET_RX.match(line)
    if m:
        indent, marker, rest = m.groups()
        marker = accent("•") if marker in ("-", "*", "•") else accent(marker)
        line = f"{indent}{marker} {rest}"
    line = _BOLD_RX.sub(lambda mm: bold(mm.group(1)), line)
    line = _INLINE_CODE_RX.sub(lambda mm: cyan(mm.group(1)), line)
    return line


class StreamRenderer:
    """Prints streamed text as it arrives; when a line completes it is restyled
    in place (headings, bullets, inline code) if that is safe to do."""

    def __init__(self, out=None, first_prefix=None, dimmed=False):
        self.out = out or sys.stdout
        self.buf = ""
        self.in_code = False
        self.line_prefix = first_prefix if first_prefix is not None else prefix() + " "
        self.prefix_len = 6 if first_prefix is None else len(_strip_ansi(first_prefix))
        self.dimmed = dimmed
        self.started = False
        self.col = 0
        self.full = []

    def start(self):
        if not self.started:
            self.out.write("\n" + self.line_prefix)
            self.col = self.prefix_len
            self.started = True

    def feed(self, delta):
        if not delta:
            return
        self.start()
        self.full.append(delta)
        while "\n" in delta:
            head, delta = delta.split("\n", 1)
            self._write_raw(head)
            self._complete_line()
        self._write_raw(delta)
        self.out.flush()

    def _write_raw(self, s):
        if not s:
            return
        self.buf += s
        self.col += len(s)
        if self.in_code or self.dimmed:
            self.out.write(dim(s) if USE_COLOR else s)
        else:
            self.out.write(s)

    def _complete_line(self):
        line = self.buf
        fence = line.strip().startswith("```")
        was_code = self.in_code
        styled = style_line(line, in_code=was_code and not fence)
        can_rewrite = (USE_COLOR and self.col < term_width() - 1 and styled != line
                       and not (was_code and not fence))
        if can_rewrite:
            self.out.write("\r\033[K" + self.line_prefix + styled)
        self.out.write("\n")
        if fence:
            self.in_code = not self.in_code
        self.buf = ""
        self.col = 0
        self.line_prefix = ""
        self.prefix_len = 0

    def finish(self):
        if self.buf:
            self._complete_line()
        elif self.started:
            pass
        if self.started:
            self.out.write("\n")
        self.out.flush()
        return "".join(self.full)


_ANSI_RX = re.compile(r"\033\[[0-9;]*[A-Za-z]|\033\][^\007]*\007")


def _strip_ansi(s):
    return _ANSI_RX.sub("", s)


def render_markdown(text, first_prefix=None, dimmed=False):
    r = StreamRenderer(first_prefix=first_prefix, dimmed=dimmed)
    r.feed(text)
    r.finish()


# --------------------------------------------------------------------------
# Block font + CHAD × CODE collision intro
# --------------------------------------------------------------------------

BLOCK_FONT = {
    "C": [" ██████ ", "██      ", "██      ", "██      ", "██      ", " ██████ "],
    "H": ["██   ██ ", "██   ██ ", "███████ ", "██   ██ ", "██   ██ ", "██   ██ "],
    "A": [" █████  ", "██   ██ ", "██   ██ ", "███████ ", "██   ██ ", "██   ██ "],
    "D": ["██████  ", "██   ██ ", "██   ██ ", "██   ██ ", "██   ██ ", "██████  "],
    "O": [" █████  ", "██   ██ ", "██   ██ ", "██   ██ ", "██   ██ ", " █████  "],
    "E": ["███████ ", "██      ", "█████   ", "██      ", "██      ", "███████ "],
}
LETTER_W, FONT_H = 8, 6
TAGLINE_QUOTED = f"“ {TAGLINE} ”"


def _word_rows(word):
    return ["".join(BLOCK_FONT[ch][r] for ch in word) for r in range(FONT_H)]


_COLOR_CODES = {"m": "35", "c": "36", "x": "1;31", "s": "1;33", "b": "1", "d": "2"}


def _paint(canvas):
    out = []
    for row in canvas:
        parts, cur = [], None
        for ch, col in row:
            if col != cur:
                parts.append("\033[0m" if col is None else f"\033[{_COLOR_CODES[col]}m")
                cur = col
            parts.append(ch)
        parts.append("\033[0m")
        out.append("".join(parts) if USE_COLOR else "".join(ch for ch, _ in row))
    return out


def _blit(canvas, rows, x, colorkey, clash="x"):
    W = len(canvas[0])
    for r, line in enumerate(rows):
        for i, ch in enumerate(line):
            px = x + i
            if ch == " " or not (0 <= px < W):
                continue
            old_ch, _ = canvas[r][px]
            canvas[r][px] = ("▓", clash) if old_ch != " " else (ch, colorkey)


def _frame_out(lines, header_rows=1):
    sys.stdout.write("\033[H" + "\n" * header_rows + "\n".join("  " + l for l in lines) + "\n")
    sys.stdout.flush()


def _chode_canvas(W):
    canvas = [[(" ", None)] * W for _ in range(FONT_H)]
    x = max(0, (W - 5 * LETTER_W) // 2)
    _blit(canvas, _word_rows("CH"), x, "m")
    _blit(canvas, _word_rows("ODE"), x + 2 * LETTER_W, "c")
    return canvas


def static_banner(version=True):
    W = max(term_width() - 4, 44)
    print()
    for line in _paint(_chode_canvas(W)):
        print("  " + line)
    tag = TAGLINE_QUOTED + (f"   v{VERSION}" if version else "")
    pad = max(0, (W - len(tag)) // 2)
    print("  " + " " * pad + (dim(tag) if USE_COLOR else tag) + "\n")


def collision_intro(cfg=None):
    """CHAD slides in from the left, CODE from the right, they smash into dust, CHODE remains."""
    if (not sys.stdout.isatty() or os.environ.get("CHODE_NO_INTRO")
            or (cfg and cfg.get("intro") is False)):
        static_banner()
        return
    cols = term_width()
    if cols < 76:
        static_banner()
        return
    W = min(cols - 4, 110)
    chad_rows, code_rows = _word_rows("CHAD"), _word_rows("CODE")
    word_w = 4 * LETTER_W
    center = W // 2
    chad_final = center - word_w + 6
    code_final = center - 6
    steps = 15
    try:
        sys.stdout.write("\033[2J\033[?25l")
        for s in range(steps + 1):
            t = s / steps
            ease = t * t * (3 - 2 * t)
            cx = int(-word_w + (chad_final + word_w) * ease)
            dx = int(W - (W - code_final) * ease)
            canvas = [[(" ", None)] * W for _ in range(FONT_H)]
            _blit(canvas, chad_rows, cx, "m")
            _blit(canvas, code_rows, dx, "c")
            _frame_out(_paint(canvas))
            time.sleep(0.045)
        # impact: shake + dust + sparks in the clash zone
        for i, shake in enumerate((1, -1, 1, 0, 0)):
            canvas = [[(" ", None)] * W for _ in range(FONT_H)]
            _blit(canvas, chad_rows, chad_final + shake, "m")
            _blit(canvas, code_rows, code_final - shake, "c")
            spread = 3 + i * 4
            for _ in range(14 + i * 6):
                r = random.randrange(FONT_H)
                px = random.randrange(max(0, code_final - spread), min(W, chad_final + word_w + spread))
                canvas[r][px] = (random.choice("✦✧*·+░▒"), "s" if i < 2 else "d")
            _frame_out(_paint(canvas))
            time.sleep(0.07)
        # dust settles, CHODE revealed row by row
        chode = _chode_canvas(W)
        blank = [[(" ", None)] * W for _ in range(FONT_H)]
        for r in range(FONT_H):
            blank[r] = chode[r]
            _frame_out(_paint(blank))
            time.sleep(0.05)
        pad = max(0, (W - len(TAGLINE_QUOTED)) // 2)
        sys.stdout.write("\n  " + " " * pad)
        for ch in TAGLINE_QUOTED:
            sys.stdout.write(dim(ch))
            sys.stdout.flush()
            time.sleep(0.016)
        print("\n")
    except KeyboardInterrupt:
        sys.stdout.write("\033[2J\033[H")
        static_banner()
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


# --------------------------------------------------------------------------
# Greetings & quips
# --------------------------------------------------------------------------

GREETINGS = {
    "morning":   ["Rise and grind, {name} ☀️", "Morning, {name} — coffee then code", "Early reps, {name}. Respect."],
    "afternoon": ["Back at it, {name} 💪", "Midday pump, {name}?", "Afternoon gains incoming, {name}"],
    "evening":   ["Evening session, {name} 🌆", "One more set, {name}?", "Golden hour commits, {name}"],
    "night":     ["Night shift, {name} 🌙", "The grind never sleeps, {name}", "3am thoughts, {name}? Let's ship them."],
}
QUIPS = ["thicc like a tuna can", "certified girthy", "100% natty code", "leg day for your repo",
         "protein for your terminal", "never skips test day", "spotter included",
         "girth-first development", "elegance where none should belong", "c'mon, don't be a chode",
         "big can energy", "ships before it sleeps"]


def greeting(cfg):
    h = time.localtime().tm_hour
    bucket = "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 18 else "evening" if 18 <= h < 23 else "night"
    return random.choice(GREETINGS[bucket]).format(name=(cfg or {}).get("name") or "legend")


def quip():
    return random.choice(QUIPS)


# --------------------------------------------------------------------------
# Prompt helpers (used by wizard/doctor/menus)
# --------------------------------------------------------------------------

def ok(msg, detail=""):   print(f"  {green('✓')} {msg}" + (dim("  " + detail) if detail else ""))
def warn(msg, detail=""): print(f"  {yellow('⚠')} {msg}" + (dim("  " + detail) if detail else ""))
def bad(msg, detail=""):  print(f"  {red('✗')} {msg}" + (dim("  " + detail) if detail else ""))
def info(msg, detail=""): print(f"  {cyan('ℹ')} {msg}" + (dim("  " + detail) if detail else ""))


def choose(prompt, options, default=1):
    """Numbered picker. options: list of (label, note). Returns index (0-based)."""
    for i, (label, note) in enumerate(options, 1):
        mark = bold(f"{i}.") if i == default else f"{i}."
        print(f"    {mark} {label}" + (dim("  — " + note) if note else ""))
    while True:
        raw = input(f"  {prompt} [{default}] › ").strip()
        if not raw:
            return default - 1
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(red(f"    pick 1-{len(options)}"))


def yesno(prompt, default=True):
    d = "Y/n" if default else "y/N"
    try:
        raw = input(f"  {prompt} [{d}] › ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not raw:
        return default
    return raw in ("y", "yes")


def parse_selection(raw, n):
    raw = (raw or "").strip().lower()
    if raw in ("all", "a", "*"):
        return set(range(n))
    picked = set()
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            if a.strip().isdigit() and b.strip().isdigit():
                picked.update(range(int(a) - 1, int(b)))
        elif part.isdigit():
            picked.add(int(part) - 1)
    return {i for i in picked if 0 <= i < n}


# --------------------------------------------------------------------------
# UI adapter the agent loop talks to
# --------------------------------------------------------------------------

class TerminalUI:
    """Everything the agent loop needs from a front end. gui.WebUI mirrors this."""
    name = "terminal"
    interactive = True

    def __init__(self, quiet=False):
        self.quiet = quiet
        self._renderer = None

    # -- streaming assistant text --
    def text_start(self, dimmed=False):
        self._renderer = StreamRenderer(dimmed=dimmed)

    def text_delta(self, s):
        if self._renderer:
            self._renderer.feed(s)

    def text_end(self):
        if self._renderer:
            self._renderer.finish()
        self._renderer = None

    def text_full(self, text, dimmed=False):
        render_markdown(text, dimmed=dimmed)

    # -- tools --
    def tool_start(self, name, preview):
        print(f"  {green('⏺')} {bold(name)} {preview}")

    def tool_result(self, name, result):
        first = result.splitlines()[0] if result else ""
        more = f" {dim(f'(+{len(result.splitlines())-1} lines)')}" if result.count('\n') else ""
        print(f"    {dim('⎿ ' + first[:140] + ('…' if len(first) > 140 else ''))}{more}")

    def tool_denied(self, name):
        print(dim("  denied"))

    def todos(self, todos):
        icons = {"pending": "☐", "in_progress": yellow("◐"), "done": green("☑")}
        lines = []
        for t in todos:
            icon = icons.get(t.get("status", "pending"), "☐")
            text = t.get("text", "")
            lines.append(f"    {icon} {text if t.get('status') != 'done' else dim(text)}")
        if lines:
            print("\n" + "\n".join(lines))

    def notice(self, msg, level="dim"):
        fn = {"dim": dim, "warn": yellow, "error": red, "ok": green, "info": cyan, "plain": str}.get(level, dim)
        print(fn(msg))

    def status(self, text):
        print(dim("  " + text))

    def thinking(self, label):
        return Spinner(label)

    # -- questions --
    def ask_permission(self, req):
        """req: dict(name, args, describe, diff, outside, danger, can_prefix, prefix_word, deny)
        Returns 'y' | 'n' | 'a' (always this tool) | 'p' (prefix-allow)."""
        print(f"\n{yellow('●')} {bold(req['name'])} {req.get('describe', '')}")
        if req.get("diff"):
            print(req["diff"])
        if req.get("outside"):
            print(red(f"  ⚠ writes OUTSIDE the working directory ({req['outside']})"))
        if req.get("sensitive"):
            print(yellow(f"  ⚠ this file usually holds secrets ({req['sensitive']}) — its contents go to the model"))
        if req.get("danger"):
            print(red(f"  ⚠ DANGEROUS: {req['danger']}"))
            try:
                ans = input(red("  type 'yes' to run, anything else to deny › ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return "n"
            return "y" if ans == "yes" else "n"
        opts = f"[{green('y')}]es / [{red('n')}]o / [{cyan('a')}]lways `{req['name']}`"
        if req.get("can_prefix"):
            opts += f" / [{cyan('p')}]refix-allow `{req.get('prefix_word','')}`"
        while True:
            try:
                ans = input(f"  {dim('allow?')} {opts} › ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return "n"
            if ans in ("y", "yes", ""):
                return "y"
            if ans in ("n", "no"):
                return "n"
            if ans in ("a", "always"):
                return "a"
            if ans == "p" and req.get("can_prefix"):
                return "p"

    def ask_user(self, question, default=""):
        print(f"\n{accent('?')} {question}")
        try:
            ans = input(f"  {dim('›')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return default
        return ans or default


class SilentUI(TerminalUI):
    """For subagents / MCP-server mode: no streaming chatter, permissions decided by lanes only."""
    name = "silent"
    interactive = False

    def __init__(self, on_notice=None):
        super().__init__(quiet=True)
        self._on_notice = on_notice

    def text_start(self, dimmed=False): pass
    def text_delta(self, s): pass
    def text_end(self): pass
    def text_full(self, text, dimmed=False): pass
    def tool_start(self, name, preview): pass
    def tool_result(self, name, result): pass
    def tool_denied(self, name): pass
    def todos(self, todos): pass
    def status(self, text): pass

    def notice(self, msg, level="dim"):
        if self._on_notice:
            self._on_notice(msg, level)

    def thinking(self, label):
        return _NullCtx()

    def ask_permission(self, req):
        return "n"

    def ask_user(self, question, default=""):
        return default


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def stop(self): pass
