import json
import sys

from chode.plans import PlanClient, _last_json_object, chode_mcp_spec, detect_plans, render_command, write_mcp_config


def test_render_command_token_substitution():
    argv = render_command('mycli -p {prompt} --json {model} {resume} --x={cwd}', prompt='say "hi"\nnow', model=["-m", "opus"],
                          resume=[], cwd="/w")
    assert argv == ["mycli", "-p", 'say "hi"\nnow', "--json", "-m", "opus", "--x=/w"]
    assert render_command("a {missing}", other="x") == ["a", "{missing}"]


def test_mcp_spec_and_config_file(tmp_path):
    spec = chode_mcp_spec("edits", tmp_path)
    assert spec["command"] == sys.executable and spec["args"][:3] == ["-m", "chode", "mcp-serve"]
    path = write_mcp_config("plan", tmp_path)
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["mcpServers"]["chode"]["args"][-1] == "plan"
    assert write_mcp_config("edits", fmt="codex") == ""


def test_detect_plans_shape():
    rows = detect_plans()
    assert {r[0] for r in rows} == {"claude-plan", "codex-plan", "gemini-plan", "custom-plan"}


def test_parse_outputs(project):
    tmp, cfg, app = project
    c = PlanClient(cfg, "claude-plan")
    out = c._parse('{"type":"result","result":"hello","session_id":"abc","usage":{"input_tokens":5,"output_tokens":2}}', "")
    assert out["content"] == "hello" and c.session_id == "abc" and out["usage_in"] == 5
    c = PlanClient(cfg, "codex-plan")
    lines = "\n".join([json.dumps({"type": "thread.started", "thread_id": "t1"}),
                       json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done it"}}),
                       json.dumps({"type": "turn.completed", "usage": {"input_tokens": 9, "output_tokens": 3}})])
    out = c._parse(lines, "")
    assert out["content"] == "done it" and c.session_id == "t1" and out["usage_out"] == 3
    g = PlanClient(cfg, "gemini-plan")
    assert g._parse('{"response":"yo","stats":{"input_tokens":1}}', "")["content"] == "yo"
    assert PlanClient(cfg, "custom-plan")._parse("plain text answer", "")["content"] == "plain text answer"
    assert _last_json_object('noise\n{"a":1}\n') == {"a": 1} and _last_json_object("") is None


def test_prompt_packing(project):
    tmp, cfg, app = project
    c = PlanClient(cfg, "claude-plan")
    msgs = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "ok", "tool_calls": []},
            {"role": "user", "content": "second"}]
    p = c._build_prompt("SYSTEM", msgs)
    assert "<chode_context>" in p and "USER: first" in p and p.endswith("second")
    c.session_id = "x"
    c.turns = 1
    assert c._build_prompt("SYSTEM", msgs) == "second"
