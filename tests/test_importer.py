import json
import os
from pathlib import Path

from chode.importer import _parse_toml, apply, mcp_from_obj, scan
from chode.paths import GLOBAL_COMMANDS_DIR, GLOBAL_MEMORY_FILE, GLOBAL_SKILLS_DIR


def _fake_home():
    home = Path(os.environ["HOME"])
    (home / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "skills" / "deploy").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "CLAUDE.md").write_text("# global\nAlways run the tests before claiming success.\n", encoding="utf-8")
    (home / ".claude" / "commands" / "review.md").write_text("---\ndescription: review code\n---\nReview $ARGUMENTS carefully\n", encoding="utf-8")
    (home / ".claude" / "skills" / "deploy" / "SKILL.md").write_text("---\nname: deploy\ndescription: ship to prod\n---\nsteps\n", encoding="utf-8")
    (home / ".claude" / "agents" / "reviewer.md").write_text("---\nname: reviewer\ndescription: reviews\n---\nYou review.\n", encoding="utf-8")
    (home / ".claude" / "settings.json").write_text(json.dumps({
        "permissions": {"allow": ["Bash(npm test:*)", "Bash(git diff *)", "Read"], "deny": ["Bash(rm -rf *)"]},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}]}}), encoding="utf-8")
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"fs": {"command": "npx", "args": ["-y", "fs"]},
                                                                  "remote": {"url": "https://mcp.example.com/sse"}}}), encoding="utf-8")
    (home / ".codex").mkdir(exist_ok=True)
    (home / ".codex" / "config.toml").write_text('model = "gpt-5-codex"\n[mcp_servers.gh]\ncommand = "gh-mcp"\nargs = ["serve"]\n', encoding="utf-8")
    (home / ".codex" / "prompts").mkdir(exist_ok=True)
    (home / ".codex" / "prompts" / "tidy.md").write_text("Tidy the repo: $ARGUMENTS\n", encoding="utf-8")
    (home / ".gemini" / "commands").mkdir(parents=True, exist_ok=True)
    (home / ".gemini" / "commands" / "plan.toml").write_text('description = "plan it"\nprompt = "Plan {{args}} step by step"\n', encoding="utf-8")
    (home / ".gemini" / "settings.json").write_text(json.dumps({"mcpServers": {"gem": {"command": "gem-mcp"}}}), encoding="utf-8")
    (home / ".cursor").mkdir(exist_ok=True)
    (home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"cur": {"command": "cur-mcp", "env": {"A": "1"}}}}), encoding="utf-8")
    vs = Path(os.environ["XDG_CONFIG_HOME"]) / "Code" / "User"
    vs.mkdir(parents=True, exist_ok=True)
    (vs / "mcp.json").write_text(json.dumps({"servers": {"vsc": {"type": "stdio", "command": "vsc-mcp"}}}), encoding="utf-8")
    (vs / "settings.json").write_text(json.dumps({"github.copilot.chat.codeGeneration.instructions": [{"text": "prefer early returns"}]}), encoding="utf-8")
    ext = home / ".vscode" / "extensions"
    (ext / "saoudrizwan.claude-dev-3.1.0").mkdir(parents=True, exist_ok=True)
    (ext / "continue.continue-1.0.0").mkdir(parents=True, exist_ok=True)
    (home / ".config" / "opencode").mkdir(parents=True, exist_ok=True)
    (home / ".config" / "opencode" / "opencode.json").write_text(json.dumps({"mcp": {"oc": {"type": "local", "command": ["oc-mcp", "--x"]}}}), encoding="utf-8")
    return home


def test_scan_finds_everything(project):
    tmp, cfg, app = project
    _fake_home()
    (tmp / ".cursorrules").write_text("Use 2-space indentation everywhere in this repo.\n", encoding="utf-8")
    (tmp / "AGENTS.md").write_text("# agents\nRun `make test` before every commit.\n", encoding="utf-8")
    (tmp / ".agent" / "rules").mkdir(parents=True)
    (tmp / ".agent" / "rules" / "style.md").write_text("Antigravity style rule: no semicolons please.\n", encoding="utf-8")
    items = scan(cfg, tmp)
    kinds = {}
    for it in items:
        kinds.setdefault(it.kind, set()).add(it.name)
    assert {"review", "tidy", "plan"} <= kinds["command"]
    assert "deploy" in kinds["skill"] and "reviewer" in kinds["agent"]
    assert {"fs", "remote", "gh", "gem", "cur", "vsc", "oc"} <= kinds["mcp"]
    assert {"npm test", "git diff"} <= kinds["allow"] and "rm -rf" in kinds["deny"]
    assert kinds["hook"]
    mem_names = kinds["memory"]
    assert any(".cursorrules" in n for n in mem_names) and any("AGENTS.md" in n for n in mem_names)
    assert any("style.md" in n for n in mem_names) and any("codeGeneration" in n for n in mem_names)
    assert kinds["extension"]
    agents = {it.agent for it in items}
    assert {"Claude Code", "Codex", "Gemini CLI", "Cursor", "Antigravity", "OpenCode"} <= agents


def test_apply_is_idempotent_and_redacts(project):
    tmp, cfg, app = project
    home = _fake_home()
    (home / ".claude" / "CLAUDE.md").write_text("token sk-ant-" + "Q" * 40 + "\nbe nice\n", encoding="utf-8")
    items = scan(cfg, tmp)
    report = apply(items, cfg, tmp)
    assert any(line.startswith("✓ memory") and "secrets stripped" in line for line in report)
    assert "Q" * 40 not in GLOBAL_MEMORY_FILE.read_text(encoding="utf-8")
    assert (GLOBAL_SKILLS_DIR / "deploy" / "SKILL.md").exists()
    assert (GLOBAL_COMMANDS_DIR / "review.md").read_text(encoding="utf-8").count("$ARGUMENTS") == 1
    assert "Plan $ARGUMENTS step by step" in (GLOBAL_COMMANDS_DIR / "plan.md").read_text(encoding="utf-8")
    assert cfg["mcp_servers"]["fs"]["command"] == "npx" and cfg["mcp_servers"]["remote"]["transport"] == "http"
    assert cfg["mcp_servers"]["oc"] == {"transport": "stdio", "command": "oc-mcp", "args": ["--x"], "env": {}}
    assert "npm test" in cfg["bash_allow"] and "rm -rf" in cfg["bash_deny"]
    assert cfg["hooks"]["PreToolUse"]
    again = apply(scan(cfg, tmp), cfg, tmp)
    assert all(not l.startswith("✓ memory") for l in again)
    assert any(l.startswith("= skill deploy") for l in again)


def test_scan_other_drives_and_named_paths(project, tmp_path_factory):
    """Skills on an external drive: a copied home (E:\\Users\\bob\\.claude) and a stray folder of SKILL.md dirs,
    plus `chode import <folder>` pointing at one skill, a skills folder and a project."""
    from chode.importer import classify_path, find_on_volume, volume_label
    tmp, cfg, app = project
    vol = tmp_path_factory.mktemp("USB-BACKUP")
    old_home = vol / "Users" / "bob"
    (old_home / ".claude" / "skills" / "ext-deploy").mkdir(parents=True)
    (old_home / ".claude" / "skills" / "ext-deploy" / "SKILL.md").write_text("---\nname: ext-deploy\ndescription: from the usb\n---\nsteps\n", encoding="utf-8")
    (old_home / ".claude" / "CLAUDE.md").write_text("# old laptop rules\nAlways write tests first, every single time.\n", encoding="utf-8")
    (old_home / ".codex" / "prompts").mkdir(parents=True)
    (old_home / ".codex" / "prompts" / "ship.md").write_text("Ship it: $ARGUMENTS\n", encoding="utf-8")
    stray = vol / "stuff" / "my-skills"
    (stray / "stray-one").mkdir(parents=True)
    (stray / "stray-one" / "SKILL.md").write_text("---\nname: stray-one\ndescription: loose skill\n---\nbody\n", encoding="utf-8")
    (vol / "Windows" / "System32" / "nope").mkdir(parents=True)          # never walked
    (vol / "Windows" / "System32" / "nope" / "SKILL.md").write_text("---\nname: nope\n---\n", encoding="utf-8")
    homes, roots = find_on_volume(vol)
    assert old_home.resolve() in [h.resolve() for h in homes]
    assert stray.resolve() in [r.resolve() for r in roots] and not any("Windows" in str(r) for r in roots)
    items = scan(cfg, tmp, volumes=[vol])
    by = {(it.kind, it.name): it for it in items}
    label = volume_label(vol)
    assert by[("skill", "ext-deploy")].agent == f"Claude Code @ {label}"
    assert by[("skill", "stray-one")].agent == f"skills folder @ {label}"
    assert by[("command", "ship")].agent == f"Codex @ {label}"
    assert any(it.kind == "memory" and "CLAUDE.md" in it.name and it.agent.endswith(label) for it in items)
    assert ("skill", "nope") not in by
    # named paths: a single skill, a skills folder, a copied home, a project with .cursorrules
    proj = tmp_path_factory.mktemp("someproject")
    (proj / ".cursorrules").write_text("Project rule: tabs not spaces, always and forever.\n", encoding="utf-8")
    assert classify_path(stray / "stray-one") == "skill" and classify_path(stray) == "skills_root"
    assert classify_path(old_home) == "home" and classify_path(proj) == "project"
    items = scan(cfg, tmp, paths=[str(stray / "stray-one"), str(old_home), str(proj)])
    kinds = {(it.kind, it.name) for it in items}
    assert ("skill", "stray-one") in kinds and ("skill", "ext-deploy") in kinds
    assert any(k == "memory" and ".cursorrules" in n for k, n in kinds)
    report = apply([it for it in items if it.kind == "skill"], cfg, tmp)
    assert (GLOBAL_SKILLS_DIR / "stray-one" / "SKILL.md").exists() and (GLOBAL_SKILLS_DIR / "ext-deploy" / "SKILL.md").exists()
    assert sum(1 for l in report if l.startswith("✓ skill")) == 2


def test_external_volumes_never_includes_home_or_root(monkeypatch):
    from chode.importer import external_volumes
    vols = external_volumes()            # whatever this machine has mounted: must be dirs, never / or $HOME
    for v in vols:
        assert Path(v).is_dir() and Path(v).resolve() != Path("/")
        assert not str(Path(os.environ["HOME"]).resolve()).startswith(str(Path(v).resolve()))


def test_mcp_from_obj_and_toml():
    found = mcp_from_obj({"x": {"mcpServers": {"a": {"command": "c", "args": ["1"]}, "b": {"url": "https://u"}, "bad": {"disabled": True, "command": "c"}}}})
    assert set(found) == {"a", "b"} and found["b"]["transport"] == "http"
    assert mcp_from_obj({"context_servers": {"z": {"command": "zz"}}})["z"]["command"] == "zz"
    data = _parse_toml('model = "m"\n[mcp_servers.one]\ncommand = "x"\nargs = ["a", "b"]\n')
    assert data["model"] == "m" and data["mcp_servers"]["one"]["args"] == ["a", "b"]
