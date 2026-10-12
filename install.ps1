# CHODE one-line installer (Windows PowerShell):
#   irm https://raw.githubusercontent.com/chchchadzilla/chode/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
$repo = "git+https://github.com/chchchadzilla/chode"
Write-Host ""
Write-Host "  CHODE - code thicc like a tuna can"
Write-Host ""
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
  Write-Host "  x Python 3.9+ not found. Install from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'."
  exit 1
}
if (Get-Command pipx -ErrorAction SilentlyContinue) {
  pipx install --force $repo
  Write-Host "  + installed with pipx"
} else {
  & $py.Source -m pip install --user --upgrade $repo
  Write-Host "  + installed with pip --user  (if 'chode' is not found: python -m chode)"
}
Write-Host ""
Write-Host "  next:  chode setup      <- 60 seconds, no coding required"
Write-Host "         chode import     <- pull your gear from Claude Code / Cursor / Codex / VS Code"
Write-Host ""
