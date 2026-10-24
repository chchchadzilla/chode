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

# Where you actually get a key (the docs page is not the keys page).
PROVIDER_KEYS = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "openai": "https://platform.openai.com/api-keys",
    "gemini": "https://aistudio.google.com/apikey",
    "xai": "https://console.x.ai",
    "openrouter": "https://openrouter.ai/keys",
    "groq": "https://console.groq.com/keys",
    "mistral": "https://console.mistral.ai/api-keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "together": "https://api.together.ai/settings/api-keys",
    "cerebras": "https://cloud.cerebras.ai",
    "moonshot": "https://platform.moonshot.ai/console/api-keys",
    "perplexity": "https://www.perplexity.ai/settings/api",
    "huggingface": "https://huggingface.co/settings/tokens",
    "azure": "https://portal.azure.com",
}

# What a real key starts with — the fastest way to spot "you pasted the wrong thing".
KEY_PREFIXES = {"anthropic": "sk-ant-", "openai": "sk-", "openrouter": "sk-or-", "groq": "gsk_", "xai": "xai-",
                "gemini": "AIza", "huggingface": "hf_", "perplexity": "pplx-", "deepseek": "sk-", "together": ""}

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
        if PROVIDERS.get(provider, ("",))[0] == "plan":
            return f"the {provider} CLI isn't signed in. Run /login (or `chode fix`) and finish the sign-in."
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
        param = _rejected_param(detail)
        if param:
            return (f"{provider} doesn't take `{param}` for {model or 'this model'} — CHODE drops it automatically, retries, and "
                    f"remembers that for this model (`/sampling` to see or change what gets sent). Just try again.")
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


def verify_model(cfg, name, client=None, available=None):
    """What a human typed → what the provider actually calls it, checked against the LIVE model list.

    'anthropic/opus-5.5' → 'claude-opus-5-5' (normalized), then looked up; 'sonnet' → the newest sonnet you
    have; a typo → the closest real id. Returns (model_id, note, verified). Never raises, never edits cfg:
    the caller decides what to do with the answer. `available` skips the network call when you already
    have the list."""
    from .config import normalize_model
    provider = cfg.get("provider", "anthropic")
    typed = (name or "").strip()
    wanted = normalize_model(provider, typed)
    if not wanted:
        return "", None, False
    style = PROVIDERS.get(provider, ("openai",))[0]
    if style == "plan":
        return wanted, None, False
    if available is None:
        if not usable(cfg, provider):
            why = "no API key yet" if PROVIDERS[provider][2] else "server not running"
            return wanted, f"couldn't check '{wanted}' against {provider}'s model list ({why}) — CHODE will auto-correct it on first use", False
        from .llm import LLMClient, LLMError
        try:
            available = [m for m in (client or LLMClient(cfg)).list_models(provider) if m]
        except LLMError as e:
            return wanted, f"couldn't check '{wanted}' against {provider}'s model list ({e.kind}) — CHODE will auto-correct it on first use", False
    if not available:
        return wanted, None, False
    low = {m.lower(): m for m in available}
    if wanted.lower() in low:
        exact = low[wanted.lower()]
        return exact, (None if exact == typed else f"'{typed}' → '{exact}'"), True
    alias_target = MODEL_ALIASES.get(provider, {}).get(wanted.lower())
    if alias_target and alias_target.lower() in low:
        return low[alias_target.lower()], f"'{typed}' → '{low[alias_target.lower()]}'", True
    fixed = correct_model(wanted, available, provider)
    if fixed:
        return fixed, f"'{typed}' isn't a model {provider} knows → using '{fixed}' (closest match on the live list; /models to see all)", True
    return wanted, (f"'{wanted}' isn't on {provider}'s model list ({len(available)} models) — /models shows them; "
                    f"CHODE will try to auto-correct on first use"), False


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
    if PROVIDERS.get(cfg.get("provider"), ("",))[0] == "plan":
        out = _fix_plan(cfg, ui)
        if out:
            return out
    work = dict(cfg)
    work["fallbacks"] = "auto"
    note = ensure_usable(work, notify=None)
    cands = [(work["provider"], work.get("model", ""))] + ladder(work, exclude=(work["provider"],))
    last_err = None
    for prov, model in cands:
        work["provider"], work["model"] = prov, model or ""
        client = LLMClient(work)
        client.allow_fallback = False
        client.auto_login = False
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


def _fix_plan(cfg, ui):
    """Plan providers have no key or model list to repair — the usual break is the vendor CLI being
    signed out. Sign it in, prove it answers, and report. Returns None to fall through to the
    general fixer (CLI missing or still not answering)."""
    from . import plans
    from .llm import LLMClient, LLMError
    provider = cfg["provider"]
    cli, label, install = plans.PLAN_CLIS.get(provider, (None, "", ""))
    if cli and not plans._which(cli):
        if ui:
            ui.notice(f"  `{cli}` isn't installed ({label}). Install: {install}", "warn")
        return None
    if cli and plans.logged_in(cli) is False:
        if ui:
            ui.notice(f"  🔑 {cli} isn't signed in — opening its sign-in…", "warn")
        web = getattr(ui, "name", "") == "web"
        ok, note = plans.login(provider, inline=False if web else None)
        if ui:
            ui.notice(("  ✓ " if ok else "  ✗ ") + note, "ok" if ok else "error")
        if ok is False:
            return (f"✗ {note}\nYour provider is still {provider}. To use something else meanwhile: "
                    f"/provider pollinations (free, no key) or `chode setup`.")
    client = LLMClient(dict(cfg))
    client.allow_fallback = False
    client.auto_login = False
    try:
        client.chat("Reply with exactly: pong", [{"role": "user", "content": "ping"}], tools=None)
    except LLMError as e:
        return (f"✗ {provider} still doesn't answer: [{e.kind}] {str(e)[:300]}\n"
                + (f"→ {e.hint}\n" if e.hint else "")
                + f"Your provider is still {provider}. To use something else meanwhile: /provider pollinations or `chode setup`.")
    return f"✓ {provider} ({label}) is signed in and answering — you're good. Nothing else changed."


_SAMPLING_PARAMS = ("temperature", "top_p", "top_k", "max_tokens", "max_completion_tokens", "stream_options")


def _rejected_param(error):
    text = str(error or "").lower()
    if not text:
        return None
    for p in _SAMPLING_PARAMS:
        if re.search(r"(?<![a-z_])" + re.escape(p) + r"(?![a-z_])", text):
            return p
    return None


def _free_paths(cfg, in_session=True):
    """The three free ways out, as concrete commands for THIS machine."""
    sw = "/provider" if in_session else "chode chat --provider"
    out = [f"free, no key, no signup:   {sw} pollinations          (slower, rate-limited — perfect for getting unstuck)"]
    if ollama_installed():
        up, models = ollama_running()
        if up and models:
            out.append(f"free, local, private:      {sw} ollama {pick_ollama_model(models)}")
        elif up:
            out.append(f"free, local, private:      ollama pull qwen2.5-coder:7b     then  {sw} ollama")
        else:
            out.append(f"free, local, private:      ollama serve   then   ollama pull qwen2.5-coder:7b   then  {sw} ollama")
    else:
        out.append(f"free, local, private:      install https://ollama.com/download → ollama pull qwen2.5-coder:7b → {sw} ollama")
    ft = FREE_TIERS["gemini"]
    out.append(f"free key, 2 minutes:       {ft['signup']} → `chode setup` → \"Free key, 2 minutes\"  (or export {PROVIDERS['gemini'][2]}=…)")
    return out


def what_now(cfg, error=None, in_session=True):
    """The whole 'what do I do now' answer for ANY connection failure, keyed by what actually went wrong.

    Sections: what happened (plain English) · what CHODE already did · do this now (specific to the error) ·
    free ways out that work on this machine · let CHODE do it (`chode fix`) · the docs link."""
    kind = getattr(error, "kind", "unknown") if error is not None else "unknown"
    provider = getattr(error, "provider", "") or cfg.get("provider", "anthropic")
    model = getattr(error, "model", "") or cfg.get("model") or PROVIDERS.get(provider, ("", "", "", ""))[3] or "(provider default)"
    key_env = PROVIDERS.get(provider, ("", "", "", ""))[2]
    docs = PROVIDER_DOCS.get(provider, "")
    keys_url = PROVIDER_KEYS.get(provider, docs)
    raw = str(error)[:220].replace("\n", " ") if error is not None else ""
    fix_cmd = "/fix" if in_session else "chode fix"
    model_cmd = "/model" if in_session else "chode chat --model"
    samp_cmd = "/sampling" if in_session else "chode sampling"
    L = []

    def section(title):
        L.append(f"{title}")

    # ---- what happened --------------------------------------------------------------
    section("WHAT HAPPENED")
    is_plan = PROVIDERS.get(provider, ("",))[0] == "plan"
    if kind == "auth":
        if is_plan:
            L.append(f"  {provider} runs through a vendor CLI on your subscription, and that CLI isn't signed in.")
        elif provider in KEYLESS:
            L.append(f"  {provider} refused the request. It's keyless, so this usually means the service is down or changed its API.")
        else:
            L.append(f"  {provider} rejected your API key (or there isn't one). The request never got to a model.")
    elif kind == "not_found":
        L.append(f"  {provider} has no model called '{model}'. Names change often and every vendor spells them differently "
                 f"(the real Anthropic ids look like claude-opus-5-5, not anthropic/opus-5.5).")
    elif kind == "bad_request":
        param = _rejected_param(error)
        if param:
            L.append(f"  {provider} rejected the `{param}` setting for {model}: {raw}")
        else:
            L.append(f"  {provider} rejected the shape of the request: {raw}")
    elif kind == "rate_limit":
        L.append(f"  {provider} says you're out of quota or sending too fast. Your setup is fine; the account is empty or throttled.")
    elif kind == "overloaded":
        L.append(f"  {provider}'s servers are overloaded or erroring. This is on their side, not yours.")
    elif kind == "network":
        if provider in ("ollama", "lmstudio", "local"):
            L.append(f"  Nothing is listening where {provider} should be ({(cfg.get('base_urls') or {}).get(provider) or PROVIDERS[provider][1]}).")
        else:
            L.append(f"  CHODE couldn't reach {provider} at all — internet, VPN/proxy, firewall, or a wrong base URL.")
    else:
        L.append(f"  Something unexpected came back from {provider}: {raw or 'no detail'}")
    if error is not None and getattr(error, "hint", "") and kind in ("unknown",):
        L.append(f"  {error.hint}")

    # ---- what CHODE already did ----------------------------------------------------
    did = []
    if kind in ("network", "overloaded", "rate_limit"):
        did.append(f"retried {cfg.get('retries', 3)}× with backoff")
    if kind == "not_found":
        did.append("tried to match the name against the live model list")
    if kind == "bad_request" and _rejected_param(error):
        did.append("drops rejected settings automatically and remembers it per model (so the next try just works)")
    fb = cfg.get("fallbacks", "auto")
    if fb is False or fb == "off":
        did.append("did NOT fall back (fallbacks are off: /config fallbacks auto to turn them on)")
    elif cfg.get("_fallback_from"):
        did.append(f"fell back from {cfg['_fallback_from']} to {cfg.get('provider')} for this session")
    if did:
        section("WHAT CHODE ALREADY DID")
        for d in did:
            L.append(f"  • {d}")

    # ---- do this now --------------------------------------------------------------
    section("DO THIS NOW")
    if kind == "auth" and is_plan:
        from .plans import AUTH_ARGS, PLAN_CLIS
        cli = PLAN_CLIS.get(provider, (provider,))[0] or provider
        L.append(f"  1. {'/login' if in_session else 'chode fix'} — opens the {cli} sign-in; finish it in the browser/window it opens.")
        L.append(f"  2. Or sign in yourself in any terminal: {' '.join([cli] + AUTH_ARGS.get(cli, (None, []))[1])}")
        L.append(f"  3. Then just send your message again.")
    elif kind == "auth" and provider not in KEYLESS:
        pfx = KEY_PREFIXES.get(provider, "")
        L.append(f"  1. Get (or re-copy) a key: {keys_url}" + (f"   — real {provider} keys start with `{pfx}`" if pfx else ""))
        L.append(f"  2. Give it to CHODE: `chode setup` → \"API key I already have\" → paste it (stored chmod 600),")
        L.append(f"     or set it in your shell: export {key_env}=…   (Windows PowerShell: $env:{key_env}=\"…\"; permanent: setx {key_env} …)")
        L.append(f"  3. Check the account has credit / an active plan — a valid key with $0 balance also fails.")
        if provider == "anthropic":
            L.append("  4. On a Claude Pro/Max subscription instead of an API key? That's a different thing: /provider claude-plan (needs the `claude` CLI logged in).")
    elif kind == "auth":
        L.append(f"  1. Check the service status / docs: {docs}")
        L.append("  2. Pick another free rung below while it's down.")
    elif kind == "not_found":
        suggestion = None
        if usable(cfg, provider):
            try:
                from .llm import LLMClient
                avail = [m for m in LLMClient(dict(cfg, provider=provider)).list_models(provider) if m]
                suggestion = correct_model(model, avail, provider)
            except Exception:
                suggestion = None
        if suggestion:
            L.append(f"  1. Did you mean `{suggestion}`?  →  {model_cmd} {suggestion}")
        else:
            known = MODEL_FALLBACKS.get(provider, [])[:3]
            if known:
                L.append(f"  1. Names {provider} definitely knows: {', '.join(known)}  →  {model_cmd} <one of them>")
        L.append(f"  2. See the real list: {'/models' if in_session else 'chode sampling (shows the current one) · /models inside a session'}   (or let `{fix_cmd}` pick one for you)")
        L.append(f"  3. Vendor's own page of names: {docs}")
        if provider in ("ollama", "lmstudio", "local"):
            L.append("  4. Local server: the model must be pulled/loaded first (ollama pull <name>; LM Studio: load it in the app).")
    elif kind == "bad_request":
        param = _rejected_param(error)
        if param:
            L.append(f"  1. Just try again — CHODE already dropped `{param}` for {model} and remembered that.")
            L.append(f"  2. Set it yourself: {samp_cmd} {param} default   (per model / per provider — `{samp_cmd}` shows what's sent)")
            L.append("  3. Some models DO take it (OpenRouter, Ollama, OpenAI's older models) — CHODE keeps per-model notes, so nothing else changes.")
        else:
            L.append(f"  1. Most common cause: a model that can't do tool calling → pick another: /models, then {model_cmd} <name>")
            L.append(f"  2. Second most common: the base URL points at the wrong API → /config base_urls.{provider} <url> (default: {PROVIDERS[provider][1] or 'n/a'})")
            L.append(f"  3. Read the message above literally — it usually names the field. Docs: {docs}")
    elif kind == "rate_limit":
        L.append(f"  1. Wait a minute and retry (free tiers reset by the minute/day).")
        L.append(f"  2. Add credit / check limits: {keys_url}")
        L.append(f"  3. Or switch for now — pick a free rung below; `{fix_cmd}` does it for you.")
    elif kind == "overloaded":
        L.append("  1. Wait 30–60 seconds and retry — this almost always clears on its own.")
        L.append(f"  2. Vendor status page / docs: {docs}")
        L.append("  3. Meanwhile use another rung below (your work isn't lost).")
    elif kind == "network":
        if provider == "ollama":
            L.append("  1. Start it:  ollama serve        (or open the Ollama app)")
            L.append("  2. Get a model: ollama pull qwen2.5-coder:7b   (~4 GB, free, good at tools)")
            L.append("  3. Not installed? https://ollama.com/download")
        elif provider == "lmstudio":
            L.append("  1. Open LM Studio → Developer tab → Start Server (port 1234), load a model.")
        elif provider == "local":
            L.append(f"  1. Start your server (llama.cpp / vLLM / LiteLLM / Jan…) and make sure the URL matches: /config base_urls.local <url>")
        else:
            L.append("  1. Open any website — is the internet up? On a VPN / corporate network, set HTTPS_PROXY if you need one.")
            L.append(f"  2. Base URL right? default is {PROVIDERS[provider][1]}  → /config base_urls.{provider} <url> (or delete the override)")
            L.append("  3. Pick a local or free rung below while it's unreachable.")
    else:
        L.append(f"  1. Read the error text above — it usually says what's wrong. Docs: {docs}")
        L.append(f"  2. `{fix_cmd}` runs the connection doctor; `chode doctor` audits everything else.")

    # ---- free ways out ----------------------------------------------------------------
    section("ANY OF THESE GETS YOU CODING IN UNDER 2 MINUTES")
    for i, line in enumerate(_free_paths(cfg, in_session), 1):
        L.append(f"  {i}. {line}")

    # ---- the easy button ------------------------------------------------------------------
    section("OR LET CHODE DO IT")
    both = "`/fix` in a session · `chode fix` from your terminal" if in_session else "`chode fix` from your terminal · `/fix` in a session"
    L.append(f"  {both} — the connection doctor runs on whatever model answers, reads the error, lists models,")
    L.append("  reads the vendor's docs, switches provider/model, tests, and tells you what it changed. It can't see or change API keys.")
    if error is not None and getattr(error, "hint", "") and kind != "unknown":
        L.append(f"  (short version: {error.hint[:200]})")
    return "\n".join(L)


def playbook(cfg, error=None):
    """Back-compat name: the full 'what now' block."""
    return what_now(cfg, error)
