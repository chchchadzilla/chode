import json
import sys

from chode.hooks import HookRunner, _matches, load_hooks

PY = sys.executable


def test_matchers_accept_claude_names():
    assert _matches("Bash", "bash") and _matches("Edit|Write", "write_file") and _matches("", "anything")
    assert not _matches("Bash", "read_file")


def test_formats_merge(project):
    tmp, cfg, app = project
    cfg["hooks"] = {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "true"}]}]}
    (tmp / ".chode").mkdir()
    (tmp / ".chode" / "hooks.json").write_text(json.dumps({"post_tool": [{"match": "write_file", "command": "true"}]}), encoding="utf-8")
    h = load_hooks(cfg, tmp)
    assert len(h["pre_tool"]) == 1 and h["pre_tool"][0]["match"] == "Bash" and len(h["post_tool"]) == 1


def test_block_and_context(project):
    tmp, cfg, app = project
    script = tmp / "hook.py"
    script.write_text(
        "import json,sys,os\n"
        "d=json.load(sys.stdin)\n"
        "if d['tool_name']=='bash' and 'rm' in d['tool_input'].get('command',''):\n"
        "    sys.stderr.write('no rm'); sys.exit(2)\n"
        "print(json.dumps({'additionalContext': 'cwd=' + os.environ['CHODE_CWD']}))\n", encoding="utf-8")
    cfg["hooks"] = {"pre_tool": [{"command": f'"{PY}" "{script}"'}]}
    h = HookRunner(cfg, tmp)
    blocked, reason, extra = h.run("pre_tool", tool="bash", args={"command": "rm x"})
    assert blocked and "no rm" in reason
    blocked, reason, extra = h.run("pre_tool", tool="bash", args={"command": "ls"})
    assert not blocked and "cwd=" in extra
