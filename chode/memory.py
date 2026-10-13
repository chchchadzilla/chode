"""Persistent memory.

Three layers, all plain files you can read and edit:

1. **Instruction files** — CHODE.md / AGENTS.md / CLAUDE.md / GEMINI.md / .cursorrules …
   found in the project (walking up) plus ~/.chode/CHODE.md. Read natively: zero migration.
2. **Episodic memory** — ~/.chode/memory/<project>.jsonl and global.jsonl. Facts,
   preferences, decisions and lessons, added by you (/remember, `#note`) or by the model
   (`remember` tool, end-of-session reflection). Recalled by relevance into each session.
3. **Session transcripts** — ~/.chode/sessions (see session.py) for /resume.
"""
import json
import math
import re
import time
import uuid
from pathlib import Path

from .paths import (GLOBAL_MEMORY_FILE, INSTRUCTION_FILES, MEMORY_DIR, MEMORY_FILENAME)
from .session import project_key

KINDS = ("fact", "preference", "decision", "lesson", "todo")
KIND_WEIGHT = {"preference": 1.5, "lesson": 1.3, "decision": 1.2, "fact": 1.0, "todo": 1.1}

_TOKEN_RX = re.compile(r"[A-Za-z0-9_]+")
_CAMEL_RX = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
STOPWORDS = set("the a an and or of to in on for with is are was were be been it this that these those "
                "i you we they he she my your our their from by as at if then else not no yes do does did "
                "have has had can could should would will just also very into over under about when where "
                "how what which who whom why all any some such than too so up out use used using".split())


def tokenize(text):
    toks = []
    for t in _TOKEN_RX.findall(text or ""):
        for part in _CAMEL_RX.split(t):
            for sub in part.split("_"):
                sub = sub.lower()
                if len(sub) > 1 and sub not in STOPWORDS:
                    toks.append(sub)
    return toks


# --------------------------------------------------------------------------
# Instruction files
# --------------------------------------------------------------------------

def instruction_files(cwd=None):
    """[(label, path, text)] — global first, then project files from root → cwd.
    Each filename is included once (nearest to cwd wins)."""
    out = []
    if GLOBAL_MEMORY_FILE.exists():
        try:
            out.append(("global", GLOBAL_MEMORY_FILE, GLOBAL_MEMORY_FILE.read_text(errors="replace", encoding="utf-8")))
        except Exception:
            pass
    cwd = Path(cwd or Path.cwd()).resolve()
    chain = [cwd] + list(cwd.parents)
    seen_names = set()
    levels = []  # nearest directory first; each level keeps INSTRUCTION_FILES order
    for d in chain:
        level = []
        for name in INSTRUCTION_FILES:
            if name in seen_names:
                continue
            f = d / name
            if f.is_file():
                try:
                    text = f.read_text(errors="replace", encoding="utf-8").strip()
                except Exception:
                    continue
                if text:
                    level.append((name, f, text))
                    seen_names.add(name)
        if level:
            levels.append(level)
        if (d / ".git").exists():
            break  # stop at the repo root
    for level in reversed(levels):  # repo root → cwd
        out.extend(level)
    return out


def instructions_block(cwd=None, max_chars=24000):
    chunks = []
    total = 0
    for label, path, text in instruction_files(cwd):
        text = text[:12000]
        if total + len(text) > max_chars:
            break
        total += len(text)
        where = "~/.chode/CHODE.md" if label == "global" else str(path)
        chunks.append(f"## {label if label == 'global' else path.name} ({where})\n{text}")
    return "\n\n".join(chunks)


def append_note(note, cwd=None):
    mem = Path(cwd or Path.cwd()) / MEMORY_FILENAME
    new = not mem.exists() or mem.stat().st_size == 0
    with open(mem, "a", encoding="utf-8") as f:
        if new:
            f.write(f"# {MEMORY_FILENAME}\n\nProject notes CHODE reads at the start of every session.\n\n")
        f.write(f"- {note}\n")
    return mem


# --------------------------------------------------------------------------
# Episodic memory store
# --------------------------------------------------------------------------

class MemoryStore:
    def __init__(self, cfg=None, cwd=None):
        self.cfg = (cfg or {}).get("memory", {})
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self.key = project_key(self.cwd)
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.files = {"project": MEMORY_DIR / f"{self.key}.jsonl", "global": MEMORY_DIR / "global.jsonl"}
        self._cache = {}

    # -- io --
    def _load(self, scope):
        if scope in self._cache:
            return self._cache[scope]
        entries = []
        f = self.files[scope]
        if f.exists():
            for line in f.read_text(errors="replace", encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
        self._cache[scope] = entries
        return entries

    def _flush(self, scope):
        entries = self._cache.get(scope, [])
        self.files[scope].write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
                                     encoding="utf-8")

    # -- api --
    def add(self, text, kind="fact", scope="project", tags=None, source="user"):
        text = " ".join((text or "").split()).strip()
        if not text:
            return None
        kind = kind if kind in KINDS else "fact"
        scope = scope if scope in self.files else "project"
        entries = self._load(scope)
        for e in entries:  # dedupe near-identical
            if e.get("text", "").lower() == text.lower():
                e["ts"] = time.time()
                e["hits"] = e.get("hits", 0)
                self._flush(scope)
                return e
        entry = {"id": uuid.uuid4().hex[:8], "ts": time.time(), "kind": kind, "text": text,
                 "tags": tags or [], "source": source, "project": self.cwd.name, "hits": 0}
        entries.append(entry)
        max_entries = int(self.cfg.get("max_entries", 2000) or 2000)
        if len(entries) > max_entries:
            entries.sort(key=lambda e: (e.get("hits", 0), e.get("ts", 0)))
            del entries[: len(entries) - max_entries]
        self._flush(scope)
        return entry

    def all(self, scope=None):
        scopes = [scope] if scope else ["project", "global"]
        out = []
        for s in scopes:
            for e in self._load(s):
                out.append(dict(e, scope=s))
        return out

    def forget(self, ident):
        for scope in self.files:
            entries = self._load(scope)
            for i, e in enumerate(entries):
                if e.get("id") == ident or e.get("text") == ident:
                    entries.pop(i)
                    self._flush(scope)
                    return True
        return False

    def clear(self, scope="project"):
        self._cache[scope] = []
        self._flush(scope)

    def search(self, query, k=10, scope=None, min_score=0.0):
        q = set(tokenize(query))
        now = time.time()
        scored = []
        for e in self.all(scope):
            toks = tokenize(e.get("text", "") + " " + " ".join(e.get("tags", [])))
            if not toks:
                continue
            overlap = len(q & set(toks))
            if q and overlap == 0:
                continue
            age_days = max(0.0, (now - e.get("ts", now)) / 86400)
            recency = 1.0 / (1.0 + age_days / 30.0)
            score = (overlap / math.sqrt(len(set(toks)) + 1)) * KIND_WEIGHT.get(e.get("kind"), 1.0)
            score += 0.15 * recency + 0.02 * min(e.get("hits", 0), 10)
            if e.get("scope") == "global" and e.get("kind") == "preference":
                score += 0.2
            if score >= min_score:
                scored.append((score, e))
        scored.sort(key=lambda t: -t[0])
        return scored[:k]

    def recall_block(self, context_text, k=None):
        """Memories worth injecting into the system prompt for this session."""
        k = k or int(self.cfg.get("inject", 12) or 12)
        picked = []
        seen = set()
        for score, e in self.search(context_text, k=k):
            picked.append(e)
            seen.add(e["id"])
        # always carry global preferences and the newest project entries
        for e in self.all("global"):
            if e.get("kind") == "preference" and e["id"] not in seen and len(picked) < k + 6:
                picked.append(e)
                seen.add(e["id"])
        for e in sorted(self.all("project"), key=lambda x: -x.get("ts", 0))[:4]:
            if e["id"] not in seen and len(picked) < k + 8:
                picked.append(e)
                seen.add(e["id"])
        if not picked:
            return ""
        for e in picked:
            self._bump(e)
        lines = [f"- [{e.get('kind','fact')}{'/global' if e.get('scope')=='global' else ''}] {e['text']}" for e in picked]
        return ("Things you remember (persistent memory — use `remember` to add more, "
                "`recall` to search):\n" + "\n".join(lines))

    def _bump(self, e):
        for scope in self.files:
            for x in self._load(scope):
                if x.get("id") == e.get("id"):
                    x["hits"] = x.get("hits", 0) + 1
                    self._flush(scope)
                    return

    def export_markdown(self):
        lines = [f"# CHODE memory — {self.cwd.name}", ""]
        for scope in ("project", "global"):
            entries = self._load(scope)
            if not entries:
                continue
            lines.append(f"## {scope}")
            for e in sorted(entries, key=lambda x: x.get("ts", 0)):
                ts = time.strftime("%Y-%m-%d", time.localtime(e.get("ts", 0)))
                lines.append(f"- `{e['id']}` {ts} **{e.get('kind')}** — {e['text']}")
            lines.append("")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# End-of-session reflection
# --------------------------------------------------------------------------

REFLECT_PROMPT = """We're wrapping up. Review this session and decide what is worth remembering for future sessions in this project (or globally about how this user likes to work).

Reply with ONLY a JSON array (no prose, no code fence), max 5 items, each:
{"kind": "fact|preference|decision|lesson|todo", "scope": "project|global", "text": "<one sentence, concrete, useful later>"}

Rules: no secrets, no transcripts, no restating files you can re-read. Prefer: decisions and WHY, user preferences, gotchas discovered, unfinished work. If nothing is worth keeping, reply []."""


def parse_reflection(text):
    text = (text or "").strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("text"):
            out.append({"kind": item.get("kind", "fact"), "scope": item.get("scope", "project"),
                        "text": str(item["text"])[:400]})
    return out[:5]
