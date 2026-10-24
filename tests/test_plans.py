import json
import sys

import pytest

from chode.plans import (PlanAuthError, PlanClient, _last_json_object, chode_mcp_spec, detect_plans, looks_like_auth,
                         render_command, write_mcp_config)


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


def test_signed_out_claude_raises_auth(project):
    tmp, cfg, app = project
    c = PlanClient(cfg, "claude-plan")
    out = ('{"type":"result","is_error":true,"terminal_reason":"api_error",'
           '"result":"Not logged in · Please run /login","session_id":"s"}')
    with pytest.raises(PlanAuthError):
        c._parse(out, "")
    assert looks_like_auth("Invalid API key · Please run /login") and not looks_like_auth("hello there")


def test_llm_opens_login_once_then_reports_auth(project, monkeypatch):
    from chode import plans
    from chode.llm import LLMClient, LLMError
    tmp, cfg, app = project
    cfg["provider"], cfg["fallbacks"] = "claude-plan", "off"
    calls = {"chat": 0, "login": 0}
    signed_in = [False]

    def fake_chat(self, system, messages, on_text=None):
        calls["chat"] += 1
        if not signed_in[0]:
            raise PlanAuthError("Claude Code is not signed in: Not logged in")
        return {"content": "pong", "usage_in": 1, "usage_out": 1, "cost": 0.0}

    def fake_login(provider, inline=None, timeout=600):
        calls["login"] += 1
        signed_in[0] = True
        return True, "signed in"

    monkeypatch.setattr(plans.PlanClient, "chat", fake_chat)
    monkeypatch.setattr(plans, "login", fake_login)
    client = LLMClient(cfg)
    assert client.chat("s", [{"role": "user", "content": "ping"}])["content"] == "pong"
    assert calls == {"chat": 2, "login": 1}

    # sign-in fails → a clean auth error, and no second window on the next message
    monkeypatch.setattr(plans, "login", lambda *a, **k: (calls.__setitem__("login", calls["login"] + 1), (False, "nope"))[1])
    calls["login"], signed_in[0] = 0, False
    client = LLMClient(cfg)
    for _ in range(2):
        with pytest.raises(LLMError) as ei:
            client.chat("s", [{"role": "user", "content": "ping"}])
        assert ei.value.kind == "auth" and "/login" in ei.value.hint
    assert calls["login"] == 1


def test_unshim_npm_cmd(tmp_path, monkeypatch):
    from chode import plans
    monkeypatch.setattr(plans.os, "name", "nt")
    exe = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    shim = tmp_path / "claude.cmd"
    shim.write_text('@ECHO off\nCALL :find_dp0\n"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe"   %*\n')
    assert plans._unshim(str(shim)) == [str(exe)]
    js = tmp_path / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    js.parent.mkdir(parents=True)
    js.write_text("")
    (tmp_path / "node.exe").write_text("")
    shim2 = tmp_path / "codex.cmd"
    shim2.write_text('"%_prog%"  "%dp0%\\node_modules\\@openai\\codex\\bin\\codex.js" %*\n')
    assert plans._unshim(str(shim2)) == [str(tmp_path / "node.exe"), str(js)]
    assert plans._unshim(str(tmp_path / "claude.exe")) is None


def test_fix_signs_in_a_signed_out_plan(project, monkeypatch):
    from chode import lifeline, plans
    from chode.llm import LLMClient
    tmp, cfg, app = project
    cfg["provider"] = "claude-plan"
    seen = []
    monkeypatch.setattr(plans, "_which", lambda cli: "/bin/" + cli if cli else None)
    monkeypatch.setattr(plans, "logged_in", lambda cli: False)
    monkeypatch.setattr(plans, "login", lambda provider, inline=None, timeout=600: (seen.append(provider), (True, "signed in"))[1])
    monkeypatch.setattr(LLMClient, "chat", lambda self, *a, **k: {"content": "pong", "tool_calls": []})
    out = lifeline.run_fixer(cfg, ui=app.ui)
    assert seen == ["claude-plan"] and "signed in and answering" in out and cfg["provider"] == "claude-plan"


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
