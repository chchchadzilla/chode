"""Sampling controls — temperature · top_p · top_k — globally, per provider, or per model.

How CHODE decides what to send:

  1. defaults        config["sampling"]        {"temperature": 0.2, "top_p": null, "top_k": null}   (null = don't send)
  2. per provider    config["sampling"]["overrides"]["openrouter"]            = {"temperature": 0.7, "top_k": 40}
  3. per model       config["sampling"]["overrides"]["openrouter/qwen/qwen3-coder:free"] = {"top_p": 0.95}
                     (a bare model id works too: "qwen3:8b")
  4. what the model can take:
       • Anthropic 4.7+/5.x reject all three → not sent, unless you set a per-model override on purpose
       • OpenAI reasoning models (gpt-5, o-series) reject them → not sent
       • anything a model has rejected before is remembered in config["param_quirks"][model] and dropped
         (CHODE learns this live from the 400 and retries — see llm.py)
  So OpenRouter / Ollama / Groq / Gemini models that DO take them get them, Claude 5 doesn't, and you can
  get as granular as one model. `/sampling` shows and edits all of it; `/sampling edit` is the submenu.
"""
import json

from .config import PROVIDERS, save_config

PARAMS = {
    # name: (what it does, min, max, type)
    "temperature": ("randomness — 0 = deterministic, ~0.7 = chatty, up to 2 on most APIs", 0.0, 2.0, float),
    "top_p": ("nucleus sampling — only tokens whose probabilities add up to p (0–1)", 0.0, 1.0, float),
    "top_k": ("only the k most likely tokens (1–1000; OpenAI's own API doesn't take it)", 1, 1000, int),
}
UNSET_WORDS = ("default", "none", "null", "unset", "off", "-", "")


def parse_value(param, raw):
    """'0.7' → 0.7 · '40' → 40 · 'default' → None. Raises ValueError with a human message."""
    if param not in PARAMS:
        raise ValueError(f"unknown setting '{param}' — one of {', '.join(PARAMS)}")
    text = str(raw).strip().lower()
    if text in UNSET_WORDS:
        return None
    desc, lo, hi, typ = PARAMS[param]
    try:
        v = typ(float(text)) if typ is int else float(text)
    except ValueError:
        raise ValueError(f"{param} needs a number (or 'default'), got '{raw}'")
    if not (lo <= v <= hi):
        raise ValueError(f"{param} must be between {lo} and {hi}")
    return v


def scope_key(scope, provider, model):
    """'global' | 'provider' | 'model' | an explicit key → the overrides key ('' = global)."""
    s = (scope or "global").strip()
    if s in ("global", "all", "everywhere", "*"):
        return ""
    if s in ("provider", "this-provider"):
        return provider
    if s in ("model", "this-model"):
        return f"{provider}/{model}" if model else provider
    return s


def _sampling(cfg):
    s = cfg.setdefault("sampling", {})
    s.setdefault("temperature", cfg.get("temperature", 0.2))
    s.setdefault("top_p", None)
    s.setdefault("top_k", None)
    s.setdefault("overrides", {})
    return s


def set_value(cfg, scope, param, value, provider=None, model=None, save=True):
    """Set one sampling param at a scope. value None = 'let the provider decide'. Returns a one-line report."""
    provider = provider or cfg.get("provider", "anthropic")
    model = model if model is not None else cfg.get("model", "")
    key = scope_key(scope, provider, model)
    s = _sampling(cfg)
    if not key:
        s[param] = value
        if param == "temperature":
            cfg["temperature"] = value if value is not None else 0.2   # legacy mirror; None isn't valid there
        where = "everywhere (default)"
    else:
        s["overrides"].setdefault(key, {})[param] = value
        where = f"for {key}"
    # the user is asking for it explicitly → forget a remembered rejection for that exact model so it's retried
    bare = key.split("/", 1)[1] if "/" in key and key.split("/", 1)[0] in PROVIDERS else key
    quirks = cfg.get("param_quirks") or {}
    if value is not None and bare in quirks and param in quirks[bare]:
        quirks[bare] = [q for q in quirks[bare] if q != param]
    if save:
        save_config(cfg)
    shown = "default (provider decides)" if value is None else value
    return f"{param} = {shown} {where}"


def reset(cfg, scope=None, provider=None, model=None, save=True):
    """Drop overrides: all of them (scope None), or one scope key."""
    s = _sampling(cfg)
    if scope is None:
        n = len(s["overrides"])
        s["overrides"] = {}
        msg = f"removed {n} override group(s); defaults stay: " + _fmt_defaults(s)
    else:
        key = scope_key(scope, provider or cfg.get("provider", "anthropic"), model if model is not None else cfg.get("model", ""))
        if not key:
            s["temperature"], s["top_p"], s["top_k"] = 0.2, None, None
            cfg["temperature"] = 0.2
            msg = "defaults reset: temperature 0.2, top_p/top_k off"
        else:
            msg = f"removed overrides for {key}" if s["overrides"].pop(key, None) is not None else f"no overrides for {key}"
    if save:
        save_config(cfg)
    return msg


def forget_quirks(cfg, model=None, save=True):
    """Forget remembered rejections so a param is sent again (one model, or all)."""
    q = cfg.get("param_quirks") or {}
    if model:
        gone = q.pop(model, None)
        msg = f"forgot {', '.join(gone)} for {model}" if gone else f"nothing remembered for {model}"
    else:
        n = sum(len(v) for v in q.values())
        cfg["param_quirks"] = {}
        msg = f"forgot {n} remembered rejection(s)"
    if save:
        save_config(cfg)
    return msg


def _fmt_defaults(s):
    return ", ".join(f"{k} {'off' if s.get(k) is None else s.get(k)}" for k in PARAMS)


def effective(cfg, client):
    """Rows for the current provider/model: (param, value, source, sent, why)."""
    provider, model = client.provider, client.model
    s = _sampling(cfg)
    ov = s.get("overrides") or {}
    gate = client.sampling_gate()
    quirks = (cfg.get("param_quirks") or {}).get(model, [])
    rows = []
    for p in PARAMS:
        value, source = s.get(p), "default"
        for key, label in ((provider, f"provider {provider}"), (model, f"model {model}"), (f"{provider}/{model}", f"model {provider}/{model}")):
            if key in ov and p in ov[key]:
                value, source = ov[key][p], label
        if value is None:
            rows.append((p, None, source, False, "off — provider decides"))
        elif p in quirks:
            rows.append((p, value, source, False, f"not sent — {model} rejected it before (/sampling forget to retry)"))
        elif gate:
            rows.append((p, value, source, False, f"not sent — {gate}"))
        elif p == "top_k" and provider in ("openai", "azure"):
            rows.append((p, value, source, True, "sent — OpenAI's API will reject it, CHODE will drop and remember"))
        else:
            rows.append((p, value, source, True, "sent"))
    return rows


def describe(cfg, client):
    """Human table: what's sent right now, where each value came from, and every override."""
    from .ui import bold, dim, green, yellow
    s = _sampling(cfg)
    out = [bold(f"  🎚 sampling for {client.provider} / {client.model or '(default)'}")]
    for p, v, src, sent, why in effective(cfg, client):
        mark = green("→") if sent else dim("·")
        val = dim("off") if v is None else bold(str(v))
        out.append(f"  {mark} {p:<12} {val:<8} {dim('(' + src + ')'):<34} {dim(why) if sent else yellow(why)}")
    out.append(f"  {dim('·')} {'max_tokens':<12} {bold(str(cfg.get('max_tokens')))}  {dim('(/config max_tokens N)')}")
    ov = s.get("overrides") or {}
    if ov:
        out.append(dim("  overrides:"))
        for key, vals in ov.items():
            out.append(dim(f"    {key}: " + ", ".join(f"{k}={'off' if v is None else v}" for k, v in vals.items())))
    q = cfg.get("param_quirks") or {}
    if q:
        out.append(dim("  remembered rejections (dropped automatically): " + "; ".join(f"{m}: {', '.join(v)}" for m, v in q.items() if v)))
    out.append(dim("  /sampling <param> <value|default> [global|provider|model|<key>]   /sampling edit   /sampling reset [scope]   /sampling forget [model]"))
    return "\n".join(out)


def handle(cfg, client, args):
    """`/sampling …` and `chode sampling …`. Returns text to print (never raises)."""
    from .ui import dim, green, red
    args = list(args or [])
    if not args:
        return describe(cfg, client)
    head = args[0].lower()
    if head in ("edit", "menu", "tune", "interactive"):
        from . import state
        app = state.app()
        if app is not None and getattr(app.ui, "name", "terminal") != "terminal":
            return describe(cfg, client) + "\n" + dim("  (the submenu is terminal-only — here use /sampling <param> <value> [global|provider|model])")
        interactive(cfg, client)
        return ""
    if head == "reset":
        return green("  " + reset(cfg, args[1] if len(args) > 1 else None))
    if head in ("forget", "forget-quirks"):
        return green("  " + forget_quirks(cfg, args[1] if len(args) > 1 else None))
    if head in ("help", "?"):
        return describe(cfg, client)
    if head not in PARAMS:
        return red(f"  unknown setting '{args[0]}'. settings: {', '.join(PARAMS)} · also: edit · reset [scope] · forget [model]")
    if len(args) < 2:
        return red(f"  usage: /sampling {head} <value|default> [global|provider|model|<provider or provider/model>]")
    try:
        value = parse_value(head, args[1])
    except ValueError as e:
        return red(f"  {e}")
    scope = args[2] if len(args) > 2 else "global"
    msg = set_value(cfg, scope, head, value)
    tail = ""
    gate = client.sampling_gate()
    if value is not None and gate and scope_key(scope, client.provider, client.model) in ("", client.provider):
        tail = dim(f"\n  note: {gate} — set it for the model itself to force it: /sampling {head} {value} model")
    return green("  " + msg) + tail


def interactive(cfg, client):
    """The submenu: pick a setting → pick a scope → type a value. Enter on an empty line leaves."""
    from .ui import bold, choose, dim, green, red
    try:
        while True:
            print()
            print(describe(cfg, client))
            print()
            options = [(p, PARAMS[p][0]) for p in PARAMS] + [
                ("max_tokens", "longest answer CHODE asks for (everywhere)"),
                ("reset overrides", "back to the defaults for every provider/model"),
                ("forget remembered rejections", "retry settings a model rejected earlier"),
                ("done", "back")]
            idx = choose("change what?", options, default=len(options))
            label = options[idx][0]
            if label == "done":
                return
            if label == "reset overrides":
                print(green("  " + reset(cfg)))
                continue
            if label.startswith("forget"):
                print(green("  " + forget_quirks(cfg)))
                continue
            if label == "max_tokens":
                raw = input(f"  max_tokens [{cfg.get('max_tokens')}] › ").strip()
                if raw.isdigit() and int(raw) > 0:
                    cfg["max_tokens"] = int(raw)
                    save_config(cfg)
                    print(green(f"  max_tokens = {raw}"))
                continue
            scopes = [("everywhere", "the default for every provider and model"),
                      (f"just {client.provider}", "every model on this provider"),
                      (f"just {client.provider}/{client.model or '(default model)'}", "this one model only")]
            sidx = choose("for which scope?", scopes, default=1)
            scope = ("global", "provider", "model")[sidx]
            cur = dict((r[0], r[1]) for r in effective(cfg, client)).get(label)
            raw = input(f"  {label} [{'default' if cur is None else cur}] (number, or 'default' to let the provider decide) › ").strip()
            if not raw:
                continue
            try:
                value = parse_value(label, raw)
            except ValueError as e:
                print(red(f"  {e}"))
                continue
            print(green("  " + set_value(cfg, scope, label, value)))
            gate = client.sampling_gate()
            if value is not None and gate and scope != "model":
                print(dim(f"  note: {gate} — pick the model scope to force it anyway"))
    except (EOFError, KeyboardInterrupt):
        print()


def as_json(cfg):
    return json.dumps({"sampling": _sampling(cfg), "param_quirks": cfg.get("param_quirks") or {}}, indent=2)
