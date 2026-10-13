"""`chode doctor` (environment audit) and `chode health` (live checks)."""
import json
import platform
import shutil
import sys

import requests

from .config import PROVIDERS, api_key_for
from .llm import LLMClient, LLMError
from .mcp import McpManager
from .paths import BACKUP_DIR, CONFIG_DIR, CONFIG_FILE, MEMORY_DIR, SESSIONS_DIR
from .skills import discover_skills
from .ui import USE_COLOR, Spinner, bad, bold, dim, green, ok, red, term_width, warn


def run_doctor(cfg):
    print(bold("\n  🩺 CHODE doctor\n"))
    py = platform.python_version()
    (ok if sys.version_info >= (3, 9) else bad)(f"Python {py}", "" if sys.version_info >= (3, 9) else "need ≥ 3.9")
    ok(f"requests {requests.__version__}")
    try:
        import PIL
        ok(f"Pillow {PIL.__version__}", "PNG banners enabled")
    except ImportError:
        warn("Pillow not installed", "pip install pillow → PNG banners (SVG works without it)")
    cols = term_width(0)
    if cols:
        (ok if cols >= 76 else warn)(f"terminal {cols} cols", "" if cols >= 76 else "under 76 cols: intro animation falls back to static")
    ok("color output") if USE_COLOR else warn("no color support detected", "set TERM, unset NO_COLOR")

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / ".w").write_text("x")
        (CONFIG_DIR / ".w").unlink()
        ok(f"{CONFIG_DIR} writable")
    except Exception as e:
        bad(f"{CONFIG_DIR} not writable", str(e))
    if CONFIG_FILE.exists():
        try:
            json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            ok("config.json parses")
        except Exception as e:
            bad("config.json is broken", f"{e} — fix or delete {CONFIG_FILE}")
        try:
            import os
            mode = oct(CONFIG_FILE.stat().st_mode & 0o777)
            (ok if os.name == "nt" or mode == "0o600" else warn)(f"config.json permissions {mode}",
                                                                 "" if mode == "0o600" or os.name == "nt" else "chmod 600 ~/.chode/config.json (it may hold API keys)")
        except Exception:
            pass
    else:
        warn("no config yet", "run: chode setup")

    provider = cfg.get("provider", "?")
    style = PROVIDERS.get(provider, ("", "", "", ""))[0]
    client = LLMClient(cfg)
    if style == "plan":
        from .plans import PLAN_CLIS, _which
        cli = PLAN_CLIS.get(provider, (None,))[0]
        if cli:
            (ok if _which(cli) else bad)(f"plan bridge: {cli} CLI", _which(cli) or PLAN_CLIS[provider][2])
        else:
            (ok if cfg.get("plans", {}).get("custom", {}).get("command") else bad)("custom plan command", cfg.get("plans", {}).get("custom", {}).get("command", "not set"))
    else:
        key_env = PROVIDERS.get(provider, ("", "", "", ""))[2]
        if key_env:
            if api_key_for(cfg, provider):
                import os
                ok(f"API key for {provider}", "env" if os.environ.get(key_env) else "config file")
            else:
                bad(f"no API key for {provider}", f"export {key_env}=… or run chode setup")
        try:
            with Spinner("pinging endpoint"):
                n = len(client.list_models())
            ok(f"{provider} endpoint reachable", f"{client.base_url} · {n} models")
        except LLMError as e:
            bad(f"{provider} endpoint unreachable", str(e)[:140])
    if not client.model:
        bad("no model set", "chode setup, or /model <name>")
    else:
        ok(f"model: {client.model}")

    for tool, why in (("git", "repo context, /ship, /release, skill installs"),
                      ("gh", "creates GitHub repos & releases (optional)"),
                      ("node", "many MCP servers run via npx"),
                      ("npx", "runs @modelcontextprotocol/* servers"),
                      ("claude", "Plan Bridge: Claude Pro/Max"),
                      ("codex", "Plan Bridge: ChatGPT Plus/Pro"),
                      ("gemini", "Plan Bridge: Google AI Pro/Ultra"),
                      ("ffmpeg", "terminal splash-video renderer (optional)")):
        if shutil.which(tool) or shutil.which(tool + ".cmd"):
            ok(f"{tool} installed", why)
        else:
            (warn if tool in ("git", "node", "npx") else lambda m, d="": print(f"  {dim('·')} {m}" + (dim('  ' + d) if d else '')))(f"{tool} not found", why)

    skills = discover_skills()
    if skills:
        ok(f"{len(skills)} skill(s) installed")
        for s in skills.values():
            if s.description == "(no description)":
                warn(f"skill '{s.name}' has no description", "add frontmatter — the model relies on it")
    else:
        warn("no skills installed", "chode import pulls them from other agents; /skills add installs")

    servers = cfg.get("mcp_servers", {})
    if servers:
        for name, spec in servers.items():
            transport = spec.get("transport") or spec.get("type") or ("http" if spec.get("url") else "stdio")
            if transport == "stdio":
                cmd = spec.get("command", "")
                found = shutil.which(cmd) or shutil.which(cmd + ".cmd")
                (ok if found else bad)(f"mcp '{name}' ({cmd})", "" if found else f"command '{cmd}' not on PATH")
            else:
                (ok if str(spec.get("url", "")).startswith("http") else bad)(f"mcp '{name}' (http)", spec.get("url", "missing url"))
    else:
        print(f"  {dim('·')} no MCP servers configured" + dim("  optional — chode import finds them"))

    try:
        n_mem = sum(1 for f in MEMORY_DIR.glob("*.jsonl") for _ in f.open(encoding="utf-8")) if MEMORY_DIR.is_dir() else 0
        ok(f"memory: {n_mem} entries", str(MEMORY_DIR))
    except Exception:
        pass
    if BACKUP_DIR.is_dir():
        total = sum(f.stat().st_size for f in BACKUP_DIR.rglob("*.tar.gz"))
        ok(f"backups using {total/1e6:.0f} MB", str(BACKUP_DIR))
    if SESSIONS_DIR.is_dir():
        total = sum(f.stat().st_size for f in SESSIONS_DIR.rglob("*.json"))
        if total > 50_000_000:
            warn(f"sessions using {total/1e6:.0f} MB", f"prune {SESSIONS_DIR}")
    print()


def run_health(cfg):
    print(bold("\n  ❤️  CHODE health check\n"))
    healthy = True
    client = LLMClient(cfg)
    from .wizard import ping_test
    if client.api_style != "plan":
        import time
        t0 = time.time()
        try:
            with Spinner("endpoint"):
                models = client.list_models()
            ok(f"endpoint up ({(time.time()-t0)*1000:.0f} ms)", f"{client.base_url} · {len(models)} models")
        except LLMError as e:
            bad("endpoint check failed", str(e)[:160])
            healthy = False
    if healthy:
        healthy = ping_test(cfg) and healthy
    servers = cfg.get("mcp_servers", {})
    if servers:
        mgr = McpManager(cfg)
        with Spinner("mcp servers"):
            mgr.start_all(quiet=True)
        for s in mgr.servers.values():
            if s.error:
                bad(f"mcp '{s.name}'", s.error)
                healthy = False
            else:
                ok(f"mcp '{s.name}'", f"{len(s.tools)} tools")
        mgr.stop_all()
    print(f"\n  {green(bold('all systems thicc 💪')) if healthy else red(bold('degraded — run: chode doctor'))}\n")
    return healthy
