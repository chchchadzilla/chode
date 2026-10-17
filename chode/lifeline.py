"""The lifeline: CHODE never dies on a connection error.

1. **Detect** what can actually work on this machine: keys in env/config, local servers that are
   really running (Ollama, LM Studio), and keyless free endpoints.
2. **Classify** failures (bad key · model not found · rate limit · overloaded · network) and
   attach a plain-English hint plus the provider's docs URL.
3. **Auto-correct** a wrong model name against the provider's live model list.
4. **Fall back** down the ladder until something answers — ending at a free model.
5. **Fix** itself: `chode fix` runs a small agent on whatever model works, with tools to list
   models, read the docs, test a connection and rewrite the config.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import time
import webbrowser

import requests

from .config import (FREE_TIERS, KEYLESS, MODEL_ALIASES, MODEL_FALLBACKS, PROVIDERS, PROVIDER_NOTES, api_key_for,
                     save_config)

PROVIDER_DOCS = {
    "anthropic": "https://docs.anthropic.com/en/docs/about-claude/models/overview",
    "openai": "https://platform.openai.com/docs/models",
    "gemini": "https://ai.google.dev/gemini-api/docs/models",
    "xai": "https://docs.x.ai/docs/models",
    "openrouter": "https://openrouter.ai/models?q=free",
    "groq": "https://console.groq.com/docs/models",
    "mistral": "https://docs.mistral.ai/getting-started/models/models_overview/",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing",
    "together": "https://docs.together.ai/docs/serverless-models",
    "cerebras": "https://inference-docs.cerebras.ai/models/overview",
    "moonshot": "https://platform.moonshot.ai/docs",
    "perplexity": "https://docs.perplexity.ai/getting-started/models",
    "azure": "https://learn.microsoft.com/azure/ai-services/openai/concepts/models",
    "huggingface": "https://huggingface.co/docs/inference-providers/index",
    "ollama": "https://ollama.com/search?c=tools",
    "lmstudio": "https://lmstudio.ai/docs/app/api/endpoints/openai",
    "local": "https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md",
    "pollinations": "https://github.com/pollinations/pollinations/blob/master/APIDOCS.md",
}

# Ladder order when "fallbacks" is "auto". Keyed providers first (best → cheapest), then local, then keyless.
AUTO_ORDER = ["anthropic", "openai", "gemini", "xai", "groq", "openrouter", "deepseek", "mistral", "cerebras",
              "together", "moonshot", "huggingface", "ollama", "lmstudio", "local", "pollinations"]

# Small, free, tool-capable local models — the first that fits is what `chode fix` pulls.
OLLAMA_STARTERS = ["qwen2.5-coder:7b", "qwen3:8b", "qwen3:4b", "llama3.2:3b"]


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def _probe(url, timeout=1.2, headers=None):
    try:
        r = requests.get(url, timeout=timeout, headers=headers or {})
        return r.status_code < 500, r
    except Exception:
        return False, None


def ollama_running(base="http://localhost:11434"):
    ok, r = _probe(f"{base}/api/tags")
    if not ok or r is None:
        return False, []
    try:
        return True, [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return True, []


def ollama_installed():
    return bool(shutil.which("ollama"))


def ollama_pull(model, progress=None, timeout=1800):
    """Pull a model with the ollama CLI. Returns (ok, message)."""
    if not ollama_installed():
        return False, "ollama is not installed — https://ollama.com/download"
    try:
        proc = subprocess.Popen(["ollama", "pull", model], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        t0 = time.time()
        for line in proc.stdout:
            if progress:
                progress(line.strip())
            if time.time() - t0 > timeout:
                proc.kill()
                return False, "pull timed out"
        proc.wait()
        return proc.returncode == 0, "pulled" if proc.returncode == 0 else f"ollama pull exited {proc.returncode}"
    except Exception as e:
        return False, str(e)


def usable(cfg, provider):
    """Can this provider plausibly answer right now? (key present, or keyless/plan, or local server up)"""
    style, default_url, key_env, default_model = PROVIDERS[provider]
    if style == "plan":
        from .plans import PLAN_CLIS, _which
        cli = PLAN_CLIS.get(provider, (None,))[0]
        return bool(cli is None and (cfg.get("plans", {}).get("custom", {}).get("command")) or (cli and _which(cli)))
    base = (cfg.get("base_urls", {}).get(provider) or default_url).rstrip("/")
    if provider in ("ollama", "lmstudio", "local"):
        ok, _ = _probe(f"{base}/models")
        if provider == "ollama" and not ok:
            ok, _ = ollama_running(base.rsplit("/v1", 1)[0])[0], None
        return ok
    if provider in KEYLESS:
        return True
    return bool(api_key_for(cfg, provider))


def ladder(cfg, exclude=()):
    """Ordered [(provider, model)] candidates that can plausibly work, best first."""
    fb = cfg.get("fallbacks", "auto")
    if fb is False or fb == "off":
        return []
    out = []
    seen = set()

    def add(p, m=""):
        if p in PROVIDERS and p not in exclude and p not in seen:
            seen.add(p)
            out.append((p, m))
    def default_model(p):
        if p == "ollama":
            up, models = ollama_running((cfg.get("base_urls", {}).get("ollama") or PROVIDERS["ollama"][1]).rsplit("/v1", 1)[0])
            if up and models:
                return pick_ollama_model(models)
            return None if up else ""  # None = running but empty: nothing to talk to yet
        if p in FREE_TIERS:
            return FREE_TIERS[p]["model"]
        return ""
    lkg = cfg.get("last_known_good") or {}
    if lkg.get("provider") and lkg["provider"] not in exclude and usable(cfg, lkg["provider"]):
        add(lkg["provider"], lkg.get("model", ""))
    if isinstance(fb, list):
        for item in fb:
            p, _, m = str(item).partition(":")
            if p in PROVIDERS and usable(cfg, p):
                dm = m or default_model(p)
                if dm is None:
                    continue
                add(p, dm)
        return out
    for p in AUTO_ORDER:
        if p in ("ollama", "lmstudio", "local"):
            if usable(cfg, p):
                dm = default_model(p)
                if dm is None:
                    continue
                add(p, dm)
        elif p in KEYLESS or api_key_for(cfg, p):
            add(p, default_model(p))
    return out


def pick_ollama_model(models):
    """Prefer coder/instruct models that support tools; fall back to whatever is installed."""
    prefs = ["qwen3-coder", "qwen2.5-coder", "qwen3", "devstral", "llama3.3", "llama3.2", "llama3.1", "mistral", "gemma3"]
    names = [m for m in models if m and not m.startswith("nomic") and "embed" not in m]
    for pref in prefs:
        for n in names:
            if n.lower().startswith(pref):
                return n
    return names[0] if names else ""


def status(cfg):
    """Human-readable detection report: [(provider, ok, note)]."""
    rows = []
    for p in AUTO_ORDER:
        style, default_url, key_env, default_model = PROVIDERS[p]
        if p in ("ollama", "lmstudio", "local"):
            up = usable(cfg, p)
            note = "running" if up else "not running"
            if p == "ollama" and up:
                _, models = ollama_running()
                note += f" · {len(models)} model(s)" + (f" · {pick_ollama_model(models)}" if models else " · none pulled yet")
            rows.append((p, up, note))
        elif p in KEYLESS:
            rows.append((p, True, PROVIDER_NOTES.get(p, "")))
        else:
            has = bool(api_key_for(cfg, p))
            rows.append((p, has, "key found" if has else f"no key ({key_env})" + (f" · free tier: {FREE_TIERS[p]['signup']}" if p in FREE_TIERS else "")))
    return rows


# --------------------------------------------------------------------------
# Error classification + hints
# --------------------------------------------------------------------------

KINDS = ("auth", "not_found", "bad_request", "rate_limit", "overloaded", "network", "unknown")


def classify(status_code=None, body="", exc=None):
    text = (body or "").lower()
    if exc is not None and status_code is None:
        return "network"
    if status_code in (401, 403):
        return "auth"
    if status_code == 404 or ("model" in text and ("not found" in text or "does not exist" in text or "not_found" in text or "unknown model" in text or "no such model" in text)):
        return "not_found"
    if status_code == 429 or "quota" in text or "rate limit" in text or "insufficient_quota" in text or "credit" in text:
        return "rate_limit"
    if status_code is not None and status_code >= 500 or status_code == 529:
        return "overloaded"
    if status_code == 400:
        return "bad_request"
    return "unknown"


def hint(kind, provider, model="", detail=""):
    docs = PROVIDER_DOCS.get(provider, "")
    key_env = PROVIDERS.get(provider, ("", "", "", ""))[2]
    free = f" Free alternative: {FREE_TIERS[provider]['signup']}" if provider in FREE_TIERS else ""
    if kind == "auth":
        if provider in KEYLESS:
            return f"{provider} refused the request (auth). It may be down or changed its API — docs: {docs}"
        return (f"{provider} rejected the API key. Check {key_env} (or run `chode setup` to paste a new one). "
                f"Keys page is linked from the docs: {docs}.{free}")
    if kind == "not_found":
        return (f"'{model}' isn't a model {provider} knows (or the base URL is wrong). CHODE will try to match it "
                f"against the live model list; otherwise pick one with /models or read {docs}")
    if kind == "rate_limit":
        return (f"{provider} says you're out of quota or rate-limited. Wait a minute, add credit, or let CHODE fall back "
                f"to another provider.{free}")
    if kind == "overloaded":
        return f"{provider} is overloaded or erroring on their side. CHODE retries with backoff, then falls back."
    if kind == "network":
        if provider in ("ollama", "lmstudio", "local"):
            return (f"Nothing is listening at the {provider} URL. Start it (ollama: `ollama serve` then `ollama pull qwen2.5-coder:7b`; "
                    f"LM Studio: enable the local server) or pick another provider.")
        return f"Couldn't reach {provider}. Check your internet/proxy/VPN, or the base URL in /config. Docs: {docs}"
    if kind == "bad_request":
        return f"{provider} rejected the request shape ({detail[:120]}). Often a model that doesn't support tool calling — try another model. Docs: {docs}"
    return f"Unexpected error from {provider}: {detail[:160]}. Docs: {docs}"


# --------------------------------------------------------------------------
# Model-name auto-correction
# --------------------------------------------------------------------------

def _version_key(model_id):
    """Sort key: version numbers first (4-5 beats 4), release date second (20250929 beats 20250514)."""
    m = re.search(r"(\d{8})", model_id)
    date = int(m.group(1)) if m else 0
    rest = model_id.replace(m.group(1), "") if m else model_id
    nums = [int(n) for n in re.findall(r"\d+", rest)]
    nums = nums + [0] * (6 - len(nums))
    return nums[:6] + [date]


def resolve_alias(alias, available):
    """'sonnet' → newest id containing 'sonnet' from the live list (date-suffixed ids rank by their numbers)."""
    cands = [m for m in available if alias.lower() in m.lower()]
    if not cands:
        return None
    cands.sort(key=_version_key, reverse=True)
    return cands[0]


def correct_model(wanted, available, provider=""):
    """Best replacement for a model name the provider rejected, or None."""
    if not available:
        return None
    low = {m.lower(): m for m in available}
    if wanted.lower() in low:
        return low[wanted.lower()]
    for alias in MODEL_ALIASES.get(provider, {}):
        if wanted.lower() == alias or wanted.lower() == MODEL_ALIASES[provider][alias].lower():
            hit = resolve_alias(alias, available)
            if hit:
                return hit
    # strip a date/version suffix and look for the newest sibling: claude-sonnet-4-5 → claude-sonnet-*
    stem = re.sub(r"[-_]?\d{8}$", "", wanted.lower())
    stem = re.sub(r"[-_.]\d+([-_.]\d+)*$", "", stem)
    sib = [m for m in available if m.lower().startswith(stem) and len(stem) >= 4]
    if sib:
        sib.sort(key=_version_key, reverse=True)
        return sib[0]
    close = difflib.get_close_matches(wanted, available, n=1, cutoff=0.6)
    if close:
        return close[0]
    for fb in MODEL_FALLBACKS.get(provider, []):
        if fb in available:
            return fb
    return None


# --------------------------------------------------------------------------
# Startup guarantee
# --------------------------------------------------------------------------

def ensure_usable(cfg, notify=None):
    """If the configured provider can't possibly work (no key, server down), switch to the best rung
    of the ladder for this session. Returns a note or None."""
    p = cfg.get("provider", "anthropic")
    if usable(cfg, p):
        return None
    cands = ladder(cfg, exclude=(p,))
    if not cands:
        note = (f"no API key for {p} and nothing else is reachable. Run `chode setup` → 'Just make it work' "
                f"(free), or `chode fix`.")
        if notify:
            notify(note, "warn")
        return note
    np_, nm = cands[0]
    cfg["_fallback_from"] = p
    cfg["provider"], cfg["model"] = np_, nm or ""
    why = "no API key" if PROVIDERS[p][2] else "not reachable"
    note = (f"{p} is unusable ({why}) → using {np_}{(' / ' + nm) if nm else ''} for this session. "
            f"`/provider keep` makes it the default; `chode setup` to change.")
    if notify:
        notify(note, "warn")
    return note


def remember_good(cfg, provider, model):
    """Record the last provider/model that answered — touching ONLY that key in the config file,
    so a session fallback never rewrites the user's chosen defaults."""
    from .paths import CONFIG_FILE
    cfg["last_known_good"] = {"provider": provider, "model": model or ""}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
        if data.get("last_known_good") == cfg["last_known_good"]:
            return
        data["last_known_good"] = cfg["last_known_good"]
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------
# Guided free-key flow (used by the wizard)
# --------------------------------------------------------------------------

def free_key_options():
    return [(p, f"{FREE_TIERS[p]['note']} · {FREE_TIERS[p]['signup']}") for p in FREE_TIERS]


def open_signup(provider):
    url = FREE_TIERS.get(provider, {}).get("signup")
    if url:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return url


# --------------------------------------------------------------------------
# `chode fix` — the self-repair agent
# --------------------------------------------------------------------------

FIXER_PROMPT = """You are CHODE's connection doctor. The user's coding assistant could not reach its model. Your ONLY job is to get a working provider+model configured and verified, then explain in 3 short lines what you changed and why. Be kind; assume the user is new to this.

Diagnosis so far:
{diagnosis}

Procedure (follow in order, stop as soon as `test_connection` succeeds):
1. `list_models` for the configured provider. If it works, pick the closest sensible match to what the user wanted (prefer models that support tool calling; prefer the newest version) and `set_config` model to it.
2. If listing fails with an auth error, the key is wrong or missing — do NOT ask for a key. Switch to a provider that is marked usable in the diagnosis (`set_config` provider), pick its default model, and test.
3. If the model list is unhelpful, `web_fetch` the provider's docs URL from the diagnosis and read the model names there.
4. Run `test_connection` after every change. If it fails, read the error kind and hint, adjust, retry (max 6 attempts total).
5. Finish with: what works now (provider + model), what was wrong, and the one command the user can run later to upgrade (`chode setup`). Never touch api_keys. Never run anything but ollama commands in bash.
"""


def diagnosis_text(cfg, error=None):
    lines = [f"- configured provider: {cfg.get('provider')} · model: {cfg.get('model') or '(default)'}"]
    if error is not None:
        lines.append(f"- last error: [{getattr(error, 'kind', 'unknown')}] {str(error)[:300]}")
        if getattr(error, "hint", ""):
            lines.append(f"- hint: {error.hint}")
    for p, ok, note in status(cfg):
        lines.append(f"- {p}: {'USABLE' if ok else 'not usable'} — {note}" + (f" — docs: {PROVIDER_DOCS[p]}" if p in PROVIDER_DOCS else ""))
    return "\n".join(lines)


def run_fixer(cfg, error=None, ui=None):
    """Try to repair the config with a small agent on whatever model works. Returns the agent's final text."""
    from . import state
    from .llm import LLMClient, LLMError
    from .agent import run_agent
    from .permissions import Permissions
    from .ui import SilentUI, TerminalUI
    ui = ui or (state.app().ui if state.app() else TerminalUI())
    work = dict(cfg)
    work["fallbacks"] = "auto"
    note = ensure_usable(work, notify=None)
    cands = [(work["provider"], work.get("model", ""))] + ladder(work, exclude=(work["provider"],))
    last_err = None
    for prov, model in cands:
        work["provider"], work["model"] = prov, model or ""
        client = LLMClient(work)
        client.allow_fallback = False
        try:
            client.chat("Reply with exactly: pong", [{"role": "user", "content": "ping"}], tools=None)
        except LLMError as e:
            last_err = e
            continue
        if ui:
            ui.notice(f"  🩹 fixer is running on {prov}{(' / ' + model) if model else ''}", "info")
        app = state.app() or state.set_app(state.App(cfg, ui=ui))
        app.client = client
        perms = Permissions(cfg, ui)
        perms.always.update({"set_config", "test_connection", "list_models", "web_fetch"})
        system = FIXER_PROMPT.format(diagnosis=diagnosis_text(cfg, error))
        history = [{"role": "user", "content": "Please get my model connection working."}]
        try:
            return run_agent(client, perms, system, history, ui=ui, max_turns=14) or "(fixer finished without a summary)"
        except LLMError as e:
            last_err = e
            continue
    return ("No model anywhere could answer, so the fixer can't run. Here's the manual path:\n" + playbook(cfg, last_err or error))


def playbook(cfg, error=None):
    p = cfg.get("provider", "anthropic")
    lines = []
    if error is not None and getattr(error, "hint", ""):
        lines.append(f"What happened: {error.hint}")
    lines.append("Fastest fixes, pick one:")
    lines.append("  1. Free, no key, no signup:  /provider pollinations        (slow-ish, rate-limited, fine for fixing things)")
    if ollama_installed():
        up, models = ollama_running()
        if up and models:
            lines.append(f"  2. Free, local, private:     /provider ollama {pick_ollama_model(models)}")
        else:
            lines.append("  2. Free, local, private:     ollama serve   &&   ollama pull qwen2.5-coder:7b   then /provider ollama")
    else:
        lines.append("  2. Free, local, private:     install https://ollama.com/download, then `ollama pull qwen2.5-coder:7b`, then /provider ollama")
    for prov in ("gemini", "groq", "openrouter"):
        ft = FREE_TIERS[prov]
        lines.append(f"  3. Free key (2 min):         {ft['signup']}  → export {PROVIDERS[prov][2]}=…  → /provider {prov} {ft['model']}")
        break
    lines.append(f"  4. Fix the current one:      docs for {p}: {PROVIDER_DOCS.get(p, '')}  → /models → /model <name>")
    lines.append("Or just run `chode fix` and let CHODE do this for you.")
    return "\n".join(lines)
