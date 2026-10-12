"""Local codebase index ("RAG for your repo, for free").

Pure-stdlib BM25 over line-chunks of your source files, stored in
./.chode/index.json. Optional dense embeddings (OpenAI-compatible /embeddings or
Ollama) stored as float32 in ./.chode/index.vec. Search is hybrid when vectors exist.

Why: the model reads *only* what matters instead of grepping blind — fewer tokens,
fewer dollars, better answers.
"""
import array
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

from .paths import PROJECT_DIRNAME, SKIP_DIRS
from .memory import tokenize

TEXT_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".json", ".md", ".txt", ".rst", ".yml", ".yaml",
            ".toml", ".ini", ".cfg", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".go", ".rs", ".java", ".kt",
            ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".rb", ".php", ".swift", ".dart", ".ex", ".exs", ".scala",
            ".sql", ".html", ".css", ".scss", ".vue", ".svelte", ".lua", ".r", ".jl", ".m", ".pl", ".el",
            ".clj", ".hs", ".ml", ".nim", ".zig", ".proto", ".graphql", ".tf", ".dockerfile", ".env.example",
            ".xml", ".gradle", ".cmake", ".mk", ".make"}
TEXT_NAMES = {"Makefile", "Dockerfile", "Justfile", "Rakefile", "Gemfile", "Procfile", "CMakeLists.txt", "LICENSE"}
MAX_FILE_BYTES = 600_000
CHUNK_LINES, CHUNK_OVERLAP = 50, 8


def index_dir(cwd=None):
    return Path(cwd or Path.cwd()) / PROJECT_DIRNAME


def _is_text_file(p):
    return p.suffix.lower() in TEXT_EXT or p.name in TEXT_NAMES


def list_source_files(cwd, max_files=4000):
    cwd = Path(cwd)
    files = []
    if (cwd / ".git").exists():
        try:
            r = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                               capture_output=True, cwd=str(cwd), timeout=20)
            if r.returncode == 0:
                for raw in r.stdout.split(b"\0"):
                    if not raw:
                        continue
                    p = cwd / raw.decode("utf-8", "replace")
                    if p.is_file() and _is_text_file(p) and not any(part in SKIP_DIRS for part in p.parts):
                        files.append(p)
        except Exception:
            files = []
    if not files:
        for dirpath, dirnames, filenames in os.walk(cwd):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                p = Path(dirpath) / fn
                if _is_text_file(p):
                    files.append(p)
            if len(files) > max_files * 2:
                break
    # prefer source over docs/config when we must cut
    def prio(p):
        return 0 if p.suffix in (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs", ".rb") else 1
    files.sort(key=lambda p: (prio(p), str(p)))
    return files[:max_files]


def chunk_lines(lines, size=CHUNK_LINES, overlap=CHUNK_OVERLAP):
    n = len(lines)
    if n == 0:
        return []
    out, start = [], 0
    while start < n:
        end = min(n, start + size)
        out.append((start + 1, end))
        if end == n:
            break
        start = end - overlap
    return out


class Index:
    VERSION = 2

    def __init__(self, cwd=None, cfg=None):
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self.cfg = (cfg or {}).get("rag", {}) if cfg else {}
        self.dir = index_dir(self.cwd)
        self.file = self.dir / "index.json"
        self.vec_file = self.dir / "index.vec"
        self.files = {}      # rel path -> {"mtime", "size", "chunks": [chunk_id...]}
        self.chunks = []     # [rel, start, end, length_tokens]
        self.postings = {}   # term -> {chunk_id: tf}
        self.avgdl = 1.0
        self.vectors = None  # array('f'), dims
        self.dims = 0
        self.built_at = 0

    # ---- persistence ----
    def load(self):
        if not self.file.exists():
            return False
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            if data.get("version") != self.VERSION:
                return False
            self.files = data["files"]
            self.chunks = data["chunks"]
            self.postings = {t: {int(k): v for k, v in d.items()} for t, d in data["postings"].items()}
            self.avgdl = data.get("avgdl", 1.0)
            self.built_at = data.get("built_at", 0)
            self.dims = data.get("dims", 0)
            if self.dims and self.vec_file.exists():
                arr = array.array("f")
                arr.frombytes(self.vec_file.read_bytes())
                self.vectors = arr
            return True
        except Exception:
            return False

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        data = {"version": self.VERSION, "built_at": self.built_at, "avgdl": self.avgdl, "dims": self.dims,
                "files": self.files, "chunks": self.chunks,
                "postings": {t: {str(k): v for k, v in d.items()} for t, d in self.postings.items()}}
        self.file.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        if self.vectors is not None and self.dims:
            self.vec_file.write_bytes(self.vectors.tobytes())
        gi = self.cwd / ".gitignore"
        try:  # make sure the index never gets committed
            txt = gi.read_text(encoding="utf-8") if gi.exists() else ""
            if ".chode/" not in txt and ".chode" not in txt.splitlines():
                with open(gi, "a", encoding="utf-8") as f:
                    f.write(("\n" if txt and not txt.endswith("\n") else "") + "# chode local state\n.chode/\n")
        except Exception:
            pass

    # ---- building ----
    def build(self, embed=None, progress=None, full=False):
        """Incremental rebuild. embed: callable(list[str]) -> list[list[float]] or None."""
        t0 = time.time()
        max_files = int(self.cfg.get("max_files", 4000) or 4000)
        sources = list_source_files(self.cwd, max_files)
        rel_now = {}
        for p in sources:
            try:
                st = p.stat()
            except Exception:
                continue
            if st.st_size > MAX_FILE_BYTES:
                continue
            rel_now[str(p.relative_to(self.cwd)).replace(os.sep, "/")] = (st.st_mtime, st.st_size)
        if full:
            self.files, self.chunks, self.postings, self.vectors, self.dims = {}, [], {}, None, 0
        changed = [r for r, (m, s) in rel_now.items()
                   if r not in self.files or self.files[r]["mtime"] != m or self.files[r]["size"] != s]
        removed = [r for r in self.files if r not in rel_now]
        if not changed and not removed and self.chunks:
            return {"files": len(self.files), "chunks": len(self.chunks), "changed": 0, "secs": time.time() - t0}
        # rebuild from scratch when anything changed (simple + correct; fast enough for ≤4k files)
        new_files, new_chunks, postings = {}, [], {}
        texts_for_embed = []
        for i, rel in enumerate(sorted(rel_now)):
            p = self.cwd / rel
            try:
                text = p.read_text(errors="replace", encoding="utf-8")
            except Exception:
                continue
            if "\x00" in text[:2000]:
                continue
            lines = text.splitlines()
            ids = []
            for start, end in chunk_lines(lines):
                cid = len(new_chunks)
                body = "\n".join(lines[start - 1:end])
                toks = tokenize(body) + tokenize(rel) * 2  # path terms count a little extra
                tf = {}
                for t in toks:
                    tf[t] = tf.get(t, 0) + 1
                for t, n in tf.items():
                    postings.setdefault(t, {})[cid] = n
                new_chunks.append([rel, start, end, len(toks)])
                ids.append(cid)
                if embed:
                    texts_for_embed.append(f"{rel}\n{body[:2000]}")
            m, s = rel_now[rel]
            new_files[rel] = {"mtime": m, "size": s, "chunks": ids}
            if progress and i % 50 == 0:
                progress(i, len(rel_now))
        self.files, self.chunks, self.postings = new_files, new_chunks, postings
        self.avgdl = (sum(c[3] for c in new_chunks) / len(new_chunks)) if new_chunks else 1.0
        self.vectors, self.dims = None, 0
        if embed and texts_for_embed:
            try:
                vecs = []
                for b in range(0, len(texts_for_embed), 64):
                    vecs.extend(embed(texts_for_embed[b:b + 64]))
                    if progress:
                        progress(min(b + 64, len(texts_for_embed)), len(texts_for_embed))
                if vecs and len(vecs) == len(new_chunks):
                    self.dims = len(vecs[0])
                    arr = array.array("f")
                    for v in vecs:
                        arr.extend(v)
                    self.vectors = arr
            except Exception:
                self.vectors, self.dims = None, 0
        self.built_at = time.time()
        self.save()
        return {"files": len(self.files), "chunks": len(self.chunks), "changed": len(changed) + len(removed),
                "secs": time.time() - t0, "embedded": bool(self.dims)}

    # ---- search ----
    def _bm25(self, query_tokens, k1=1.5, b=0.75):
        N = len(self.chunks) or 1
        scores = {}
        for t in set(query_tokens):
            plist = self.postings.get(t)
            if not plist:
                continue
            idf = math.log(1 + (N - len(plist) + 0.5) / (len(plist) + 0.5))
            for cid, tf in plist.items():
                dl = self.chunks[cid][3] or 1
                denom = tf + k1 * (1 - b + b * dl / self.avgdl)
                scores[cid] = scores.get(cid, 0.0) + idf * (tf * (k1 + 1)) / denom
        return scores

    def _dense(self, qvec):
        if self.vectors is None or not self.dims:
            return {}
        d = self.dims
        qn = math.sqrt(sum(x * x for x in qvec)) or 1.0
        out = {}
        v = self.vectors
        for cid in range(len(self.chunks)):
            base = cid * d
            dot = 0.0
            nn = 0.0
            for j in range(d):
                x = v[base + j]
                dot += x * qvec[j]
                nn += x * x
            out[cid] = dot / ((math.sqrt(nn) or 1.0) * qn)
        return out

    def search(self, query, k=8, embed=None, per_file=3):
        qt = tokenize(query)
        scores = self._bm25(qt)
        if embed and self.dims:
            try:
                qv = embed([query])[0]
                dense = self._dense(qv)
                if scores:
                    mx = max(scores.values()) or 1.0
                    scores = {c: s / mx for c, s in scores.items()}
                for cid, s in dense.items():
                    scores[cid] = scores.get(cid, 0.0) * 0.5 + max(0.0, s) * 0.5
            except Exception:
                pass
        # phrase/identifier boost
        ql = query.lower().strip()
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        out, per = [], {}
        for cid, s in ranked:
            rel, start, end, _ = self.chunks[cid]
            if per.get(rel, 0) >= per_file:
                continue
            snippet = self._snippet(rel, start, end)
            if ql and len(ql) > 3 and ql in snippet.lower():
                s *= 1.3
            per[rel] = per.get(rel, 0) + 1
            out.append({"path": rel, "start": start, "end": end, "score": round(s, 3), "snippet": snippet})
            if len(out) >= k * 2:
                break
        out.sort(key=lambda r: -r["score"])
        return out[:k]

    def _snippet(self, rel, start, end, max_chars=2400):
        try:
            lines = (self.cwd / rel).read_text(errors="replace", encoding="utf-8").splitlines()
            body = "\n".join(f"{i:5d}  {l}" for i, l in enumerate(lines[start - 1:end], start=start))
            return body[:max_chars]
        except Exception:
            return ""

    def stats(self):
        return {"files": len(self.files), "chunks": len(self.chunks), "terms": len(self.postings),
                "embedded": bool(self.dims), "built_at": self.built_at,
                "size_kb": (self.file.stat().st_size // 1024) if self.file.exists() else 0}


def format_results(results):
    if not results:
        return "No matches in the index. (Try `grep`, or rebuild with /index.)"
    parts = []
    for r in results:
        parts.append(f"=== {r['path']}:{r['start']}-{r['end']}  (score {r['score']})\n{r['snippet']}")
    return "\n\n".join(parts)
