"""Providers, pricing, defaults, and config load/save.

Config precedence (last wins):  defaults → ~/.chode/config.json → ./.chode/config.json
Project files that also merge in: ./.chode/mcp.json (MCP servers) and
./.chode/permissions.json ({"allow": [...], "deny": [...]} bash prefixes).
"""
import json
from pathlib import Path

from .paths import CONFIG_DIR, CONFIG_FILE, PROJECT_DIRNAME
from .security import secure_file
from .ui import yellow

# name: (api_style, default_base_url, api_key_env, default_model)
PROVIDERS = {
    "anthropic":  ("anthropic", "https://api.anthropic.com",     "ANTHROPIC_API_KEY",  "claude-sonnet-5-5"),
    "openai":     ("openai",    "https://api.openai.com/v1",     "OPENAI_API_KEY",     "gpt-5"),
    "xai":        ("openai",    "https://api.x.ai/v1",           "XAI_API_KEY",        "grok-4"),
    "openrouter": ("openai",    "https://openrouter.ai/api/v1",  "OPENROUTER_API_KEY", "qwen/qwen3-coder:free"),
    "gemini":     ("openai",    "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-2.5-flash"),
    "groq":       ("openai",    "https://api.groq.com/openai/v1", "GROQ_API_KEY",      "llama-3.3-70b-versatile"),
    "mistral":    ("openai",    "https://api.mistral.ai/v1",     "MISTRAL_API_KEY",    "devstral-medium-latest"),
    "deepseek":   ("openai",    "https://api.deepseek.com/v1",   "DEEPSEEK_API_KEY",   "deepseek-chat"),
    "together":   ("openai",    "https://api.together.xyz/v1",   "TOGETHER_API_KEY",   "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "cerebras":   ("openai",    "https://api.cerebras.ai/v1",    "CEREBRAS_API_KEY",   "llama-3.3-70b"),
    "moonshot":   ("openai",    "https://api.moonshot.ai/v1",    "MOONSHOT_API_KEY",   "kimi-k2-0905-preview"),
    "perplexity": ("openai",    "https://api.perplexity.ai",     "PERPLEXITY_API_KEY", "sonar"),
    "azure":      ("azure",     "",                              "AZURE_OPENAI_API_KEY", ""),
    "huggingface": ("openai",   "https://router.huggingface.co/v1", "HF_TOKEN",        "Qwen/Qwen2.5-Coder-32B-Instruct"),
    "ollama":     ("openai",    "http://localhost:11434/v1",     "",                   "qwen3-coder"),
    "lmstudio":   ("openai",    "http://localhost:1234/v1",      "",                   ""),
    "local":      ("openai",    "http://localhost:8080/v1",      "",                   ""),
    # ---- keyless, free, community-run — the last rung of the lifeline ladder ----
    "pollinations": ("openai",  "https://text.pollinations.ai/openai", "",             "openai"),
    # ---- Plan Bridge: ride the subscription you already pay for (no API key) ----
    "claude-plan": ("plan", "", "", "sonnet"),
    "codex-plan":  ("plan", "", "", ""),
    "gemini-plan": ("plan", "", "", ""),
    "custom-plan": ("plan", "", "", ""),
}

PROVIDER_NOTES = {
    "anthropic":  "Claude models · ANTHROPIC_API_KEY",
    "openai":     "GPT models · OPENAI_API_KEY",
    "xai":        "Grok models · XAI_API_KEY",
    "openrouter": "hundreds of models incl. FREE ones · OPENROUTER_API_KEY",
    "gemini":     "Google Gemini · GEMINI_API_KEY",
    "groq":       "ultra-fast open models · GROQ_API_KEY",
    "mistral":    "Mistral / Devstral · MISTRAL_API_KEY",
    "deepseek":   "DeepSeek V3/R1, very cheap · DEEPSEEK_API_KEY",
    "together":   "big open-model catalog · TOGETHER_API_KEY",
    "cerebras":   "fastest inference on earth · CEREBRAS_API_KEY",
    "moonshot":   "Kimi K2 · MOONSHOT_API_KEY",
    "perplexity": "Sonar (search-grounded) · PERPLEXITY_API_KEY",
    "azure":      "Azure OpenAI · AZURE_OPENAI_API_KEY + deployment URL",
    "huggingface": "Hugging Face Inference (free tier) · HF_TOKEN",
    "ollama":     "local, no key, FREE — ollama serve on :11434",
    "lmstudio":   "local, no key, FREE — LM Studio server on :1234",
    "local":      "any OpenAI-compatible server (llama.cpp, vLLM, LiteLLM, Jan, Kobold…)",
    "pollinations": "FREE, no key, no signup — community-run, rate-limited, best effort",
    "claude-plan": "your Claude Pro/Max plan via the `claude` CLI — no API key",
    "codex-plan":  "your ChatGPT Plus/Pro plan via the `codex` CLI — no API key",
    "gemini-plan": "your Google AI Pro/Ultra plan via the `gemini` CLI — no API key",
    "custom-plan": "any other agent CLI (configure a command template)",
}

# Aliases accepted by /model for the anthropic provider. When the API can list models, the alias
# resolves to the NEWEST matching id at runtime (see lifeline.resolve_alias); these are the fallbacks.
MODEL_ALIASES = {
    "anthropic": {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5",
                  "haiku": "claude-haiku-5-5", "fable": "claude-fable-5-1"},
}

# If the configured model 404s, these are tried in order before giving up on the provider.
MODEL_FALLBACKS = {
    "anthropic": ["claude-sonnet-5-5", "claude-sonnet-4-5", "claude-sonnet-4-5-20250929", "claude-sonnet-4-20250514",
                  "claude-3-5-sonnet-latest"],
    "openai": ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "xai": ["grok-4", "grok-3", "grok-3-mini"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3-32b"],
    "openrouter": ["qwen/qwen3-coder:free", "meta-llama/llama-3.3-70b-instruct:free", "openrouter/auto"],
    "mistral": ["devstral-medium-latest", "mistral-small-latest", "mistral-large-latest"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "cerebras": ["llama-3.3-70b", "qwen-3-32b"],
    "ollama": ["qwen3-coder", "qwen2.5-coder:7b", "qwen3:8b", "qwen3:4b", "llama3.2:3b"],
    "pollinations": ["openai", "openai-large", "mistral"],
}

# Free tiers you can sign up for in about two minutes, no card. (Limits change; links are the source of truth.)
FREE_TIERS = {
    "gemini":     {"signup": "https://aistudio.google.com/apikey", "model": "gemini-2.5-flash",
                   "note": "generous free tier, strong tool calling"},
    "groq":       {"signup": "https://console.groq.com/keys", "model": "llama-3.3-70b-versatile",
                   "note": "very fast, free tier with daily limits"},
    "openrouter": {"signup": "https://openrouter.ai/keys", "model": "qwen/qwen3-coder:free",
                   "note": "many ':free' models, some with tool calling"},
    "mistral":    {"signup": "https://console.mistral.ai/api-keys", "model": "mistral-small-latest",
                   "note": "free 'experiment' tier"},
    "cerebras":   {"signup": "https://cloud.cerebras.ai", "model": "llama-3.3-70b",
                   "note": "fastest inference, free tier"},
    "huggingface": {"signup": "https://huggingface.co/settings/tokens", "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                    "note": "free monthly credits"},
}
KEYLESS = ("ollama", "lmstudio", "local", "pollinations")

MODES = ("plan", "ask", "edits", "yolo")
MODE_ICONS = {"plan": "🔍", "ask": "🛡", "edits": "✏️", "yolo": "🔥"}
MODE_NOTES = {"plan": "read-only — CHODE can look but not touch",
              "ask": "prompt before every write/command (recommended)",
              "edits": "auto-approve file edits, still ask for shell",
              "yolo": "auto-approve everything except dangerous commands"}

DEFAULT_CONFIG = {
    "provider": "anthropic",
    "model": "",
    "max_tokens": 8192,
    "temperature": 0.2,
    "stream": True,
    "base_urls": {},
    "api_keys": {},
    "mode": "ask",                  # plan | ask | edits | yolo
    "bash_allow": ["git status", "git diff", "git log", "git branch", "ls", "pwd", "cat",
                   "echo", "which", "python --version", "python3 --version", "node --version"],
    "bash_deny": [],                # prefixes that are ALWAYS refused (project permissions.json adds more)
    "redact_secrets": True,         # scrub API-key-looking strings from tool output
    "allow_outside_cwd": False,     # writes outside the working dir always prompt
    "allow_private_urls": True,     # web_fetch may hit localhost / LAN (cloud metadata is always blocked)
    "auto_compact_tokens": 120000,  # auto-summarize history past this context size (0 = off)
    "mcp_servers": {},
    "hooks": {},                    # {"pre_tool": [{"match": "bash", "command": "..."}], ...}
    "name": "",
    "theme": "magenta",
    "shell": "auto",                # windows: auto|powershell|cmd
    "azure_api_version": "2024-06-01",
    "intro": True,
    "skip_menu": False,
    "memory": {"auto_reflect": True, "inject": 12, "max_entries": 2000},
    "conscience": {"reflect": True},
    "order": {"auto_check": True, "auto_backup_hours": 24, "backup_keep": 10, "backup_max_mb": 200,
              "auto_about": True},
    "rag": {"auto_index": True, "embeddings": False, "embedding_model": "", "max_files": 4000},
    "publish": {"autocommit": "off", "remote": "origin", "huggingface_repo": "", "sign_off": ""},
    "plans": {
        # {prompt}, {model}, {mcp_config}, {resume} are filled in by chode. {resume} expands to
        # the resume flag + id when a session id is known (see plans.py).
        "claude": {"command": "claude -p {prompt} --output-format json --tools \"\" --strict-mcp-config "
                              "--mcp-config {mcp_config} --allowedTools mcp__chode__* {model} {resume}",
                   "model_flag": "--model {model}", "resume_flag": "--resume {id}"},
        "codex":  {"command": "codex exec --json --skip-git-repo-check {model} {prompt}",
                   "model_flag": "-m {model}", "resume_flag": ""},
        "gemini": {"command": "gemini -p {prompt} --output-format json {model} {resume}",
                   "model_flag": "-m {model}", "resume_flag": "--resume {id}"},
        "custom": {"command": "", "model_flag": "", "resume_flag": ""},
    },
    "gui": {"port": 7331, "open_browser": True},
    "banner": {"image_provider": "auto"},
    "agents": {"subagent_model": "", "max_depth": 2},
    # ---- lifeline: never die on a connection error ----
    "fallbacks": "auto",            # "auto" = any provider with a key → local servers → keyless free; a list of
                                    # "provider" or "provider:model" strings to control the order; false = off
    "retries": 3,                   # network / 429 / 5xx retries per request (exponential backoff)
    "last_known_good": {},          # {"provider": ..., "model": ...} — remembered automatically
}

_NESTED = ("memory", "conscience", "order", "rag", "publish", "plans", "gui", "banner", "agents", "last_known_good")


def _deep_merge(base, override):
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as e:
        print(yellow(f"warning: could not parse {path}: {e}"))
        return None


def load_config(cwd=None):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    user = _read_json(CONFIG_FILE)
    if user:
        _deep_merge(cfg, user)
    cwd = Path(cwd or Path.cwd())
    proj_dir = cwd / PROJECT_DIRNAME
    cfg["_project_keys"] = []
    proj = _read_json(proj_dir / "config.json")
    if proj:
        cfg["_project_keys"] = list(proj.keys())
        _deep_merge(cfg, proj)
    # project-level MCP: .chode/mcp.json merges in (project wins)
    proj_mcp = _read_json(proj_dir / "mcp.json")
    if isinstance(proj_mcp, dict):
        servers = proj_mcp.get("mcpServers", proj_mcp)
        cfg["_project_mcp"] = [k for k in servers if k not in cfg.get("mcp_servers", {})]
        cfg["mcp_servers"] = {**cfg.get("mcp_servers", {}), **servers}
    # project permissions
    perms = _read_json(proj_dir / "permissions.json")
    if isinstance(perms, dict):
        cfg["_project_allow"] = list(perms.get("allow", []))
        cfg["_project_deny"] = list(perms.get("deny", []))
        cfg["bash_allow"] = list(dict.fromkeys(cfg.get("bash_allow", []) + cfg["_project_allow"]))
        cfg["bash_deny"] = list(dict.fromkeys(cfg.get("bash_deny", []) + cfg["_project_deny"]))
    if cfg.get("mode") not in MODES:
        cfg["mode"] = "ask"
    if cfg.get("provider") not in PROVIDERS:
        print(yellow(f"warning: unknown provider '{cfg.get('provider')}' — falling back to anthropic"))
        cfg["provider"] = "anthropic"
    return cfg


def save_config(cfg):
    """Persist user-level config (project-only overlays are stripped back out)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    persisted = {k: v for k, v in cfg.items() if k in DEFAULT_CONFIG}
    if cfg.get("_fallback_from"):
        # a session-only fallback must never silently become the default (see lifeline.py / `/provider keep`)
        persisted["provider"] = cfg["_fallback_from"]
        persisted["model"] = cfg.get("_fallback_model", "")
    proj_only = set(cfg.get("_project_mcp", []))
    if proj_only:
        persisted["mcp_servers"] = {k: v for k, v in persisted.get("mcp_servers", {}).items()
                                    if k not in proj_only}
    for key, proj_key in (("bash_allow", "_project_allow"), ("bash_deny", "_project_deny")):
        extra = set(cfg.get(proj_key, []))
        if extra:
            persisted[key] = [x for x in persisted.get(key, []) if x not in extra]
    for k in cfg.get("_project_keys", []):
        # don't copy project-level overrides into the user config
        if k in persisted and k in DEFAULT_CONFIG and not isinstance(DEFAULT_CONFIG[k], dict):
            persisted[k] = DEFAULT_CONFIG[k] if k not in _user_saved_keys() else persisted[k]
    CONFIG_FILE.write_text(json.dumps(persisted, indent=2), encoding="utf-8")
    secure_file(CONFIG_FILE)


def _user_saved_keys():
    user = _read_json(CONFIG_FILE) or {}
    return set(user.keys())


def save_project_config(cwd, data):
    d = Path(cwd) / PROJECT_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    f = d / "config.json"
    existing = _read_json(f) or {}
    _deep_merge(existing, data)
    f.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return f


def set_config_path(cfg, dotted, value):
    keys = dotted.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    leaf = keys[-1]
    if isinstance(value, str):
        v = value.strip()
        if v.lower() in ("true", "false"):
            node[leaf] = v.lower() == "true"
            return
        if v.startswith(("[", "{")):
            try:
                node[leaf] = json.loads(v)
                return
            except Exception:
                pass
        try:
            node[leaf] = int(v)
        except ValueError:
            try:
                node[leaf] = float(v)
            except ValueError:
                node[leaf] = v
    else:
        node[leaf] = value


# USD per million tokens (input, output). Estimates — check your provider's page.
PRICES = {
    "claude-opus-4-5":   (5.0, 25.0),
    "claude-opus-4-1":   (15.0, 75.0),
    "claude-opus-4":     (15.0, 75.0),
    "claude-sonnet-4":   (3.0, 15.0),
    "claude-haiku-4":    (1.0, 5.0),
    "claude-3-5-haiku":  (0.8, 4.0),
    "gpt-5-nano":        (0.05, 0.4),
    "gpt-5-mini":        (0.25, 2.0),
    "gpt-5":             (1.25, 10.0),
    "gpt-4.1-mini":      (0.4, 1.6),
    "gpt-4.1":           (2.0, 8.0),
    "gpt-4o-mini":       (0.15, 0.6),
    "gpt-4o":            (2.5, 10.0),
    "o4-mini":           (1.1, 4.4),
    "o3":                (2.0, 8.0),
    "grok-4-fast":       (0.2, 0.5),
    "grok-4":            (3.0, 15.0),
    "grok-3-mini":       (0.3, 0.5),
    "grok-3":            (3.0, 15.0),
    "grok-code-fast":    (0.2, 1.5),
    "gemini-3-pro":      (2.0, 12.0),
    "gemini-2.5-flash-lite": (0.1, 0.4),
    "gemini-2.5-flash":  (0.3, 2.5),
    "gemini-2.5-pro":    (1.25, 10.0),
    "deepseek-chat":     (0.28, 0.42),
    "deepseek-reasoner": (0.28, 0.42),
    "kimi-k2":           (0.6, 2.5),
    "devstral":          (0.4, 2.0),
    "mistral-large":     (2.0, 6.0),
    "llama-3.3-70b":     (0.59, 0.79),
    "sonar":             (1.0, 1.0),
}


def price_for(model):
    model = (model or "").lower()
    for prefix, p in sorted(PRICES.items(), key=lambda kv: -len(kv[0])):
        if model.startswith(prefix) or ("/" in model and model.split("/", 1)[1].startswith(prefix)):
            return p
    return None


def resolve_model(cfg):
    provider = cfg.get("provider", "anthropic")
    model = cfg.get("model") or PROVIDERS[provider][3]
    return MODEL_ALIASES.get(provider, {}).get(model, model)


def api_key_for(cfg, provider=None):
    import os
    provider = provider or cfg.get("provider")
    env = PROVIDERS.get(provider, ("", "", "", ""))[2]
    return (os.environ.get(env) if env else "") or cfg.get("api_keys", {}).get(provider, "")
