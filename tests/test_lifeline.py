"""The lifeline: classification, retries, model auto-correct, fallback ladder, the fixer."""
import json

import pytest

from chode import lifeline
from chode.config import CONFIG_FILE
from chode.llm import LLMClient, LLMError


def test_classify_and_hints():
    assert lifeline.classify(401, "") == "auth"
    assert lifeline.classify(404, "") == "not_found"
    assert lifeline.classify(400, '{"error":{"message":"The model `x` does not exist"}}') == "not_found"
    assert lifeline.classify(429, "") == "rate_limit"
    assert lifeline.classify(400, "insufficient_quota") == "rate_limit"
    assert lifeline.classify(503, "") == "overloaded"
    assert lifeline.classify(400, "bad schema") == "bad_request"
    assert lifeline.classify(None, "", exc=OSError()) == "network"
    assert "ANTHROPIC_API_KEY" in lifeline.hint("auth", "anthropic")
    assert "ollama serve" in lifeline.hint("network", "ollama")
    assert "aistudio" in lifeline.hint("rate_limit", "gemini")


def test_model_correction():
    avail = ["claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805", "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"]
    assert lifeline.resolve_alias("sonnet", avail) == "claude-sonnet-4-5-20250929"
    assert lifeline.correct_model("claude-sonnet-5-5", avail, "anthropic") == "claude-sonnet-4-5-20250929"
    assert lifeline.correct_model("sonnet", avail, "anthropic") == "claude-sonnet-4-5-20250929"
    assert lifeline.correct_model("CLAUDE-OPUS-4-1-20250805", avail, "anthropic") == "claude-opus-4-1-20250805"
    assert lifeline.correct_model("gpt-4o", ["gpt-4o-mini", "gpt-4.1"], "openai") in ("gpt-4o-mini", "gpt-4.1")
    assert lifeline.correct_model("totally-unrelated", ["llama-3.3-70b-versatile"], "groq") == "llama-3.3-70b-versatile"
    assert lifeline.correct_model("x", [], "openai") is None
    assert lifeline.pick_ollama_model(["nomic-embed-text", "llama3.2:3b", "qwen2.5-coder:7b"]) == "qwen2.5-coder:7b"


def test_retries_then_success(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(script=["ok after retries"], fail_with=[503, 429], retry_after=0) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["retries"] = 3
        client = LLMClient(cfg)
        assert client.chat("s", [{"role": "user", "content": "q"}])["content"] == "ok after retries"
        assert len(m.requests) == 3


def test_auth_error_is_not_retried_and_is_classified(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(fail_with=[401]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["retries"] = 3
        with pytest.raises(LLMError) as ei:
            LLMClient(cfg).chat("s", [{"role": "user", "content": "q"}])
        assert ei.value.kind == "auth" and len(m.requests) == 1 and ei.value.hint


def test_model_autocorrect_from_live_list(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(script=["corrected!"], valid_models={"mock-1", "mock-2"}, models=["mock-1", "mock-2"]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["model"] = "mock-l"           # typo → 404 → corrected against GET /models
        cfg["fallbacks"] = []             # ladder empty, but autocorrect still runs
        client = LLMClient(cfg)
        notes = []
        client.on_fallback = notes.append
        assert client.chat("s", [{"role": "user", "content": "q"}])["content"] == "corrected!"
        assert cfg["model"] in ("mock-1", "mock-2") and "mock-l" in notes[0]


def test_provider_fallback_ladder(project, mock_llm):
    """local (dead key → 401) → lmstudio (mock #2) answers. Session-only switch; config stays on `local`."""
    tmp, cfg, app = project
    with mock_llm(fail_with=[401, 401, 401]) as bad, mock_llm(script=["hello from the fallback"]) as good:
        cfg["base_urls"]["local"] = bad.url
        cfg["base_urls"]["lmstudio"] = good.url
        cfg["fallbacks"] = ["lmstudio"]
        client = LLMClient(cfg)
        notes = []
        client.on_fallback = notes.append
        out = client.chat("s", [{"role": "user", "content": "q"}])
        assert out["content"] == "hello from the fallback"
        assert client.provider == "lmstudio" and client.switched_from == ("local", "")
        assert any("falling back to lmstudio" in n for n in notes)
        from chode.config import save_config, load_config
        save_config(cfg)
        assert load_config(tmp)["provider"] == "local"        # a session fallback never becomes the default silently
        assert json.loads(CONFIG_FILE.read_text(encoding="utf-8"))["last_known_good"]["provider"] == "lmstudio"


def test_fallbacks_off_raises(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(fail_with=[503, 503, 503, 503]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["fallbacks"] = False
        cfg["retries"] = 1
        with pytest.raises(LLMError) as ei:
            LLMClient(cfg).chat("s", [{"role": "user", "content": "q"}])
        assert ei.value.kind == "overloaded"


def test_ladder_and_ensure_usable(project, mock_llm, monkeypatch):
    tmp, cfg, app = project
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with mock_llm(models=["qwen2.5-coder:7b"]) as m:
        cfg["base_urls"]["ollama"] = m.url
        cfg["base_urls"]["lmstudio"] = "http://127.0.0.1:1/v1"
        cfg["base_urls"]["local"] = "http://127.0.0.1:1/v1"
        cfg["fallbacks"] = ["ollama", "pollinations"]
        cfg["provider"] = "anthropic"
        cfg["api_keys"] = {}
        assert not lifeline.usable(cfg, "anthropic")
        lad = lifeline.ladder(cfg)
        assert lad[0] == ("ollama", "qwen2.5-coder:7b") and lad[1][0] == "pollinations"
        notes = []
        note = lifeline.ensure_usable(cfg, notify=lambda m_, lvl="warn": notes.append(m_))
        assert cfg["provider"] == "ollama" and cfg["model"] == "qwen2.5-coder:7b" and cfg["_fallback_from"] == "anthropic"
        assert "no API key" in note and notes
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        cfg["provider"] = "anthropic"
        assert lifeline.ensure_usable(cfg) is None
        rows = dict((p, ok) for p, ok, _ in lifeline.status(cfg))
        assert rows["anthropic"] and rows["ollama"] and rows["pollinations"] and not rows["lmstudio"]


def test_fixer_repairs_config(project, mock_llm):
    """The fixer agent (running on the working rung) lists models and sets a valid one."""
    tmp, cfg, app = project
    script = [
        "pong",  # probe
        {"content": "", "tool_calls": [{"name": "list_models", "arguments": {"provider": "local"}}]},
        {"content": "", "tool_calls": [{"name": "set_config", "arguments": {"key": "model", "value": "mock-2"}}]},
        {"content": "", "tool_calls": [{"name": "test_connection", "arguments": {}}]},
        "pong",  # the test_connection probe
        "Fixed: local / mock-2 works now.",
    ]
    with mock_llm(script=script, models=["mock-1", "mock-2"]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["model"] = "nonsense"
        cfg["fallbacks"] = ["local"]
        out = lifeline.run_fixer(cfg, error=LLMError("HTTP 404", kind="not_found", provider="local", model="nonsense",
                                                     hint=lifeline.hint("not_found", "local", "nonsense")), ui=app.ui)
        assert "Fixed" in out
        assert cfg["model"] == "mock-2"
        assert json.loads(CONFIG_FILE.read_text(encoding="utf-8"))["model"] == "mock-2"


def test_set_config_tool_refuses_keys(project):
    from chode.tools import tool_set_config, tool_list_models
    tmp, cfg, app = project
    assert tool_set_config({"key": "api_keys.openai", "value": "sk-x"}).startswith("Refused")
    assert tool_set_config({"key": "bash_allow", "value": "rm"}).startswith("Refused")
    assert tool_set_config({"key": "provider", "value": "nope"}).startswith("Error")
    assert tool_set_config({"key": "provider", "value": "ollama"}).startswith("Set") and cfg["provider"] == "ollama"
    assert tool_list_models({"provider": "nope"}).startswith("Error")


def test_playbook_mentions_free_paths(project):
    tmp, cfg, app = project
    text = lifeline.playbook(cfg, LLMError("x", kind="auth", provider="local", hint="bad key"))
    assert "pollinations" in text and "ollama" in text and "chode fix" in text and "bad key" in text
