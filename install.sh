#!/usr/bin/env sh
# CHODE one-line installer (macOS / Linux):   curl -fsSL https://raw.githubusercontent.com/chchchadzilla/chode/main/install.sh | sh
# It only does one thing: installs the `chode` command with pipx (preferred) or pip --user.
set -e
REPO="git+https://github.com/chchchadzilla/chode"
echo ""
echo "  CHODE — code thicc like a tuna can"
echo ""
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "  ✗ Python 3.9+ not found."
  echo "    macOS:  brew install python3     Ubuntu/Debian:  sudo apt install python3 python3-pip"
  exit 1
fi
if command -v pipx >/dev/null 2>&1; then
  pipx install --force "$REPO" && echo "  ✓ installed with pipx"
else
  "$PY" -m pip install --user --upgrade "$REPO" && echo "  ✓ installed with pip --user"
  echo "  (if 'chode' is not found, add ~/.local/bin to your PATH, or: python3 -m chode)"
fi
echo ""
echo "  next:  chode setup      ← 60 seconds, no coding required"
echo "         chode import     ← pull your gear from Claude Code / Cursor / Codex / VS Code"
echo ""
