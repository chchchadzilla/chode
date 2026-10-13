import io
import json

from chode.config import (DEFAULT_CONFIG, PROVIDERS, api_key_for, load_config, price_for, resolve_model, save_config,
                          save_project_config, set_config_path)
from chode.paths import CONFIG_FILE
from chode.ui import StreamRenderer, style_line


def test_load_save_roundtrip(project, monkeypatch):
    tmp, cfg, app = project
    cfg["theme"] = "cyan"
    cfg["memory"]["inject"] = 5
    save_config(cfg)
    saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    assert saved["theme"] == "cyan" and saved["memory"]["inject"] == 5 and "_project_keys" not in saved
    again = load_config(tmp)
    assert again["theme"] == "cyan" and again["memory"]["inject"] == 5
    assert again["memory"]["max_entries"] == 2000  # untouched defaults survive the deep merge


def test_project_overlays(project):
    tmp, cfg, app = project
    save_project_config(tmp, {"mode": "edits"})
    (tmp / ".chode" / "mcp.json").write_text(json.dumps({"mcpServers": {"proj": {"command": "x"}}}), encoding="utf-8")
    (tmp / ".chode" / "permissions.json").write_text(json.dumps({"allow": ["make test"], "deny": ["rm -rf"]}), encoding="utf-8")
    c = load_config(tmp)
    assert c["mode"] == "edits" and "proj" in c["mcp_servers"] and "make test" in c["bash_allow"] and "rm -rf" in c["bash_deny"]
    save_config(c)
    saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    assert "proj" not in saved.get("mcp_servers", {}) and "make test" not in saved.get("bash_allow", [])


def test_set_config_path_types():
    cfg = {}
    set_config_path(cfg, "a.b", "true")
    set_config_path(cfg, "n", "42")
    set_config_path(cfg, "f", "1.5")
    set_config_path(cfg, "l", '["x","y"]')
    set_config_path(cfg, "s", "hello")
    assert cfg == {"a": {"b": True}, "n": 42, "f": 1.5, "l": ["x", "y"], "s": "hello"}


def test_prices_and_aliases():
    assert price_for("claude-opus-4-5-20251101") == (5.0, 25.0)
    assert price_for("anthropic/claude-sonnet-4-5") == (3.0, 15.0)
    assert price_for("gpt-5-mini-2025") == (0.25, 2.0)
    assert price_for("totally-unknown") is None
    assert resolve_model({"provider": "anthropic", "model": "opus"}) == "claude-opus-5-5"
    assert resolve_model({"provider": "openai", "model": ""}) == PROVIDERS["openai"][3]
    assert api_key_for({"provider": "ollama", "api_keys": {}}) == ""


def test_style_and_stream_renderer():
    assert style_line("```py", False) == "```py"  # NO_COLOR → unchanged
    out = io.StringIO()
    r = StreamRenderer(out=out, first_prefix="> ")
    r.feed("hello ")
    r.feed("world\n# Title\n")
    r.feed("```\ncode\n```\ntail")
    text = r.finish()
    assert text == "hello world\n# Title\n```\ncode\n```\ntail"
    assert out.getvalue().startswith("\n> hello world\n")
    assert "tail\n" in out.getvalue()
