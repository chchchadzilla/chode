"""Interactive flows: setup wizard, one-click import, plan detection, ORDER CLI."""
import getpass
import os
import time
from pathlib import Path

from . import VERSION
from .config import MODES, MODE_NOTES, PROVIDERS, PROVIDER_NOTES, api_key_for, save_config
from .llm import LLMClient, LLMError
from .paths import CONFIG_FILE
from .ui import (Spinner, THEMES, accent_bold, bad, bold, c, choose, cyan, dim, green, info, magenta, ok,
                 parse_selection, red, set_theme, warn, yellow, yesno)


# ---- setup wizard ----------------------------------------------------------

def run_wizard(cfg):
    print(bold("\n  ⚙  CHODE setup") + dim("  (Enter accepts the [default] · Ctrl-C bails)\n"))
    try:
        _wizard(cfg)
    except (EOFError, KeyboardInterrupt):
        print(dim("\n  setup cancelled (nothing saved)"))


def _wizard(cfg):
    cur_name = cfg.get("name") or ""
    raw = input(f"  what should CHODE call you? [{cur_name or 'legend'}] › ").strip()
    cfg["name"] = raw or cur_name
    theme_names = list(THEMES)
    tidx = choose("accent color?", [(c(THEMES[t], "■■■ " + t), "") for t in theme_names],
                  default=theme_names.index(cfg.get("theme", "magenta")) + 1)
    cfg["theme"] = theme_names[tidx]
    set_theme(cfg)

    # 1. how do you want to pay? (the question nobody else asks first)
    print()
    print(bold("  how should CHODE think?"))
    from .plans import detect_plans
    from . import lifeline
    plans = [p for p in detect_plans() if p[2]]
    options = [("Just make it work (free)", "CHODE picks whatever answers right now: a local model if you have one, else a free keyless model"),
               ("Free key, 2 minutes", "Gemini / Groq / OpenRouter / Mistral / Cerebras free tiers — no card; CHODE opens the page"),
               ("API key I already have", "pay per token — Anthropic, OpenAI, Gemini, xAI, DeepSeek, OpenRouter…"),
               ("Local & free", "Ollama / LM Studio / llama.cpp on this machine — no key, no bill")]
    if plans:
        options.insert(0, ("Subscription I already pay for", "detected: " + ", ".join(p[3].split(' — ')[0] for p in plans)))
    else:
        options.append(("Subscription I already pay for", "none detected yet (install claude / codex / gemini CLI)"))
    pick = choose("pick one", options, default=1)
    label = options[pick][0]
    if label.startswith("Just make it work"):
        cands = lifeline.ladder(dict(cfg, provider="__none__", fallbacks="auto"), exclude=("__none__",))
        if cands:
            provider, model = cands[0]
            cfg["provider"], cfg["model"] = provider, model or ""
            ok(f"using {provider}{(' / ' + model) if model else ''}", PROVIDER_NOTES.get(provider, ""))
            if provider == "pollinations":
                print(dim("    it's free and keyless, so it's slower and rate-limited — perfect to start, upgrade any time with `chode setup`"))
        else:
            warn("nothing reachable right now", "falling back to the keyless free model; check your internet")
            cfg["provider"], cfg["model"] = "pollinations", ""
    elif label.startswith("Free key"):
        opts = lifeline.free_key_options()
        idx = choose("which free tier?", opts, default=1)
        provider = opts[idx][0]
        cfg["provider"] = provider
        url = lifeline.open_signup(provider)
        print(dim(f"    opened {url} in your browser — sign in, create a key, copy it"))
        key = getpass.getpass(f"  paste the key here (hidden) › ").strip()
        if key:
            cfg.setdefault("api_keys", {})[provider] = key
            ok("key stored in ~/.chode/config.json (chmod 600)")
        else:
            warn("no key pasted", f"set {PROVIDERS[provider][2]} later or run chode setup again")
        cfg["model"] = ""
        ok(f"model: {FREE_TIERS_MODEL(provider)}", "the free-tier default; /models to see others")
    elif label.startswith("Subscription"):
        names = [p[0] for p in detect_plans()]
        notes = [(p[0], PROVIDER_NOTES[p[0]] + ("" if p[2] else f"  [not installed: {p[4]}]")) for p in detect_plans()]
        idx = choose("which plan?", notes, default=1)
        provider = names[idx]
        cfg["provider"] = provider
        ok("no API key needed — CHODE drives the CLI and your plan pays")
        cfg["model"] = input(f"  model alias (optional, e.g. opus/sonnet) [{cfg.get('model') or PROVIDERS[provider][3] or 'default'}] › ").strip() or cfg.get("model", "")
    elif label.startswith("Local"):
        up, models = lifeline.ollama_running()
        if lifeline.ollama_installed() and up and not models:
            if yesno("ollama is running but has no models — pull a small free coding model now (~4 GB)?", True):
                okp, msg = lifeline.ollama_pull(lifeline.OLLAMA_STARTERS[0], progress=lambda l: print("\r  " + l[:70], end=""))
                print()
                (ok if okp else bad)(msg)
        elif not lifeline.ollama_installed():
            print(dim("    tip: Ollama is the easiest free local option — https://ollama.com/download, then `ollama pull qwen2.5-coder:7b`"))
        names = ["ollama", "lmstudio", "local"]
        idx = choose("which?", [(n, PROVIDER_NOTES[n]) for n in names], default=1)
        provider = names[idx]
        cfg["provider"] = provider
        ok("local provider — nothing leaves your machine")
        _base_url_step(cfg, provider)
        _model_step(cfg, provider)
    else:
        names = [n for n in PROVIDERS if PROVIDERS[n][0] in ("anthropic", "openai", "azure") and n not in ("ollama", "lmstudio", "local")]
        idx = choose("provider?", [(n, PROVIDER_NOTES[n]) for n in names],
                     default=(names.index(cfg["provider"]) + 1) if cfg.get("provider") in names else 1)
        provider = names[idx]
        cfg["provider"] = provider
        style, default_url, key_env, default_model = PROVIDERS[provider]
        if os.environ.get(key_env):
            ok(f"{key_env} found in environment")
        else:
            print(dim(f"    no {key_env} in environment"))
            key = getpass.getpass(f"  paste API key (hidden; empty = set {key_env} yourself later) › ").strip()
            if key:
                cfg.setdefault("api_keys", {})[provider] = key
                ok("key stored in ~/.chode/config.json (chmod 600)", "env var still takes priority")
        _base_url_step(cfg, provider)
        _model_step(cfg, provider)

    # 2. permission mode
    print()
    midx = choose("permission mode?", [(m, MODE_NOTES[m]) for m in MODES], default=MODES.index(cfg.get("mode", "ask")) + 1)
    cfg["mode"] = MODES[midx]

    # 3. the ORDER stuff
    print()
    cfg.setdefault("order", {})["auto_backup_hours"] = 24 if yesno("auto-backup projects daily to ~/.chode/backups?", True) else 0
    cfg.setdefault("memory", {})["auto_reflect"] = yesno("let CHODE remember things between sessions (persistent memory)?", True)
    ac = choose("auto-commit?", [("off", "you /ship when you want"), ("turn", "a local commit after every change CHODE makes"),
                                 ("session", "one local commit when you quit")], default=1)
    cfg.setdefault("publish", {})["autocommit"] = ["off", "turn", "session"][ac]
    cfg["redact_secrets"] = yesno("redact API-key-looking strings before sending tool output to the model?", cfg.get("redact_secrets", True))

    # 4. optional: tune sampling (temperature / top_p / top_k) — most people never need to
    if PROVIDERS[cfg["provider"]][0] != "plan" and yesno("tune sampling (temperature · top_p · top_k)? most people skip this", False):
        from . import sampling
        sampling.interactive(cfg, LLMClient(cfg))

    save_config(cfg)
    ok(f"saved to {CONFIG_FILE}")
    worked = True
    if yesno("test the connection now?", True):
        worked = ping_test(cfg)
        if not worked and yesno("let CHODE try to fix it (connection doctor)?", True):
            from . import lifeline
            out = lifeline.run_fixer(cfg)
            print("  " + (out or "").strip().replace("\n", "\n  "))
            worked = ping_test(cfg, explain=False)
    if worked:
        print(dim("  tip: `chode import` pulls your skills/rules/MCP servers from Claude Code, Cursor, Codex, VS Code…"
                  " (`chode import --drives` also looks on external drives)\n"))
    else:
        print(dim("  nothing saved is wrong — follow the steps above, or run `chode fix` whenever you like.\n"))


def FREE_TIERS_MODEL(provider):
    from .config import FREE_TIERS
    return FREE_TIERS.get(provider, {}).get("model") or PROVIDERS[provider][3]


def _base_url_step(cfg, provider):
    style, default_url, key_env, default_model = PROVIDERS[provider]
    if provider == "azure":
        print(dim("    azure format: https://RESOURCE.openai.azure.com/openai/deployments/DEPLOYMENT"))
    cur = cfg.get("base_urls", {}).get(provider, default_url)
    url = input(f"  base URL [{cur}] › ").strip()
    if url and url != default_url:
        cfg.setdefault("base_urls", {})[provider] = url
    elif url == default_url and provider in cfg.get("base_urls", {}):
        del cfg["base_urls"][provider]


def _model_step(cfg, provider):
    """Pick a model. Whatever gets typed is normalized ("anthropic/opus-5.5" → claude-opus-5-5) and checked
    against the provider's live list, so a wrong name is corrected here instead of failing later."""
    from . import lifeline
    default_model = PROVIDERS[provider][3]
    model = cfg.get("model") or default_model
    models = None
    if yesno("fetch the model list from the provider?", default=provider in ("ollama", "lmstudio", "local")):
        try:
            with Spinner("fetching models"):
                models = LLMClient(cfg).list_models()
            for i, m in enumerate(models[:30], 1):
                print(f"    {i:2d}. {m}")
            raw = input(f"  model number, or type a name [{model}] › ").strip()
            if raw.isdigit() and 1 <= int(raw) <= min(30, len(models)):
                model = models[int(raw) - 1]
            elif raw:
                model = raw
        except LLMError as e:
            bad("could not fetch models", f"[{e.kind}] {str(e)[:120]}")
            if e.hint:
                print(dim("    → " + e.hint[:200]))
            raw = input(f"  model name [{model}] › ").strip()
            model = raw or model
    else:
        raw = input(f"  model name [{model}] › ").strip()
        model = raw or model
    if model and model != default_model:
        with Spinner("checking the model name"):
            new, note, verified = lifeline.verify_model(cfg, model, available=models)
        if note:
            warn(note) if not verified else ok(note)
        elif verified:
            ok(f"{new} is on {provider}'s model list")
        model = new
    cfg["model"] = "" if model == default_model else model


def ping_test(cfg, explain=True):
    """One-token round trip. On failure prints the full 'what do I do now' block (unless explain=False)."""
    from . import lifeline
    client = LLMClient(cfg)
    t0 = time.time()
    with Spinner("ping"):
        okp, err = client.probe()
    for note in client.fallback_notes:
        info(note)
    if okp:
        ok(f"model responded in {time.time()-t0:.1f}s", f"{client.model or '(default)'} via {client.provider}")
        return True
    bad("connection test failed", f"[{err.kind}] {str(err)[:200]}")
    if explain:
        print()
        print("  " + lifeline.what_now(cfg, err, in_session=False).replace("\n", "\n  "))
        print()
    elif err.hint:
        print(dim("    → " + err.hint[:300]))
    return False


# ---- one-click import -------------------------------------------------------

KIND_COLORS = {"memory": green, "skill": cyan, "command": magenta, "agent": yellow, "mcp": accent_bold,
               "allow": green, "deny": red, "hook": yellow, "extension": dim, "setting": dim}


def run_import(cfg, cwd=None, auto_yes=False, paths=(), drives=None):
    """paths: extra folders to look in (a skill, a skills folder, a copied ~/.claude, a project).
    drives: True = also scan other/external drives · False = don't · None = ask if any are mounted."""
    from .importer import scan, apply, vscode_extension_list, external_volumes, volume_label
    print(bold("\n  🥤 the gulp — import your gear from every other coding agent\n"))
    print(dim("  scanning Claude Code · Codex · Gemini CLI · Antigravity · Cursor · Windsurf · VS Code · Cline · Roo · Kilo\n"
              "           Continue · Copilot · OpenCode · Zed · Kiro · Amp · Junie · Aider · OpenClaw · Hermes …"))
    paths = [p for p in (paths or []) if p]
    if paths:
        print(dim("  plus: " + ", ".join(paths)))
    vols = external_volumes()
    if vols and drives is None and not auto_yes:
        labels = ", ".join(volume_label(v) for v in vols[:6]) + (" …" if len(vols) > 6 else "")
        drives = yesno(f"also look on {len(vols)} other drive(s) for skills and agent folders? ({labels}) — takes a few seconds each", False)
    use_vols = vols if drives else []
    if use_vols:
        print(dim("  other drives: " + ", ".join(volume_label(v) for v in use_vols)))
    elif vols and drives is None:
        print(dim(f"  ({len(vols)} other drive(s) mounted — `chode import --drives` or `/import --drives` to include them)"))
    with Spinner("scanning"):
        items = scan(cfg, cwd, paths=paths, volumes=use_vols)
        exe, exts = vscode_extension_list()
    if exe and exts:
        from .importer import KNOWN_AI_EXTENSIONS, Item
        ai = [(n, KNOWN_AI_EXTENSIONS[n]) for n in exts if n in KNOWN_AI_EXTENSIONS]
        if ai and not any(i.kind == "extension" for i in items):
            items.append(Item("extension", f"{len(ai)} AI extension(s)", f"{exe} CLI", ai, ", ".join(l for _, l in ai)[:70]))
    if not items:
        print(dim("\n  nothing found. (looked for rules, SKILL.md folders, commands, agents, mcpServers, permissions, hooks)"))
        print(dim("  stuff somewhere else? `chode import <folder>` (a skill, a skills folder, a copied ~/.claude, a project)"
                  + ("" if use_vols else " · `chode import --drives` scans other drives") + "\n"))
        return []
    print()
    agents = {}
    for it in items:
        agents[it.agent] = agents.get(it.agent, 0) + 1
    print("  found: " + dim(" · ".join(f"{a} ×{n}" for a, n in sorted(agents.items()))))
    print()
    for i, it in enumerate(items, 1):
        tag = KIND_COLORS.get(it.kind, dim)(f"{it.kind:<9}")
        flag = yellow(" [have]") if it.dup else ""
        print(f"  {i:3d}. {tag} {bold(it.name[:40])}{flag}  {dim(f'({it.agent}) ' + str(it.note)[:60])}")
    if auto_yes:
        picked = {i for i, it in enumerate(items) if not it.dup}
    else:
        try:
            raw = input(f"\n  import which? (e.g. 1,3-5 / all / new = everything you don't have / empty = cancel) › ")
        except (EOFError, KeyboardInterrupt):
            print()
            return []
        if raw.strip().lower() == "new":
            picked = {i for i, it in enumerate(items) if not it.dup}
        else:
            picked = parse_selection(raw, len(items))
    if not picked:
        print(dim("  cancelled\n"))
        return []
    chosen = [items[i] for i in sorted(picked)]
    report = apply(chosen, cfg, cwd)
    print()
    for line in report:
        color = green if line.startswith("✓") else (dim if line.startswith("=") else (cyan if line.startswith("ℹ") else red))
        print("  " + color(line))
    print(dim("\n  done. nothing was removed from the other tools — they keep working too.\n"))
    return report


# ---- plans --------------------------------------------------------------------

def run_plans(cfg):
    from .plans import detect_plans
    print(bold("\n  💳 Plan Bridge — ride the subscription you already pay for\n"))
    found = []
    for prov, cli, path, label, hint in detect_plans():
        if cli is None:
            continue
        if path:
            ok(f"{label}", f"{cli} → {path}")
            found.append(prov)
        else:
            warn(f"{label} not installed", hint)
    print(dim("\n  how it works: CHODE runs the vendor CLI in non-interactive mode with ITSELF attached as an MCP server,\n"
              "  so the model thinks on your plan and acts through CHODE's tools (permissions, memory, ORDER, ledger).\n"
              "  `chode ride claude` does the opposite: opens their TUI with CHODE's tools mounted.\n"))
    if cfg.get("provider", "").endswith("-plan"):
        info(f"current provider: {cfg['provider']}")
        return
    if found and yesno(f"switch provider to {found[0]} now?", False):
        cfg["provider"] = found[0]
        cfg["model"] = ""
        save_config(cfg)
        ok(f"provider → {found[0]}", "switch back any time with /provider")


# ---- ORDER CLI ----------------------------------------------------------------

def run_order_cli(cfg, argv):
    from .order import audit, scaffold, tidy_report, backup, list_backups, status_line, about_prompt
    import json as _json
    if argv and argv[0] == "--json":
        print(_json.dumps(audit(), indent=2, default=str))
        return
    line, a = status_line(cfg=cfg)
    print(bold(f"\n  📐 ORDER — {a['project']['name']}") + dim(f"  [{a['project']['type']}] {a['project']['files']} files"))
    print(f"  {accent_bold(line)}\n")
    for ch in a["checks"]:
        (ok if ch["ok"] else bad)(ch["label"], ch["detail"] or (ch["how"] if not ch["ok"] else ""))
    tips = tidy_report()
    if tips:
        print()
        for f, t in tips[:12]:
            warn(f, t)
    if argv and argv[0] in ("fix", "apply", "--fix"):
        res = scaffold(apply=True)
        print()
        for cr in res["created"]:
            ok(cr)
        if res["needs_model"]:
            print(dim(f"\n  these need the model: {', '.join(res['needs_model'])} — starting a one-shot run…\n"))
            from .repl import start_chat
            start_chat(cfg, None, oneshot=about_prompt(res["project"], audit()))
        return
    print(dim("\n  chode order fix   → scaffold the essentials, then let the model write README/ABOUT/tests"))
    print(dim("  chode backup      → snapshot now · chode backup list\n"))


def run_backup_cli(cfg, argv):
    from .order import backup, list_backups, restore_backup
    if argv and argv[0] == "list":
        bl = list_backups()
        if not bl:
            print(dim("  no backups yet"))
        for i, b in enumerate(bl, 1):
            print(f"  {i}. {time.strftime('%Y-%m-%d %H:%M', time.localtime(b['ts']))}  {b['files']} files  {b['mb']} MB  {dim(b['note'])}")
        return
    if argv and argv[0] == "restore":
        bl = list_backups()
        idx = int(argv[1]) - 1 if len(argv) > 1 and argv[1].isdigit() else 0
        if not bl or idx >= len(bl):
            bad("no such backup")
            return
        dest = Path.cwd().parent / (Path.cwd().name + "-restored-" + time.strftime("%H%M%S"))
        ok(f"restored to {restore_backup(bl[idx]['path'], dest)}", "never overwrites your working tree")
        return
    r = backup(cfg=cfg, note=" ".join(argv) or "manual")
    if r.get("ok"):
        ok(f"{r['files']} files ({r['mb']} MB) → {r['path']}")
    else:
        warn(r.get("reason", "skipped"))
