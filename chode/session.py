"""Checkpoints (undo) and session persistence (auto-save / resume)."""
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path

from .paths import CHECKPOINT_DIR, SESSIONS_DIR


class Checkpoints:
    """Backs up files before CHODE modifies them so /undo can restore them."""

    def __init__(self):
        self.session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.dir = CHECKPOINT_DIR / self.session_id
        self.stack = []  # list of (target_path, backup_path_or_None_if_file_was_new)

    def before_modify(self, path):
        path = Path(path).expanduser().resolve()
        if path.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            backup = self.dir / f"{len(self.stack):04d}_{path.name}"
            try:
                shutil.copy2(path, backup)
                self.stack.append((path, backup))
            except Exception:
                pass
        else:
            self.stack.append((path, None))

    def undo(self):
        if not self.stack:
            return None
        path, backup = self.stack.pop()
        try:
            if backup is None:
                if path.exists():
                    path.unlink()
                return f"deleted {path} (was created by CHODE)"
            shutil.copy2(backup, path)
            return f"restored {path}"
        except Exception as e:
            return f"undo failed for {path}: {e}"

    def touched(self):
        seen = []
        for p, _ in self.stack:
            if p not in seen:
                seen.append(p)
        return seen

    def cleanup(self):
        try:
            if self.dir.exists() and not any(self.dir.iterdir()):
                self.dir.rmdir()
        except Exception:
            pass


def project_key(cwd=None):
    return hashlib.sha1(str(Path(cwd or Path.cwd()).resolve()).encode()).hexdigest()[:12]


def session_dir_for_cwd(cwd=None):
    return SESSIONS_DIR / project_key(cwd)


class SessionStore:
    def __init__(self, cwd=None):
        self.dir = session_dir_for_cwd(cwd)
        self.file = self.dir / (time.strftime("%Y%m%d-%H%M%S") + ".json")
        self.meta = {}

    def save(self, history, **meta):
        if not history:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.meta.update(meta)
            self.file.write_text(json.dumps({
                "cwd": str(Path.cwd()), "ts": time.time(), "meta": self.meta,
                "history": history}, indent=0), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def list_sessions(cwd=None):
        d = session_dir_for_cwd(cwd)
        if not d.is_dir():
            return []
        return sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

    @staticmethod
    def load(path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return data.get("history", [])
        except Exception:
            return []

    @staticmethod
    def load_meta(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8")).get("meta", {})
        except Exception:
            return {}


def session_summary(path):
    hist = SessionStore.load(path)
    first = next((m["content"] for m in hist if m["role"] == "user"), "")
    first = first.strip().splitlines()[0] if first.strip() else ""
    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
    return f"{ts}  ({len(hist)} msgs)  {first[:70]}"


def prune_sessions(keep=200):
    """Keep the newest N session files per project; delete the rest."""
    removed = 0
    if not SESSIONS_DIR.is_dir():
        return 0
    for d in SESSIONS_DIR.iterdir():
        if not d.is_dir():
            continue
        files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[keep:]:
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass
    return removed
