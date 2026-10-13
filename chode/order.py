"""ORDER — Organize · Record · Document · Export · Release.

CHODE keeps every repo in order without being asked: it audits the project,
scaffolds the boring-but-essential files, snapshots backups, and hands the
judgment-heavy pieces (README, ABOUT.md with story + marketing + social posts)
to the model via the `repo-order` skill.
"""
import json
import os
import re
import subprocess
import tarfile
import time
from pathlib import Path

from .paths import BACKUP_DIR, MEMORY_FILENAME, PROJECT_DIRNAME, SKIP_DIRS
from .security import scan_for_secrets
from .session import project_key

MANIFESTS = [
    ("pyproject.toml", "python"), ("setup.py", "python"), ("requirements.txt", "python"), ("Pipfile", "python"),
    ("package.json", "node"), ("deno.json", "deno"), ("bun.lockb", "node"),
    ("Cargo.toml", "rust"), ("go.mod", "go"), ("pom.xml", "java"), ("build.gradle", "java"),
    ("build.gradle.kts", "kotlin"), ("Gemfile", "ruby"), ("composer.json", "php"), ("Package.swift", "swift"),
    ("pubspec.yaml", "dart"), ("mix.exs", "elixir"), ("CMakeLists.txt", "cpp"), ("Makefile", "make"),
    ("Dockerfile", "docker"), ("*.csproj", "dotnet"), ("*.sln", "dotnet"), ("*.gemspec", "ruby"),
]
EXT_LANG = {".py": "python", ".js": "node", ".ts": "typescript", ".tsx": "typescript", ".jsx": "node",
            ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".rb": "ruby", ".php": "php",
            ".swift": "swift", ".dart": "dart", ".ex": "elixir", ".c": "c", ".cpp": "cpp", ".cs": "dotnet",
            ".html": "web", ".css": "web", ".sh": "shell", ".lua": "lua", ".r": "r", ".jl": "julia"}

GITIGNORE = {
    "common": ["# chode local state", ".chode/", "", "# OS", ".DS_Store", "Thumbs.db", "", "# editors", ".idea/", ".vscode/*",
               "!.vscode/settings.json", "!.vscode/extensions.json", "*.swp", "", "# env & secrets", ".env", ".env.*",
               "!.env.example", "*.pem", "*.key", "", "# logs", "*.log", "logs/"],
    "python": ["__pycache__/", "*.py[cod]", ".venv/", "venv/", "env/", "dist/", "build/", "*.egg-info/",
               ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", ".coverage", "htmlcov/"],
    "node": ["node_modules/", "dist/", "build/", ".next/", ".nuxt/", "coverage/", "*.tsbuildinfo", ".turbo/"],
    "typescript": ["node_modules/", "dist/", "build/", "coverage/", "*.tsbuildinfo"],
    "rust": ["target/", "Cargo.lock.bak"],
    "go": ["bin/", "*.test", "*.out"],
    "java": ["target/", "build/", "*.class", ".gradle/"],
    "kotlin": ["build/", ".gradle/", "*.class"],
    "ruby": ["vendor/bundle/", ".bundle/", "tmp/"],
    "php": ["vendor/"],
    "dotnet": ["bin/", "obj/", "*.user"],
    "dart": [".dart_tool/", "build/", ".packages"],
    "elixir": ["_build/", "deps/", "*.ez"],
    "cpp": ["build/", "*.o", "*.obj", "*.exe", "cmake-build-*/"],
    "c": ["build/", "*.o", "*.exe"],
    "swift": [".build/", "*.xcodeproj/xcuserdata/", "DerivedData/"],
}

MIT = """MIT License

Copyright (c) {year} {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

CHANGELOG = """# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Project put in ORDER by [CHODE](https://github.com/chchchadzilla/chode).
"""

DOCS_README = """# docs

Documentation for {name}.

- [README](../README.md) — start here
- [ABOUT](../ABOUT.md) — the story, who it's for, and ready-to-post marketing copy
- [CHANGELOG](../CHANGELOG.md) — what changed, when
"""

CI_TEMPLATES = {
    "python": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {{ python-version: "3.12" }}
      - run: pip install -e . || pip install -r requirements.txt || true
      - run: pip install pytest && (pytest -q || python -c "import {module}")
""",
    "node": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {{ node-version: 22 }}
      - run: npm ci || npm install
      - run: npm test --if-present
""",
    "generic": """name: ci
on: [push, pull_request]
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "add a real test step for {name}"
""",
}


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def _git(args, cwd, timeout=10):
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=str(cwd), timeout=timeout)
        return r.returncode, (r.stdout or "").strip()
    except Exception:
        return 1, ""


def detect_project(cwd=None):
    cwd = Path(cwd or Path.cwd()).resolve()
    langs = {}
    manifests = []
    for pattern, lang in MANIFESTS:
        hits = list(cwd.glob(pattern)) if "*" in pattern else ([cwd / pattern] if (cwd / pattern).exists() else [])
        if hits:
            manifests.append(pattern)
            langs[lang] = langs.get(lang, 0) + 5
    n_files, size = 0, 0
    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            n_files += 1
            p = Path(dirpath) / fn
            try:
                size += p.stat().st_size
            except Exception:
                pass
            lang = EXT_LANG.get(p.suffix.lower())
            if lang:
                langs[lang] = langs.get(lang, 0) + 1
        if n_files > 20000:
            break
    primary = max(langs, key=langs.get) if langs else "generic"
    name = cwd.name
    desc = ""
    pj = cwd / "package.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            name = data.get("name") or name
            desc = data.get("description") or ""
        except Exception:
            pass
    pp = cwd / "pyproject.toml"
    if pp.exists():
        try:
            txt = pp.read_text(encoding="utf-8")
            m = re.search(r'^name\s*=\s*"([^"]+)"', txt, re.M)
            if m:
                name = m.group(1)
            m = re.search(r'^description\s*=\s*"([^"]+)"', txt, re.M)
            if m:
                desc = m.group(1)
        except Exception:
            pass
    test_cmd = {"python": "pytest -q", "node": "npm test", "typescript": "npm test", "rust": "cargo test",
                "go": "go test ./...", "java": "mvn test", "kotlin": "./gradlew test", "ruby": "bundle exec rspec",
                "dotnet": "dotnet test", "dart": "dart test", "elixir": "mix test"}.get(primary, "")
    return {"name": name, "description": desc, "type": primary, "langs": sorted(langs, key=langs.get, reverse=True),
            "manifests": manifests, "files": n_files, "size_mb": round(size / 1e6, 1), "test_cmd": test_cmd,
            "cwd": str(cwd), "git": (cwd / ".git").exists()}


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

def _exists_any(cwd, names):
    for n in names:
        if "*" in n:
            if list(cwd.glob(n)):
                return True
        elif (cwd / n).exists():
            return True
    return False


def _has_real_content(path, min_chars=120):
    try:
        return path.exists() and len(path.read_text(errors="replace", encoding="utf-8").strip()) >= min_chars
    except Exception:
        return False


def audit(cwd=None):
    cwd = Path(cwd or Path.cwd()).resolve()
    proj = detect_project(cwd)
    checks = []

    def add(key, label, ok, weight, detail="", fixable=False, how=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "weight": weight, "detail": detail,
                       "fixable": fixable, "how": how})

    add("readme", "README.md with real content", _has_real_content(cwd / "README.md", 300), 14,
        fixable=True, how="model writes it (repo-order skill)")
    add("about", "ABOUT.md (story + marketing + social posts)", _has_real_content(cwd / "ABOUT.md", 300), 10,
        fixable=True, how="model writes it (repo-order skill)")
    add("license", "LICENSE", _exists_any(cwd, ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]), 8,
        fixable=True, how="MIT by default")
    add("gitignore", ".gitignore", (cwd / ".gitignore").exists(), 6, fixable=True)
    add("changelog", "CHANGELOG.md", _exists_any(cwd, ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"]), 6, fixable=True)
    add("docs", "docs/ folder", (cwd / "docs").is_dir(), 4, fixable=True)
    add("tests", "tests", _exists_any(cwd, ["tests", "test", "spec", "__tests__", "*_test.go", "src/**/*.test.*"]), 10,
        fixable=True, how="model adds a smoke test")
    add("ci", "CI workflow", _exists_any(cwd, [".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml",
                                               ".circleci/config.yml"]), 6, fixable=True)
    add("git", "git repository", proj["git"], 8, fixable=True, how="git init")
    remote = _git(["remote", "get-url", "origin"], cwd)[1] if proj["git"] else ""
    add("remote", "remote (GitHub/GitLab/HF…)", bool(remote), 6, detail=remote, fixable=True, how="/ship creates one")
    dirty = _git(["status", "--porcelain"], cwd)[1] if proj["git"] else ""
    n_dirty = len(dirty.splitlines()) if dirty else 0
    add("clean", "everything committed", proj["git"] and n_dirty == 0, 6,
        detail=f"{n_dirty} uncommitted file(s)" if n_dirty else "", fixable=True, how="/ship")
    add("memory", f"{MEMORY_FILENAME} / AGENTS.md project memory",
        _exists_any(cwd, [MEMORY_FILENAME, "AGENTS.md", "CLAUDE.md"]), 6, fixable=True, how="/init")
    # secrets in tracked files
    secret_hits = []
    if proj["git"]:
        rc, listing = _git(["ls-files"], cwd)
        for rel in listing.splitlines()[:3000]:
            p = cwd / rel
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".ico", ".woff", ".woff2", ".ttf", ".otf"):
                continue
            try:
                if p.is_file() and p.stat().st_size < 400_000:
                    hits = scan_for_secrets(p.read_text(errors="replace", encoding="utf-8"), max_hits=2)
                    if hits:
                        secret_hits.append(f"{rel} ({hits[0][0]})")
            except Exception:
                continue
            if len(secret_hits) >= 5:
                break
    add("secrets", "no secrets in tracked files", not secret_hits, 10,
        detail="; ".join(secret_hits[:3]), how="remove + rotate the key")
    big = []
    if proj["git"]:
        rc, listing = _git(["ls-files"], cwd)
        for rel in listing.splitlines()[:5000]:
            p = cwd / rel
            try:
                if p.is_file() and p.stat().st_size > 25_000_000:
                    big.append(rel)
            except Exception:
                pass
    add("large", "no huge tracked files (>25MB)", not big, 3, detail=", ".join(big[:3]), how="git lfs or .gitignore")
    structure_ok = proj["type"] == "generic" or _exists_any(cwd, ["src", "lib", "app", "pkg", "cmd", proj["name"].replace("-", "_"),
                                                                 "*.py", "*.go", "*.rs", "*.js", "*.ts", "index.*", "main.*"])
    add("structure", "recognizable source layout", structure_ok, 3)
    add("contributing", "CONTRIBUTING.md", _exists_any(cwd, ["CONTRIBUTING.md", ".github/CONTRIBUTING.md"]), 2, fixable=True)
    add("security", "SECURITY.md", _exists_any(cwd, ["SECURITY.md", ".github/SECURITY.md"]), 2, fixable=True)

    total = sum(c["weight"] for c in checks)
    got = sum(c["weight"] for c in checks if c["ok"])
    score = int(round(100 * got / total)) if total else 0
    return {"score": score, "label": thiccness_label(score), "checks": checks, "project": proj,
            "missing": [c for c in checks if not c["ok"]]}


def thiccness_label(score):
    if score >= 90:
        return "tuna can 🥫"
    if score >= 75:
        return "thicc 💪"
    if score >= 55:
        return "getting there 🏋️"
    if score >= 35:
        return "skipping leg day 🦵"
    return "flat 📏"


# --------------------------------------------------------------------------
# Scaffold (deterministic parts)
# --------------------------------------------------------------------------

def git_author(cwd=None):
    rc, name = _git(["config", "user.name"], cwd or Path.cwd())
    return name or os.environ.get("USER") or os.environ.get("USERNAME") or "the author"


def _write_if_missing(path, content):
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def scaffold(cwd=None, apply=True, author="", license_kind="MIT", with_ci=True):
    """Create the boring essentials that don't need taste. Never overwrites.
    Returns {"created": [...], "needs_model": [...]}."""
    cwd = Path(cwd or Path.cwd()).resolve()
    proj = detect_project(cwd)
    created, needs_model = [], []
    author = author or git_author(cwd)
    year = time.strftime("%Y")

    plans = []
    # .gitignore (merge: add missing lines)
    gi = cwd / ".gitignore"
    wanted = list(GITIGNORE["common"])
    for lang in proj["langs"][:2]:
        wanted += GITIGNORE.get(lang, [])
    existing = gi.read_text(errors="replace", encoding="utf-8") if gi.exists() else ""
    have = {l.strip() for l in existing.splitlines()}
    missing_lines = [l for l in wanted if l.strip() and not l.startswith("#") and l.strip() not in have]
    if missing_lines or not gi.exists():
        plans.append((".gitignore", "append" if gi.exists() else "create", missing_lines if gi.exists() else wanted))
    if license_kind and not _exists_any(cwd, ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]):
        plans.append(("LICENSE", "create", MIT.format(year=year, author=author)))
    if not _exists_any(cwd, ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"]):
        plans.append(("CHANGELOG.md", "create", CHANGELOG))
    if not (cwd / "docs").is_dir():
        plans.append(("docs/README.md", "create", DOCS_README.format(name=proj["name"])))
    if with_ci and not _exists_any(cwd, [".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml"]):
        tpl = CI_TEMPLATES.get(proj["type"], CI_TEMPLATES["generic"])
        module = proj["name"].replace("-", "_")
        plans.append((".github/workflows/ci.yml", "create", tpl.format(name=proj["name"], module=module)))
    if not _exists_any(cwd, ["CONTRIBUTING.md", ".github/CONTRIBUTING.md"]):
        plans.append(("CONTRIBUTING.md", "create", CONTRIBUTING.format(name=proj["name"], test=proj["test_cmd"] or "the tests")))
    if not _exists_any(cwd, ["SECURITY.md", ".github/SECURITY.md"]):
        plans.append(("SECURITY.md", "create", SECURITY.format(name=proj["name"])))
    if not _has_real_content(cwd / "README.md", 300):
        needs_model.append("README.md")
    if not _has_real_content(cwd / "ABOUT.md", 300):
        needs_model.append("ABOUT.md")
    if not _exists_any(cwd, ["tests", "test", "spec", "__tests__"]):
        needs_model.append("tests/")
    if not proj["git"]:
        plans.append((".git", "init", None))

    if apply:
        for rel, action, content in plans:
            p = cwd / rel
            try:
                if action == "init":
                    if _git(["init", "-q"], cwd)[0] == 0:
                        created.append("git init")
                elif action == "append":
                    with open(p, "a", encoding="utf-8") as f:
                        txt = p.read_text(errors="replace", encoding="utf-8")
                        f.write(("\n" if txt and not txt.endswith("\n") else "") + "\n".join(content) + "\n")
                    created.append(rel + " (+%d lines)" % len(content))
                else:
                    if _write_if_missing(p, content if isinstance(content, str) else "\n".join(content) + "\n"):
                        created.append(rel)
            except Exception as e:
                created.append(f"{rel} FAILED: {e}")
    return {"created": created, "planned": [(r, a) for r, a, _ in plans], "needs_model": needs_model, "project": proj}


CONTRIBUTING = """# Contributing to {name}

Thanks for helping. Keep it simple:

1. Fork and branch from `main`.
2. Make the change. Run `{test}` before you push.
3. Open a pull request with a short description of *why*.

No contribution is too small. Typos count.
"""

SECURITY = """# Security policy

If you find a vulnerability in {name}, please **do not** open a public issue.
Email the maintainer (see the git log / package metadata) with details and
steps to reproduce. You'll get a reply within a few days.
"""


def about_prompt(proj, audit_result=None):
    missing = [c["label"] for c in (audit_result or audit(proj["cwd"]))["missing"]]
    return (f"Put this repository in ORDER using the `repo-order` skill (load it with the `skill` tool first).\n"
            f"Project: {proj['name']} ({proj['type']}; langs: {', '.join(proj['langs'][:3]) or 'n/a'}; "
            f"{proj['files']} files). Description so far: {proj['description'] or '(none)'}.\n"
            f"Missing: {', '.join(missing) or 'nothing major'}.\n"
            "Write/extend README.md and ABOUT.md (origin story, what it does, marketing copy, 3 X posts, "
            "1 LinkedIn post, 1 Reddit post, 1 Show HN line, hashtags, 'explain it to your mom'). "
            "Add a smoke test if there are no tests. Don't invent facts you can't see in the code — "
            "ask me one question if the project's purpose is unclear.")


# --------------------------------------------------------------------------
# Backups
# --------------------------------------------------------------------------

def _backup_root(cwd):
    cwd = Path(cwd).resolve()
    return BACKUP_DIR / f"{cwd.name}-{project_key(cwd)}"


def _project_files(cwd):
    cwd = Path(cwd)
    if (cwd / ".git").exists():
        rc, out = _git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd, timeout=30)
        if rc == 0:
            return [cwd / f for f in out.split("\0") if f and (cwd / f).is_file()]
    files = []
    for dirpath, dirnames, filenames in os.walk(cwd):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            files.append(Path(dirpath) / fn)
    return files


def backup(cwd=None, cfg=None, note="", max_mb=None):
    cwd = Path(cwd or Path.cwd()).resolve()
    ocfg = (cfg or {}).get("order", {})
    max_mb = max_mb or ocfg.get("backup_max_mb", 200)
    files = _project_files(cwd)
    total = 0
    for f in files:
        try:
            total += f.stat().st_size
        except Exception:
            pass
    if total > max_mb * 1e6:
        return {"ok": False, "reason": f"project is {total/1e6:.0f} MB (> order.backup_max_mb={max_mb}); skipped"}
    root = _backup_root(cwd)
    root.mkdir(parents=True, exist_ok=True)
    import uuid
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    path = root / f"{stamp}.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for f in files:
            try:
                tar.add(f, arcname=str(f.relative_to(cwd)))
            except Exception:
                continue
    meta = {"ts": time.time(), "files": len(files), "bytes": total, "note": note, "cwd": str(cwd)}
    (root / f"{stamp}.json").write_text(json.dumps(meta), encoding="utf-8")
    keep = int(ocfg.get("backup_keep", 10) or 10)
    olds = sorted(root.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime)
    for old in olds[:-keep] if len(olds) > keep else []:
        try:
            old.unlink()
            (root / (old.name[:-7] + ".json")).unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True, "path": str(path), "files": len(files), "mb": round(total / 1e6, 1)}


def list_backups(cwd=None):
    root = _backup_root(cwd or Path.cwd())
    out = []
    for t in sorted(root.glob("*.tar.gz"), reverse=True):
        meta = {}
        j = root / (t.name[:-7] + ".json")
        if j.exists():
            try:
                meta = json.loads(j.read_text(encoding="utf-8"))
            except Exception:
                pass
        out.append({"path": str(t), "ts": meta.get("ts", t.stat().st_mtime), "files": meta.get("files", "?"),
                    "mb": round(t.stat().st_size / 1e6, 2), "note": meta.get("note", "")})
    out.sort(key=lambda b: -b["ts"])
    return out


def last_backup_age_hours(cwd=None):
    b = list_backups(cwd)
    if not b:
        return None
    return (time.time() - b[0]["ts"]) / 3600


def restore_backup(path, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "r:gz") as tar:
        members = [m for m in tar.getmembers() if not (m.name.startswith("/") or ".." in Path(m.name).parts)]
        try:
            tar.extractall(dest, members=members, filter="data")
        except TypeError:  # Python < 3.12 has no `filter`
            tar.extractall(dest, members=members)
    return str(dest)


def maybe_auto_backup(cwd=None, cfg=None):
    ocfg = (cfg or {}).get("order", {})
    hours = ocfg.get("auto_backup_hours", 24)
    if not hours:
        return None
    cwd = Path(cwd or Path.cwd())
    if not (cwd / ".git").exists() and not any(cwd.glob("*")):
        return None
    age = last_backup_age_hours(cwd)
    if age is not None and age < hours:
        return None
    return backup(cwd, cfg, note="auto")


# --------------------------------------------------------------------------
# Tidy report
# --------------------------------------------------------------------------

STRAY_PATTERNS = [
    ("*.log", "log file at the root → delete or .gitignore"),
    ("*.tmp", "temp file → delete"),
    ("*.bak", "backup file → delete (CHODE keeps real backups: /backup)"),
    ("*.orig", "merge leftover → delete"),
    ("*.zip", "archive at the root → move to dist/ or delete"),
    ("*.tar.gz", "archive at the root → move to dist/ or delete"),
    ("Untitled*", "untitled file → name it or delete it"),
    ("test.py", "loose test → move to tests/"),
    ("test_*.py", "loose test → move to tests/"),
    ("scratch*", "scratch file → delete or move to scratch/ (gitignored)"),
    ("*.ipynb", "notebook at the root → move to notebooks/"),
    ("*.png", "image at the root → move to assets/ or docs/"),
    ("*.jpg", "image at the root → move to assets/ or docs/"),
    ("*.jfif", "image at the root → move to assets/"),
    ("*.mp4", "video at the root → .gitignore it or move to assets/"),
    ("*.csv", "data file at the root → move to data/"),
    ("*.sqlite", "database at the root → .gitignore it"),
    ("*.db", "database at the root → .gitignore it"),
]


def tidy_report(cwd=None):
    cwd = Path(cwd or Path.cwd()).resolve()
    tips = []
    for pattern, tip in STRAY_PATTERNS:
        for p in cwd.glob(pattern):
            if p.is_file() and p.name not in ("README.md",):
                tips.append((str(p.relative_to(cwd)), tip))
    loose_scripts = [p for p in cwd.glob("*.py") if p.name not in ("setup.py", "conftest.py", "manage.py", "noxfile.py", "tasks.py")]
    if len(loose_scripts) > 4 and (cwd / "src").is_dir():
        tips.append((f"{len(loose_scripts)} loose .py files", "you have src/ — consider moving scripts to scripts/"))
    for d in cwd.iterdir():
        try:
            if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".") and not any(d.iterdir()):
                tips.append((d.name + "/", "empty directory → delete or add a README"))
        except Exception:
            pass
    readmes = [p.name for p in cwd.glob("README*") if p.is_file()]
    if len(readmes) > 1:
        tips.append((", ".join(readmes), "multiple READMEs → keep README.md, fold the rest into docs/"))
    return tips


def status_line(cwd=None, cfg=None):
    a = audit(cwd)
    age = last_backup_age_hours(cwd)
    if age is None:
        b = "no backup yet"
    elif age < 1:
        b = "backup <1h ago"
    elif age < 48:
        b = f"backup {age:.0f}h ago"
    else:
        b = f"backup {age/24:.0f}d ago"
    return f"ORDER {a['score']}/100 {a['label']} · {b}", a
