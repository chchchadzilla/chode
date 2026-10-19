"""Request-parameter self-healing: retired params get dropped, retried and remembered per model."""
import json

from chode.config import CONFIG_FILE
from chode.llm import LLMClient


def test_anthropic_sampling_gate():
    ok = LLMClient._anthropic_accepts_sampling
    assert ok("claude-3-5-haiku-latest") and ok("claude-sonnet-4-5-20250929") and ok("claude-opus-4-6") and ok("claude-sonnet-4-20250514")
    assert not ok("claude-sonnet-5-5") and not ok("claude-opus-5") and not ok("claude-opus-4-7") and not ok("claude-opus-4-8")
    assert not ok("claude-fable-5-1") and not ok("claude-haiku-5-5")


def test_anthropic_payload_has_no_temperature_for_new_models(project):
    tmp, cfg, app = project
    cfg["provider"] = "anthropic"
    cfg["api_keys"] = {"anthropic": "sk-ant-test"}
    captured = {}

    class R:
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"content": [{"type": "text", "text": "pong"}], "usage": {"input_tokens": 3, "output_tokens": 1}}

    def fake_post(url, headers, payload, stream=False):
        captured["payload"] = json.loads(json.dumps(payload))
        return R()
    for model, expect_temp in (("claude-sonnet-5-5", False), ("claude-sonnet-4-5-20250929", True)):
        cfg["model"] = model
        client = LLMClient(cfg)
        client._post = fake_post
        assert client.chat("s", [{"role": "user", "content": "ping"}])["content"] == "pong"
        assert ("temperature" in captured["payload"]) is expect_temp, model
        assert "max_tokens" in captured["payload"] and captured["payload"]["model"] == model


def test_rejected_param_is_dropped_retried_and_remembered(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(script=["healed", "still fine"], reject_params={"temperature": "`temperature` is deprecated for this model."}) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["model"] = "mock-1"
        client = LLMClient(cfg)
        notes = []
        client.on_fallback = notes.append
        assert client.chat("s", [{"role": "user", "content": "q"}])["content"] == "healed"
        assert len(m.requests) == 2 and "temperature" in m.requests[0] and "temperature" not in m.requests[1]
        assert any("rejected `temperature`" in n for n in notes)
        assert cfg["param_quirks"]["mock-1"] == ["temperature"]
        assert json.loads(CONFIG_FILE.read_text(encoding="utf-8"))["param_quirks"]["mock-1"] == ["temperature"]
        # a fresh client on the same model never sends it again — one request, no 400
        from chode.config import load_config
        cfg2 = load_config(tmp)
        cfg2.update({"provider": "local", "model": "mock-1", "fallbacks": False, "retries": 0})
        cfg2["base_urls"]["local"] = m.url
        assert LLMClient(cfg2).chat("s", [{"role": "user", "content": "q"}])["content"] == "still fine"
        assert len(m.requests) == 3 and "temperature" not in m.requests[2]


def test_max_tokens_is_renamed_not_dropped(project, mock_llm):
    tmp, cfg, app = project
    with mock_llm(script=["ok"], reject_params={"max_tokens": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."}) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["model"] = "mock-reasoner"
        assert LLMClient(cfg).chat("s", [{"role": "user", "content": "q"}])["content"] == "ok"
        assert "max_tokens" not in m.requests[1] and m.requests[1]["max_completion_tokens"] == cfg["max_tokens"]


def test_unrelated_400_is_not_mangled(project, mock_llm):
    tmp, cfg, app = project
    import pytest
    from chode.llm import LLMError
    with mock_llm(fail_with=[400]) as m:  # generic "error" body, names no parameter
        cfg["base_urls"]["local"] = m.url
        with pytest.raises(LLMError) as ei:
            LLMClient(cfg).chat("s", [{"role": "user", "content": "q"}])
        assert ei.value.status == 400 and len(m.requests) == 1


# ---- model names: what humans type vs what the API wants ---------------------------------

def test_normalize_model_names():
    from chode.config import normalize_model, load_config
    n = normalize_model
    assert n("anthropic", "anthropic/opus-5.5") == "claude-opus-5-5"
    assert n("anthropic", "Opus 5.5") == "claude-opus-5-5"
    assert n("anthropic", "claude-sonnet-4-5-20250929") == "claude-sonnet-4-5-20250929"
    assert n("anthropic", "sonnet") == "sonnet"                      # alias → resolved by resolve_model / the live list
    assert n("openai", "gpt5 mini") == "gpt-5-mini"
    assert n("openai", "openai/gpt-5") == "gpt-5"
    assert n("gemini", "models/gemini-2.5-flash") == "gemini-2.5-flash"
    assert n("xai", "Grok 4") == "grok-4"
    assert n("openrouter", "qwen/qwen3-coder:free") == "qwen/qwen3-coder:free"     # openrouter ids ARE vendor/model
    assert n("ollama", "Qwen2.5-Coder:7b") == "qwen2.5-coder:7b"
    assert n("anthropic", "") == ""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"provider": "anthropic", "model": "anthropic/opus-5.5", "temperature": 0.9}), encoding="utf-8")
    cfg = load_config()
    assert cfg["model"] == "claude-opus-5-5"            # a saved mistake is fixed on load
    assert cfg["sampling"]["temperature"] == 0.9         # legacy top-level temperature feeds sampling


def test_verify_model_against_live_list(project, mock_llm):
    from chode import lifeline
    tmp, cfg, app = project
    with mock_llm(models=["mock-1", "mock-2"]) as m:
        cfg["base_urls"]["local"] = m.url
        assert lifeline.verify_model(cfg, "Mock 1") == ("mock-1", "'Mock 1' → 'mock-1'", True)
        assert lifeline.verify_model(cfg, "mock-1") == ("mock-1", None, True)
        new, note, verified = lifeline.verify_model(cfg, "mock-l")
        assert new in ("mock-1", "mock-2") and verified and "isn't a model local knows" in note
        new, note, verified = lifeline.verify_model(cfg, "zzz-totally-different", available=["alpha-9", "beta-9"])
        assert not verified and new == "zzz-totally-different" and "isn't on local's model list" in note   # no wild guesses
    cfg["base_urls"]["local"] = "http://127.0.0.1:1/v1"           # nothing listening → can't verify, say so, don't break
    new, note, verified = lifeline.verify_model(cfg, "mock-1")
    assert new == "mock-1" and not verified and "auto-correct" in note


def test_slash_model_and_provider_verify_names(project, mock_llm, capsys):
    from chode.commands import handle_slash
    from chode.repl import Repl
    tmp, cfg, app = project
    with mock_llm(models=["mock-1", "mock-2"]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["base_urls"]["lmstudio"] = m.url
        repl = Repl(cfg, ui=app.ui)
        handle_slash("/model Mock 1", repl)
        assert cfg["model"] == "mock-1"
        assert json.loads(CONFIG_FILE.read_text(encoding="utf-8"))["model"] == "mock-1"
        handle_slash("/provider lmstudio mock-l", repl)
        assert cfg["provider"] == "lmstudio" and cfg["model"] in ("mock-1", "mock-2")
        out = capsys.readouterr().out
        assert "'Mock 1' → 'mock-1'" in out and "isn't a model lmstudio knows" in out


def test_set_config_tool_normalizes_and_verifies_model(project, mock_llm):
    from chode.tools import tool_set_config
    tmp, cfg, app = project
    with mock_llm(models=["mock-1", "mock-2"]) as m:
        cfg["base_urls"]["local"] = m.url
        out = tool_set_config({"key": "model", "value": "Mock 1"})
        assert "mock-1" in out and cfg["model"] == "mock-1"
        assert tool_set_config({"key": "sampling.temperature", "value": "0.5"}).startswith("Set") and cfg["sampling"]["temperature"] == 0.5


# ---- sampling: global · per provider · per model, remembered per model ------------------------

def test_sampling_overrides_reach_the_payload(project, mock_llm):
    from chode import sampling
    tmp, cfg, app = project
    with mock_llm(script=["a", "b", "c", "d"]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["model"] = "mock-1"
        client = LLMClient(cfg)
        client.chat("s", [{"role": "user", "content": "q"}])
        assert m.requests[0]["temperature"] == 0.2 and "top_k" not in m.requests[0]          # defaults: temp on, top_k off
        assert "top_k = 40 for local" in sampling.set_value(cfg, "provider", "top_k", 40)
        client.chat("s", [{"role": "user", "content": "q"}])
        assert m.requests[1]["top_k"] == 40
        sampling.set_value(cfg, "model", "temperature", 0.9)                                  # local/mock-1 only
        sampling.set_value(cfg, "global", "top_p", None)
        client.chat("s", [{"role": "user", "content": "q"}])
        assert m.requests[2]["temperature"] == 0.9 and m.requests[2]["top_k"] == 40 and "top_p" not in m.requests[2]
        cfg["model"] = "mock-2"                                                                 # other model: provider override, global temp
        client.chat("s", [{"role": "user", "content": "q"}])
        assert m.requests[3]["temperature"] == 0.2 and m.requests[3]["top_k"] == 40
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))["sampling"]
        assert saved["overrides"]["local"]["top_k"] == 40 and saved["overrides"]["local/mock-1"]["temperature"] == 0.9
        rows = {r[0]: r for r in sampling.effective(cfg, client)}
        assert rows["temperature"][2] == "default" and rows["top_k"][2] == "provider local" and rows["top_p"][1] is None
        assert "removed overrides for local" in sampling.reset(cfg, "provider")
        assert "local" not in cfg["sampling"]["overrides"] and "local/mock-1" in cfg["sampling"]["overrides"]


def test_explicit_model_override_bypasses_anthropic_gate(project):
    """Claude 5.x normally gets no temperature. A per-model override means 'I know, send it anyway'
    (and the self-healing path drops it if Anthropic still refuses)."""
    from chode import sampling
    tmp, cfg, app = project
    cfg["provider"] = "anthropic"
    cfg["api_keys"] = {"anthropic": "sk-ant-test"}
    cfg["model"] = "claude-sonnet-5-5"
    captured = {}

    class R:
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"content": [{"type": "text", "text": "pong"}], "usage": {"input_tokens": 1, "output_tokens": 1}}

    def fake_post(url, headers, payload, stream=False):
        captured["payload"] = dict(payload)
        return R()
    client = LLMClient(cfg)
    client._post = fake_post
    assert client.sampling_gate() and "Claude 4.7+/5.x" in client.sampling_gate()
    client.chat("s", [{"role": "user", "content": "ping"}])
    assert "temperature" not in captured["payload"]
    sampling.set_value(cfg, "model", "temperature", 0.5)
    assert client.sampling_gate() is None
    client.chat("s", [{"role": "user", "content": "ping"}])
    assert captured["payload"]["temperature"] == 0.5


def test_sampling_command_and_quirk_forgetting(project, mock_llm):
    from chode import sampling
    from chode.commands import handle_slash
    from chode.repl import Repl
    tmp, cfg, app = project
    with mock_llm(script=["x"]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["model"] = "mock-1"
        repl = Repl(cfg, ui=app.ui)
        assert "temperature = 0.7 everywhere" in sampling.handle(cfg, repl.client, ["temperature", "0.7"])
        assert cfg["sampling"]["temperature"] == 0.7
        assert "needs a number" in sampling.handle(cfg, repl.client, ["top_p", "hot"])
        assert "between" in sampling.handle(cfg, repl.client, ["top_p", "7"])
        assert "unknown setting" in sampling.handle(cfg, repl.client, ["topk", "7"])
        assert "default (provider decides) everywhere" in sampling.handle(cfg, repl.client, ["temperature", "default"])
        handle_slash("/sampling top_k 20 model", repl)
        assert cfg["sampling"]["overrides"]["local/mock-1"]["top_k"] == 20
        view = sampling.describe(cfg, repl.client)
        assert "top_k" in view and "model local/mock-1" in view
        # a remembered rejection is dropped — until the user asks for that param on that model explicitly
        cfg["param_quirks"] = {"mock-1": ["top_k", "top_p"]}
        rows = {r[0]: r for r in sampling.effective(cfg, repl.client)}
        assert not rows["top_k"][3] and "rejected it before" in rows["top_k"][4]
        sampling.set_value(cfg, "model", "top_k", 30)
        assert cfg["param_quirks"]["mock-1"] == ["top_p"]
        assert "forgot top_p for mock-1" in sampling.forget_quirks(cfg, "mock-1")
        assert "mock-1" not in cfg["param_quirks"]
