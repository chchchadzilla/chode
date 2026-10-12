import subprocess

from chode.publish import (_categorize, _clean_message, autocommit, bump_version_files, changed_files, commits_since,
                           current_branch, is_repo, release_notes, ship, staged_secret_hits, update_changelog)


def test_ship_local_flow(project):
    tmp, cfg, app = project
    assert is_repo(tmp) and current_branch(tmp) == "main"
    assert ship(tmp, cfg, push=False) == "nothing to commit — working tree clean"
    (tmp / "a.py").write_text("print('a')\n", encoding="utf-8")
    out = ship(tmp, cfg, message="feat: add a", push=False)
    assert out.startswith("✓ committed on main: feat: add a")
    assert changed_files(tmp) == []
    (tmp / "b.py").write_text("x = 1\n", encoding="utf-8")
    asked = {}

    def fake_model(prompt):
        asked["prompt"] = prompt
        return "```\nchore: add b\n\n- adds b\n```"
    out = ship(tmp, cfg, ask_model=fake_model, push=False)
    assert "chore: add b" in out and "diffstat" in asked["prompt"]
    log = subprocess.run(["git", "log", "--pretty=%s"], cwd=tmp, capture_output=True, text=True).stdout
    assert "chore: add b" in log


def test_ship_refuses_secrets(project):
    tmp, cfg, app = project
    (tmp / "cfg.py").write_text('API = "sk-' + "z" * 30 + '"\n', encoding="utf-8")
    out = ship(tmp, cfg, message="x", push=False)
    assert out.startswith("🛑") and changed_files(tmp)  # nothing committed, still dirty
    assert ship(tmp, cfg, message="x", push=False, force=True).startswith("✓")


def test_autocommit(project):
    tmp, cfg, app = project
    assert autocommit(tmp, cfg) is None
    (tmp / "n.txt").write_text("n", encoding="utf-8")
    assert autocommit(tmp, cfg, summary="user asked for n").startswith("autocommitted")
    (tmp / "leak.txt").write_text("ghp_" + "k" * 30, encoding="utf-8")
    assert "skipped" in autocommit(tmp, cfg)


def test_release_helpers(project):
    tmp, cfg, app = project
    (tmp / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp / "package.json").write_text('{"name": "x", "version": "0.1.0"}\n', encoding="utf-8")
    pkg = tmp / "x"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('VERSION = "0.1.0"\n', encoding="utf-8")
    changed = bump_version_files(tmp, "v1.2.3")
    assert set(changed) == {"pyproject.toml", "package.json", "x/__init__.py"}
    assert 'version = "1.2.3"' in (tmp / "pyproject.toml").read_text(encoding="utf-8")
    ship(tmp, cfg, message="feat: first", push=False)
    ship(tmp, cfg, message="fix: second", push=False) if (tmp / "z").write_text("z") is None else None
    notes = release_notes(tmp, "v1.2.3")
    assert "### Added" in notes and "feat: first" in notes
    assert update_changelog(tmp, "v1.2.3", notes) and not update_changelog(tmp, "v1.2.3", notes)
    assert "## [1.2.3]" in (tmp / "CHANGELOG.md").read_text(encoding="utf-8")
    cats = _categorize(["feat: a", "fix: b", "docs: c", "refactor: d", "misc"])
    assert set(cats) == {"Added", "Fixed", "Docs", "Changed", "Other"}
    assert _clean_message("```\nfeat: x\n```") == "feat: x"
    assert len(_clean_message("x" * 100).splitlines()[0]) <= 72
