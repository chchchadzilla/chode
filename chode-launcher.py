#!/usr/bin/env python3
"""
chode-start — Cross-platform splash launcher for Chad Code (CHODE v0.5.0)
Works seamlessly across macOS, Linux, and Windows.
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

def main():
    script_dir = Path(__file__).parent.resolve()
    
    # 1. Resolve splash file
    splash_env = os.environ.get("CHODE_SPLASH")
    if splash_env:
        splash_path = Path(splash_env)
    else:
        splash_path = Path.home() / ".chode" / "splash.mp4"
        if not splash_path.exists():
            splash_path = script_dir / "splash.mp4"

    skip_splash = os.environ.get("CHODE_NO_SPLASH") == "1"
    
    # 2. Render splash if video exists and stdout is interactive TTY
    if splash_path.exists() and not skip_splash and sys.stdout.isatty():
        chode_splash_py = script_dir / "chode_splash.py"
        ffmpeg_bin = shutil.which("ffmpeg")
        mpv_bin = shutil.which("mpv")
        ffplay_bin = shutil.which("ffplay")

        if ffmpeg_bin and chode_splash_py.exists():
            try:
                subprocess.run([sys.executable, str(chode_splash_py), str(splash_path)], check=False)
            except Exception:
                pass
        elif mpv_bin:
            try:
                subprocess.run([mpv_bin, "--vo=tct", "--really-quiet", "--length=10", str(splash_path)], check=False)
            except Exception:
                pass
        elif ffplay_bin:
            try:
                subprocess.run([ffplay_bin, "-autoexit", "-fs", "-loglevel", "quiet", str(splash_path)], check=False)
            except Exception:
                pass

    # 3. Launch main CHODE process
    chode_py = script_dir / "chode.py"
    if not chode_py.exists():
        print(f"Error: chode.py not found at {chode_py}")
        sys.exit(1)

    cmd = [sys.executable, str(chode_py)] + sys.argv[1:]
    
    # On POSIX (Mac/Linux), replace process; on Windows, run and exit
    if os.name != "nt":
        os.execv(sys.executable, cmd)
    else:
        sys.exit(subprocess.call(cmd))

if __name__ == "__main__":
    main()
