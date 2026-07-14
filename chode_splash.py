#!/usr/bin/env python3
"""
chode_splash.py — plays a video file INSIDE the terminal as ANSI truecolor
half-block art, then fades to black and hands off to the CLI.

Requires ffmpeg on PATH. Audio plays through ffplay if available.

Usage: python3 chode_splash.py path/to/splash.mp4 [--fps 14] [--no-audio] [--max-seconds 10]
"""

import os
import shutil
import subprocess
import sys
import time

RESET = "\033[0m"

if os.name == "nt":  # enable ANSI escape processing on Windows consoles
    try:
        import ctypes
        _k32 = ctypes.windll.kernel32
        _h = _k32.GetStdHandle(-11)
        _m = ctypes.c_uint32()
        if _k32.GetConsoleMode(_h, ctypes.byref(_m)):
            _k32.SetConsoleMode(_h, _m.value | 0x0004)
    except Exception:
        os.system("")
FPS_DEFAULT = 14


def term_size():
    ts = shutil.get_terminal_size((80, 24))
    cols = max(20, ts.columns)
    rows = max(10, ts.lines - 1)
    return cols, rows * 2  # half-blocks: 2 pixels per text row


def render_frame(buf, w, h):
    """RGB24 buffer → one string using ▀ (fg = top pixel, bg = bottom pixel)."""
    out = ["\033[H"]
    last_fg = last_bg = None
    for y in range(0, h - 1, 2):
        row_top = y * w * 3
        row_bot = (y + 1) * w * 3
        line = []
        for x in range(w):
            t = row_top + x * 3
            b = row_bot + x * 3
            fg = (buf[t], buf[t + 1], buf[t + 2])
            bg = (buf[b], buf[b + 1], buf[b + 2])
            codes = []
            if fg != last_fg:
                codes.append(f"38;2;{fg[0]};{fg[1]};{fg[2]}")
                last_fg = fg
            if bg != last_bg:
                codes.append(f"48;2;{bg[0]};{bg[1]};{bg[2]}")
                last_bg = bg
            line.append((f"\033[{';'.join(codes)}m" if codes else "") + "▀")
        out.append("".join(line) + RESET + "\n")
        last_fg = last_bg = None
    return "".join(out)


def fade_out(buf, w, h, steps=6, step_time=0.06):
    """Progressively darken the last frame down to black."""
    for i in range(steps, -1, -1):
        k = i / steps
        dark = bytes(int(b * k) for b in buf)
        sys.stdout.write(render_frame(dark, w, h))
        sys.stdout.flush()
        time.sleep(step_time)


def main():
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print("usage: chode_splash.py <video-file>", file=sys.stderr)
        return 1
    video = sys.argv[1]
    fps = FPS_DEFAULT
    no_audio = "--no-audio" in sys.argv
    max_seconds = 10
    for i, a in enumerate(sys.argv):
        if a == "--fps" and i + 1 < len(sys.argv):
            fps = max(1, min(30, int(sys.argv[i + 1])))
        if a == "--max-seconds" and i + 1 < len(sys.argv):
            max_seconds = int(sys.argv[i + 1])

    if not shutil.which("ffmpeg"):
        print("chode_splash: ffmpeg not found — skipping splash", file=sys.stderr)
        return 0

    w, h = term_size()
    h -= h % 2
    frame_bytes = w * h * 3

    ff = subprocess.Popen(
        ["ffmpeg", "-v", "quiet", "-i", video, "-t", str(max_seconds),
         "-vf", f"scale={w}:{h}:flags=area,fps={fps}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        stdout=subprocess.PIPE)

    audio = None
    if not no_audio and shutil.which("ffplay"):
        audio = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
             "-t", str(max_seconds), video],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    last = None
    frame_time = 1.0 / fps
    try:
        sys.stdout.write("\033[2J\033[?25l")  # clear, hide cursor
        next_t = time.time()
        while True:
            buf = ff.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            now = time.time()
            if now < next_t:
                time.sleep(next_t - now)
            elif now - next_t > frame_time * 2:
                next_t = now  # we're behind; drop pacing debt, keep playing
            sys.stdout.write(render_frame(buf, w, h))
            sys.stdout.flush()
            last = buf
            next_t += frame_time
        if last:
            fade_out(last, w, h)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        try:
            ff.terminate()
        except Exception:
            pass
        if audio:
            try:
                audio.terminate()
            except Exception:
                pass
        sys.stdout.write(RESET + "\033[2J\033[H\033[?25h")  # clean slate, cursor back
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
