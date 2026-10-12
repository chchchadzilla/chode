"""End-to-end: real agent loop against the scripted mock LLM, streaming and not."""
import json

import pytest

from chode import state
from chode.agent import build_system_prompt, compact_history, oneshot_ask, run_agent
from chode.llm import LLMClient, LLMError
from chode.permissions import Permissions, render_diff
from chode.ui import SilentUI


def _client(cfg, url):
    cfg["base_urls"]["local"] = url
    c = LLMClient(cfg)
    return c


@pytest.mark.parametrize("stream", [True, False])
def test_loop_writes_and_runs(project, mock_llm, stream):
    tmp, cfg, app = project
    cfg["stream"] = stream
    with mock_llm() as m:
        client = _client(cfg, m.url)
        perms = Permissions(cfg, app.ui)
        history = [{"role": "user", "content": "make hello"}]
        deltas = []
        app.ui.text_delta = lambda s: deltas.append(s)
        final = run_agent(client, perms, "SYS", history, ui=app.ui)
    assert (tmp / "hello.txt").read_text(encoding="utf-8") == "hi from chode\n"
    assert final.startswith("Done.")
    tools = [h for h in history if h["role"] == "tool"]
    assert len(tools) == 2 and "hi from chode" in tools[1]["content"]
    assert client.total_in > 0 and client.calls == 3
    assert len(m.requests) == 3 and m.requests[1]["messages"][-1]["role"] == "tool"
    assert str(tmp / "hello.txt") in app.touched_files
    assert app.checkpoints.undo().startswith("deleted")


def test_streaming_fallback_when_server_ignores_stream(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(script=["plain answer"], stream_ok=False) as m:
        client = _client(cfg, m.url)
        got = []
        resp = client.chat("s", [{"role": "user", "content": "q"}], on_text=got.append)
    assert resp["content"] == "plain answer" and got == ["plain answer"]


def test_permissions_lanes(project, mock_llm):
    tmp, cfg, app = project
    perms = Permissions(cfg, app.ui)
    cfg["mode"] = "ask"
    assert perms.decide("read_file", {"path": "x"})[0] == "allow"
    assert perms.decide("bash", {"command": "git status"})[0] == "allow"
    assert perms.decide("bash", {"command": "pytest"})[0] == "prompt"
    assert perms.decide("write_file", {"path": "a.py"})[0] == "prompt"
    cfg["mode"] = "edits"
    assert perms.decide("write_file", {"path": "a.py"})[0] == "allow"
    assert perms.decide("write_file", {"path": "/etc/passwd"})[0] == "prompt"
    cfg["mode"] = "yolo"
    assert perms.decide("bash", {"command": "rm -rf /"})[0] == "prompt"  # danger always prompts
    cfg["bash_deny"] = ["npm publish"]
    assert perms.decide("bash", {"command": "npm publish"})[0] == "deny"
    cfg["mode"] = "plan"
    assert perms.decide("bash", {"command": "ls"})[0] == "deny"
    # SilentUI can't answer prompts → denied, and the loop tells the model so
    cfg["mode"] = "ask"
    assert perms.ask("bash", {"command": "pytest"}) is False
    cfg["mode"] = "yolo"
    with mock_llm(script=[{"content": "", "tool_calls": [{"name": "bash", "arguments": {"command": "rm -rf /"}}]}, "ok"]) as m:
        client = _client(cfg, m.url)
        history = [{"role": "user", "content": "nuke it"}]
        run_agent(client, perms, "SYS", history, ui=app.ui)
    tool_msg = next(h for h in history if h["role"] == "tool")
    assert "denied" in tool_msg["content"]
    assert any(e["event"] == "danger_denied" for e in app.session_events)


def test_unknown_tool_and_redaction(project, mock_llm):
    tmp, cfg, app = project
    (tmp / "env.txt").write_text("TOKEN=ghp_" + "a" * 30 + "\n", encoding="utf-8")
    script = [{"content": "", "tool_calls": [{"name": "nope_tool", "arguments": {}}, {"name": "read_file", "arguments": {"path": "env.txt"}}]}, "fin"]
    with mock_llm(script=script) as m:
        client = _client(cfg, m.url)
        history = [{"role": "user", "content": "go"}]
        run_agent(client, perms := Permissions(cfg, app.ui), "SYS", history, ui=app.ui)
    tools = [h for h in history if h["role"] == "tool"]
    assert "unknown tool" in tools[0]["content"]
    assert "[REDACTED-SECRET]" in tools[1]["content"] and "ghp_" not in tools[1]["content"]


def test_memory_tools_and_subagent(project, mock_llm):
    tmp, cfg, app = project
    script = [
        {"content": "", "tool_calls": [{"name": "remember", "arguments": {"text": "Project uses pytest", "kind": "fact"}}]},
        {"content": "", "tool_calls": [{"name": "recall", "arguments": {"query": "pytest"}}]},
        {"content": "", "tool_calls": [{"name": "spawn_agent", "arguments": {"task": "count files", "read_only": True}}]},
        # sub-agent turn(s):
        {"content": "", "tool_calls": [{"name": "list_dir", "arguments": {}}]},
        "sub report: 1 file",
        "all done",
    ]
    with mock_llm(script=script) as m:
        client = _client(cfg, m.url)
        app.client = client
        app.perms = Permissions(cfg, app.ui)
        history = [{"role": "user", "content": "go"}]
        final = run_agent(client, app.perms, "SYS", history, ui=app.ui)
    tools = [h for h in history if h["role"] == "tool"]
    assert tools[0]["content"].startswith("Remembered")
    assert "Project uses pytest" in tools[1]["content"]
    assert "sub report" in tools[2]["content"]
    assert final == "all done"
    assert any(e["text"] == "Project uses pytest" for e in app.memory_store().all())


def test_system_prompt_includes_everything(project):
    tmp, cfg, app = project
    (tmp / "CHODE.md").write_text("# rules\nnever use tabs\n", encoding="utf-8")
    app.memory_store().add("Deploys happen on Fridays", kind="fact")
    client = LLMClient(cfg)
    sp = build_system_prompt(client, cfg, user_hint="deploy")
    assert "never use tabs" in sp and "Deploys happen on Fridays" in sp
    assert "conscience" in sp and "ORDER" in sp and "search_codebase" in sp
    cfg["mode"] = "plan"
    assert "PLAN MODE" in build_system_prompt(client, cfg)


def test_compact_and_oneshot(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(script=["SUMMARY OF EVERYTHING", "pong"]) as m:
        client = _client(cfg, m.url)
        history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b", "tool_calls": []}]
        compact_history(client, "SYS", history, app.ui)
        assert len(history) == 2 and "SUMMARY OF EVERYTHING" in history[0]["content"]
        assert oneshot_ask(client, "ping") == "pong"
        assert cfg["max_tokens"] == 8192


def test_llm_errors(project, mock_llm):
    tmp, cfg, app = project
    cfg["base_urls"]["local"] = "http://127.0.0.1:1"
    with pytest.raises(LLMError):
        LLMClient(cfg).chat("s", [{"role": "user", "content": "x"}])


def test_render_diff(project):
    tmp, cfg, app = project
    (tmp / "f.txt").write_text("a\nb\nc\n", encoding="utf-8")
    d = render_diff("edit_file", {"path": "f.txt", "old_str": "b", "new_str": "B"})
    assert "-b" in d and "+B" in d
    assert render_diff("edit_file", {"path": "f.txt", "old_str": "zzz", "new_str": ""}) == ""
    assert "+new" in render_diff("write_file", {"path": "new.txt", "content": "new\n"})
