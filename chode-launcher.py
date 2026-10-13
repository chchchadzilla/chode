#!/usr/bin/env python3
"""chode-launcher.py — run CHODE straight from a git checkout, no install needed.

    python3 chode-launcher.py            # menu
    python3 chode-launcher.py -p "hi"    # one-shot

Optional terminal splash video: drop an .mp4 at ~/.chode/splash.mp4 (needs ffmpeg).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()


def _splash():
    if os.environ.get("CHODE_NO_SPLASH") == "1" or not sys.stdout.isatty():
        return
    splash = Path(os.environ.get("CHODE_SPLASH") or (Path.home() / ".chode" / "splash.mp4"))
    if not splash.exists():
        splash = HERE / "splash.mp4"
    if not splash.exists():
        return
    player = HERE / "chode_splash.py"
    try:
        if shutil.which("ffmpeg") and player.exists():
            subprocess.run([sys.executable, str(player), str(splash)], check=False)
        elif shutil.which("mpv"):
            subprocess.run(["mpv", "--vo=tct", "--really-quiet", "--length=10", str(splash)], check=False)
    except Exception:
        pass


def main():
    try:
        import requests  # noqa: F401
    except ImportError:
        print("CHODE needs one package. Installing it now:  pip install requests")
        subprocess.call([sys.executable, "-m", "pip", "install", "--user", "requests"])
    _splash()
    sys.path.insert(0, str(HERE))
    from chode.cli import main as chode_main
    chode_main()


if __name__ == "__main__":
    main()
