"""Publish: /ship (commit + push), autocommit, releases, GitHub + Hugging Face.

Everyone has GitHub. Nobody likes writing commit messages. CHODE writes the
message, refuses to commit secrets, pushes, and can create the remote repo
and a tagged release — one command.
"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

from . import conscience
from .security import scan_for_secrets


def git(args, cwd=None, timeout=120, check=False):
    try:
        r = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=str(cwd or Path.cwd()),
                           timeout=timeout, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return 127, "git is not installed"
    except subprocess.TimeoutExpired:
        return 124, "git timed out"
    out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    return r.returncode, out.strip()


def is_repo(cwd=None):
    return git(["rev-parse", "--is-inside-work-tree"], cwd)[1] == "true"


def current_branch(cwd=None):
    return git(["branch", "--show-current"], cwd)[1] or "HEAD"


def remote_url(cwd=None, name="origin"):
    rc, out = git(["remote", "get-url", name], cwd)
    return out if rc == 0 else ""


def changed_files(cwd=None):
    rc, out = git(["status", "--porcelain"], cwd)
    return [l[3:] for l in out.splitlines() if l.strip()] if rc == 0 else []


def staged_diff(cwd=None, max_chars=12000):
    rc, stat = git(["diff", "--cached", "--stat"], cwd)
    rc2, diff = git(["diff", "--cached", "--no-color", "-U2"], cwd)
    if len(diff) > max_chars:
        diff = diff[:max_chars] + f"\n… [diff truncated, {len(diff)-max_chars} more chars]"
    return stat, diff


def staged_secret_hits(cwd=None):
    rc, diff = git(["diff", "--cached", "--no-color", "-U0"], cwd)
    added = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    return scan_for_secrets(added)


COMMIT_PROMPT = """Write a git commit message for these staged changes.
Format: Conventional Commits — `type(scope): summary` on line 1 (≤72 chars, imperative, no period),
blank line, then 1-5 bullet lines explaining WHAT changed and WHY (skip bullets for trivial changes).
Types: feat, fix, docs, refactor, test, chore, perf, build, ci, style.
Reply with ONLY the message, no quotes, no code fence.

--- diffstat ---
{stat}

--- diff ---
{diff}
"""


def ship(cwd=None, cfg=None, message=None, push=True, ask_model=None, confirm=None, force=False, add_all=True):
    """Stage → secret scan → commit (model-written message) → push. Returns a human report."""
    cwd = Path(cwd or Path.cwd())
    cfg = cfg or {}
    pub = cfg.get("publish", {})
    if not is_repo(cwd):
        if confirm and not confirm("not a git repo yet — git init?"):
            return "aborted: not a git repository"
        rc, out = git(["init", "-q"], cwd)
        if rc != 0:
            return f"git init failed: {out}"
    if add_all:
        git(["add", "-A"], cwd)
    rc, staged = git(["diff", "--cached", "--name-only"], cwd)
    if not staged.strip():
        return "nothing to commit — working tree clean"
    hits = staged_secret_hits(cwd)
    if hits and not force:
        conscience.log("secret_in_commit", detail="; ".join(f"{k}:{p}" for k, p in hits[:5]))
        git(["reset", "-q"], cwd)
        return ("🛑 refused: the staged changes contain secret-looking values:\n  " +
                "\n  ".join(f"{k}  {p}" for k, p in hits[:8]) +
                "\n  Move them to .env (gitignored) and rotate the key. Use /ship --force to override (not recommended).")
    if not message:
        stat, diff = staged_diff(cwd)
        if ask_model:
            try:
                message = (ask_model(COMMIT_PROMPT.format(stat=stat, diff=diff)) or "").strip().strip("`").strip()
            except Exception:
                message = ""
        if not message:
            n = len(staged.splitlines())
            message = f"chore: update {n} file{'s' if n != 1 else ''}\n\n" + "\n".join(f"- {f}" for f in staged.splitlines()[:10])
    message = _clean_message(message)
    args = ["commit", "-q", "-m", message]
    if pub.get("sign_off"):
        args.append("--signoff")
    rc, out = git(args, cwd)
    if rc != 0:
        return f"commit failed: {out}"
    report = [f"✓ committed on {current_branch(cwd)}: {message.splitlines()[0]}"]
    if not push:
        return "\n".join(report)
    remote = pub.get("remote", "origin")
    if not remote_url(cwd, remote):
        created = _maybe_create_remote(cwd, cfg, confirm)
        report.append(created)
        if not remote_url(cwd, remote):
            return "\n".join(report + ["(no remote — commit is local only; add one with `git remote add origin <url>`)"])
    branch = current_branch(cwd)
    rc, out = git(["push", "-u", remote, branch], cwd, timeout=300)
    if rc != 0:
        return "\n".join(report + [f"push failed: {out[-800:]}"])
    url = remote_url(cwd, remote)
    report.append(f"✓ pushed {branch} → {remote} ({_pretty_remote(url)})")
    hf = pub.get("huggingface_repo")
    if hf:
        report.append(huggingface_push(cwd, hf))
    return "\n".join(report)


def _clean_message(msg):
    msg = msg.strip()
    if msg.startswith("```"):
        msg = re.sub(r"^```[a-z]*\n|\n```$", "", msg).strip()
    lines = [l.rstrip() for l in msg.splitlines()]
    if lines and len(lines[0]) > 72:
        lines[0] = lines[0][:69] + "…"
    return "\n".join(lines).strip()


def _pretty_remote(url):
    url = url.strip()
    m = re.match(r"(?:git@|https://)([^/:]+)[:/](.+?)(?:\.git)?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else url


def autocommit(cwd=None, cfg=None, summary=""):
    """Quiet local commit after an agent turn that changed files (never pushes)."""
    cwd = Path(cwd or Path.cwd())
    if not is_repo(cwd):
        return None
    if not changed_files(cwd):
        return None
    git(["add", "-A"], cwd)
    hits = staged_secret_hits(cwd)
    if hits:
        git(["reset", "-q"], cwd)
        conscience.log("secret_in_commit", detail="autocommit skipped: " + hits[0][0])
        return "autocommit skipped: secrets detected in changes"
    summary = " ".join((summary or "update").split())[:60]
    rc, out = git(["commit", "-q", "-m", f"chode: {summary}"], cwd)
    return f"autocommitted: {summary}" if rc == 0 else None


# --------------------------------------------------------------------------
# Remote creation (GitHub via gh or token)
# --------------------------------------------------------------------------

def _maybe_create_remote(cwd, cfg, confirm):
    name = Path(cwd).resolve().name
    if confirm and not confirm(f"no remote yet — create a GitHub repo '{name}'?"):
        return "(no remote created)"
    private = confirm("private repo?", default=True) if confirm else True
    return create_github_repo(cwd, name, private=private)


def create_github_repo(cwd, name, private=True, description=""):
    gh = shutil.which("gh")
    if gh:
        vis = "--private" if private else "--public"
        rc = subprocess.run([gh, "repo", "create", name, vis, "--source", str(cwd), "--remote", "origin",
                             "--description", description or f"{name} — kept in ORDER by chode"],
                            capture_output=True, text=True, cwd=str(cwd))
        if rc.returncode == 0:
            return f"✓ created GitHub repo {name} ({'private' if private else 'public'}) via gh"
        err = (rc.stderr or rc.stdout).strip()[-300:]
        if "already exists" not in err:
            return f"gh repo create failed: {err}"
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return ("no `gh` CLI and no GITHUB_TOKEN — create the repo on github.com, then:\n"
                f"  git remote add origin https://github.com/<you>/{name}.git")
    r = requests.post("https://api.github.com/user/repos",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"name": name, "private": private, "description": description}, timeout=30)
    if r.status_code not in (200, 201):
        return f"GitHub API refused ({r.status_code}): {r.text[:200]}"
    data = r.json()
    git(["remote", "add", "origin", data.get("clone_url") or data.get("html_url")], cwd)
    return f"✓ created GitHub repo {data.get('full_name')} ({'private' if private else 'public'})"


# --------------------------------------------------------------------------
# Hugging Face
# --------------------------------------------------------------------------

def huggingface_push(cwd, repo_id, repo_type="model"):
    cli = shutil.which("hf") or shutil.which("huggingface-cli")
    if not cli:
        return "huggingface: install `pip install huggingface_hub` and run `hf auth login` to enable pushes"
    args = [cli, "upload", repo_id, ".", ".", "--repo-type", repo_type, "--exclude", ".git/*", "--exclude", ".chode/*"]
    r = subprocess.run(args, capture_output=True, text=True, cwd=str(cwd))
    if r.returncode == 0:
        return f"✓ uploaded to huggingface.co/{repo_id}"
    return f"huggingface upload failed: {(r.stderr or r.stdout).strip()[-300:]}"


# --------------------------------------------------------------------------
# Releases
# --------------------------------------------------------------------------

def last_tag(cwd=None):
    rc, out = git(["describe", "--tags", "--abbrev=0"], cwd)
    return out if rc == 0 else ""


def commits_since(cwd=None, ref=""):
    rng = f"{ref}..HEAD" if ref else "HEAD"
    rc, out = git(["log", rng, "--pretty=format:%s", "--no-merges", "-n", "200"], cwd)
    return out.splitlines() if rc == 0 else []


def bump_version_files(cwd, version):
    cwd = Path(cwd)
    changed = []
    v = version.lstrip("v")
    for rel in ("pyproject.toml", "setup.py", "Cargo.toml"):
        p = cwd / rel
        if p.exists():
            txt = p.read_text(encoding="utf-8")
            new = re.sub(r'(?m)^(version\s*=\s*")[^"]+(")', rf'\g<1>{v}\2', txt, count=1)
            if new != txt:
                p.write_text(new, encoding="utf-8"); changed.append(rel)
    p = cwd / "package.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("version") != v:
                data["version"] = v
                p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8"); changed.append("package.json")
        except Exception:
            pass
    for init in list(cwd.glob("*/__init__.py"))[:5]:
        txt = init.read_text(encoding="utf-8")
        new = re.sub(r'(?m)^(VERSION\s*=\s*")[^"]+(")', rf'\g<1>{v}\2', txt, count=1)
        new = re.sub(r'(?m)^(__version__\s*=\s*")[^"]+(")', rf'\g<1>{v}\2', new, count=1)
        if new != txt:
            init.write_text(new, encoding="utf-8"); changed.append(str(init.relative_to(cwd)))
    return changed


def _categorize(commits):
    buckets = {"Added": [], "Fixed": [], "Changed": [], "Docs": [], "Other": []}
    for c in commits:
        low = c.lower()
        if low.startswith("feat"):
            buckets["Added"].append(c)
        elif low.startswith("fix"):
            buckets["Fixed"].append(c)
        elif low.startswith(("refactor", "perf", "chore", "build", "ci")):
            buckets["Changed"].append(c)
        elif low.startswith("docs"):
            buckets["Docs"].append(c)
        else:
            buckets["Other"].append(c)
    return {k: v for k, v in buckets.items() if v}


def release_notes(cwd, version, ask_model=None):
    prev = last_tag(cwd)
    commits = commits_since(cwd, prev)
    if ask_model and commits:
        try:
            text = ask_model(
                f"Write release notes for version {version} from these commit subjects (previous tag: {prev or 'none'}).\n"
                "Markdown, Keep-a-Changelog headings (Added/Changed/Fixed), 1 line per item, user-facing language, "
                "no fluff. Start with a one-sentence summary.\n\n" + "\n".join(f"- {c}" for c in commits[:120]))
            if text and text.strip():
                return text.strip()
        except Exception:
            pass
    cats = _categorize(commits)
    lines = [f"Release {version}" + (f" — changes since {prev}" if prev else ""), ""]
    for k, items in cats.items():
        lines.append(f"### {k}")
        lines += [f"- {c}" for c in items]
        lines.append("")
    return "\n".join(lines).strip() or f"Release {version}"


def update_changelog(cwd, version, notes):
    p = Path(cwd) / "CHANGELOG.md"
    date = time.strftime("%Y-%m-%d")
    section = f"## [{version.lstrip('v')}] - {date}\n\n{notes}\n\n"
    if p.exists():
        txt = p.read_text(encoding="utf-8")
        if f"## [{version.lstrip('v')}]" in txt:
            return False
        if "## [Unreleased]" in txt:
            txt = txt.replace("## [Unreleased]\n", "## [Unreleased]\n\n" + section, 1)
        else:
            parts = txt.split("\n## ", 1)
            txt = parts[0].rstrip() + "\n\n" + section + ("## " + parts[1] if len(parts) > 1 else "")
        p.write_text(txt, encoding="utf-8")
    else:
        p.write_text("# Changelog\n\n## [Unreleased]\n\n" + section, encoding="utf-8")
    return True


def release(cwd=None, cfg=None, version="", notes=None, ask_model=None, confirm=None, push=True, draft=False):
    cwd = Path(cwd or Path.cwd())
    if not is_repo(cwd):
        return "not a git repository"
    if not version:
        return "usage: /release v1.2.3"
    tag = version if version.startswith("v") else "v" + version
    report = []
    changed = bump_version_files(cwd, tag)
    if changed:
        report.append("✓ bumped version in " + ", ".join(changed))
    notes = notes or release_notes(cwd, tag, ask_model)
    if update_changelog(cwd, tag, notes):
        report.append("✓ CHANGELOG.md updated")
    if changed_files(cwd):
        git(["add", "-A"], cwd)
        hits = staged_secret_hits(cwd)
        if hits:
            git(["reset", "-q"], cwd)
            return "🛑 refused: secrets in the release commit — fix and retry"
        git(["commit", "-q", "-m", f"chore(release): {tag}"], cwd)
        report.append(f"✓ committed release {tag}")
    rc, out = git(["tag", "-a", tag, "-m", f"Release {tag}"], cwd)
    if rc != 0:
        return "\n".join(report + [f"tag failed: {out}"])
    report.append(f"✓ tagged {tag}")
    if push:
        remote = (cfg or {}).get("publish", {}).get("remote", "origin")
        rc, out = git(["push", remote, current_branch(cwd), "--follow-tags"], cwd, timeout=300)
        report.append("✓ pushed with tags" if rc == 0 else f"push failed: {out[-300:]}")
        gh = shutil.which("gh")
        if gh and rc == 0:
            args = [gh, "release", "create", tag, "--title", f"{tag}", "--notes", notes]
            if draft:
                args.append("--draft")
            r = subprocess.run(args, capture_output=True, text=True, cwd=str(cwd))
            report.append("✓ GitHub release created" if r.returncode == 0 else
                          f"gh release failed: {(r.stderr or r.stdout).strip()[-200:]}")
        elif rc == 0:
            report.append("(install `gh` to create the GitHub release automatically; the tag is pushed)")
    return "\n".join(report)
