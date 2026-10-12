"""Where CHODE keeps its stuff.

Everything lives under ~/.chode (override with the CHODE_HOME env var — handy
for tests and for keeping work/personal setups apart).
"""
import os
from pathlib import Path

IS_WIN = os.name == "nt"

CONFIG_DIR = Path(os.environ.get("CHODE_HOME") or (Path.home() / ".chode")).expanduser()
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
CHECKPOINT_DIR = CONFIG_DIR / "checkpoints"
GLOBAL_SKILLS_DIR = CONFIG_DIR / "skills"
GLOBAL_COMMANDS_DIR = CONFIG_DIR / "commands"
GLOBAL_AGENTS_DIR = CONFIG_DIR / "agents"
MEMORY_DIR = CONFIG_DIR / "memory"
BACKUP_DIR = CONFIG_DIR / "backups"
LEDGER_FILE = CONFIG_DIR / "ledger.jsonl"
CONSCIENCE_FILE = CONFIG_DIR / "CONSCIENCE.md"
GLOBAL_MEMORY_FILE = CONFIG_DIR / "CHODE.md"

MEMORY_FILENAME = "CHODE.md"
PROJECT_DIRNAME = ".chode"

# Instruction files CHODE reads natively from a project — zero migration needed.
# Order = precedence when the same guidance appears twice (first wins).
INSTRUCTION_FILES = [
    "CHODE.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "AGENT.md",
    "CONVENTIONS.md",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
    ".github/copilot-instructions.md",
    ".junie/guidelines.md",
]

MAX_TOOL_OUTPUT = 30_000
MAX_AGENT_TURNS = 60

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
             ".pytest_cache", "dist", "build", ".next", "target", ".tox", ".idea",
             ".chode", ".cache", ".ruff_cache", "coverage", ".nuxt", ".svelte-kit",
             ".turbo", ".parcel-cache", "vendor", ".terraform", ".gradle", ".dart_tool"}


def project_dir(cwd=None):
    return Path(cwd or Path.cwd()) / PROJECT_DIRNAME


def ensure_home():
    for d in (CONFIG_DIR, SESSIONS_DIR, CHECKPOINT_DIR, GLOBAL_SKILLS_DIR,
              GLOBAL_COMMANDS_DIR, GLOBAL_AGENTS_DIR, MEMORY_DIR, BACKUP_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
