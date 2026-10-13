"""Test harness: every test gets a throwaway CHODE_HOME and HOME, and runs inside a
fresh git repo so nothing touches the developer's real ~/.chode."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="chode-tests-"))
os.environ["CHODE_HOME"] = str(_TMP / "home" / ".chode")
os.environ["HOME"] = str(_TMP / "home")
os.environ["USERPROFILE"] = str(_TMP / "home")
os.environ["XDG_CONFIG_HOME"] = str(_TMP / "home" / ".config")
os.environ["APPDATA"] = str(_TMP / "home" / "AppData" / "Roaming")
os.environ["CHODE_NO_INTRO"] = "1"
os.environ["NO_COLOR"] = "1"
(_TMP / "home" / ".chode").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from chode import state  # noqa: E402
from chode.config import load_config  # noqa: E402
from chode.ui import SilentUI  # noqa: E402


def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A fresh git repo as cwd, with a configured App (local provider, SilentUI)."""
    monkeypatch.chdir(tmp_path)
    _git(["init", "-q", "-b", "main"], tmp_path)
    _git(["config", "user.email", "t@test"], tmp_path)
    _git(["config", "user.name", "tester"], tmp_path)
    cfg = load_config(tmp_path)
    cfg["provider"] = "local"
    cfg["mode"] = "yolo"
    cfg["rag"]["auto_index"] = False
    cfg["order"]["auto_backup_hours"] = 0
    cfg["memory"]["auto_reflect"] = False
    cfg["conscience"]["reflect"] = False
    app = state.set_app(state.App(cfg, ui=SilentUI()))
    yield tmp_path, cfg, app
    state.set_app(None)


@pytest.fixture
def mock_llm():
    from mock_server import MockLLM
    return MockLLM
