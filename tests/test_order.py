import json
import tarfile
from pathlib import Path

from chode.order import (audit, backup, detect_project, last_backup_age_hours, list_backups, maybe_auto_backup,
                         restore_backup, scaffold, status_line, thiccness_label, tidy_report)


def test_detect_and_audit(project):
    tmp, cfg, app = project
    (tmp / "pyproject.toml").write_text('[project]\nname = "thing"\ndescription = "does stuff"\n', encoding="utf-8")
    (tmp / "thing.py").write_text("print(1)\n", encoding="utf-8")
    p = detect_project(tmp)
    assert p["name"] == "thing" and p["type"] == "python" and p["description"] == "does stuff"
    a = audit(tmp)
    keys = {c["key"]: c["ok"] for c in a["checks"]}
    assert keys["git"] and not keys["readme"] and not keys["license"] and keys["secrets"]
    assert 0 <= a["score"] <= 100 and a["label"] == thiccness_label(a["score"])


def test_audit_catches_tracked_secret(project):
    tmp, cfg, app = project
    (tmp / "cfg.py").write_text('TOKEN = "ghp_' + "x" * 30 + '"\n', encoding="utf-8")
    import subprocess
    subprocess.run(["git", "add", "-A"], cwd=tmp)
    a = audit(tmp)
    sec = next(c for c in a["checks"] if c["key"] == "secrets")
    assert not sec["ok"] and "cfg.py" in sec["detail"]


def test_scaffold_never_overwrites(project):
    tmp, cfg, app = project
    (tmp / "package.json").write_text(json.dumps({"name": "web", "version": "0.0.1"}), encoding="utf-8")
    (tmp / "CHANGELOG.md").write_text("# mine\n", encoding="utf-8")
    res = scaffold(tmp, apply=True, author="Tester")
    assert "LICENSE" in res["created"] and "CHANGELOG.md" not in res["created"]
    assert (tmp / "CHANGELOG.md").read_text(encoding="utf-8") == "# mine\n"
    assert "Tester" in (tmp / "LICENSE").read_text(encoding="utf-8")
    assert "node_modules/" in (tmp / ".gitignore").read_text(encoding="utf-8")
    assert ".chode/" in (tmp / ".gitignore").read_text(encoding="utf-8")
    assert (tmp / ".github" / "workflows" / "ci.yml").exists()
    assert "README.md" in res["needs_model"] and "ABOUT.md" in res["needs_model"]
    res2 = scaffold(tmp, apply=True)
    assert res2["created"] == []


def test_backup_rotation_and_restore(project):
    tmp, cfg, app = project
    (tmp / "a.txt").write_text("A", encoding="utf-8")
    (tmp / "node_modules").mkdir()
    (tmp / "node_modules" / "big.js").write_text("x" * 100, encoding="utf-8")
    (tmp / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    cfg["order"]["backup_keep"] = 2
    paths = [backup(tmp, cfg, note=str(i))["path"] for i in range(3)]
    bl = list_backups(tmp)
    assert len(bl) == 2 and bl[0]["note"] == "2"
    with tarfile.open(bl[0]["path"]) as tar:
        names = tar.getnames()
    assert "a.txt" in names and not any("node_modules" in n for n in names)
    dest = tmp.parent / "restored"
    restore_backup(bl[0]["path"], dest)
    assert (dest / "a.txt").read_text(encoding="utf-8") == "A"
    assert last_backup_age_hours(tmp) < 1
    cfg["order"]["auto_backup_hours"] = 24
    assert maybe_auto_backup(tmp, cfg) is None  # fresh backup exists
    cfg["order"]["backup_max_mb"] = 0.00001
    assert backup(tmp, cfg)["ok"] is False


def test_tidy_and_status(project):
    tmp, cfg, app = project
    (tmp / "debug.log").write_text("x", encoding="utf-8")
    (tmp / "empty").mkdir()
    tips = dict(tidy_report(tmp))
    assert "debug.log" in tips and "empty/" in tips
    line, a = status_line(tmp, cfg)
    assert line.startswith("ORDER") and "backup" in line
