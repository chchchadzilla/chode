"""Security helpers: dangerous-command guard, secret redaction, path guards,
SSRF guard for web_fetch, and a secret scanner for commits.

Philosophy: never restrictive by default, always *honest*. CHODE will do what
you ask, but it tells you when something is risky, asks you to type `yes` for
the truly destructive stuff, and writes it all down in the ledger.
"""
import ipaddress
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

DANGEROUS_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(/|~|\$HOME|\.\.)(\s|$|/)*", "recursive delete near root/home"),
    (r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+\*", "recursive delete with a wildcard"),
    (r"\bsudo\b|\bdoas\b", "privilege escalation (sudo)"),
    (r"\bmkfs\b|\bfdisk\b|\bparted\b", "disk formatting/partitioning"),
    (r"\bdd\b.*\bof=/dev/", "raw write to a device"),
    (r"(curl|wget)[^|;&]*\|\s*(ba|z|da)?sh\b", "piping the internet into a shell"),
    (r"\bchmod\s+(-R\s+)?777\s+/", "chmod 777 on root paths"),
    (r"\bchown\s+-R\b.*\s/(\s|$)", "recursive chown on root"),
    (r":\(\)\s*\{.*\};\s*:", "fork bomb"),
    (r"\bshutdown\b|\breboot\b|\bhalt\b|\bpoweroff\b", "system shutdown/reboot"),
    (r">\s*/dev/sd[a-z]", "overwriting a block device"),
    (r"\bgit\s+push\b.*(--force\b|-f\b)", "force push"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s+\.)", "discarding uncommitted work"),
    (r"\bgit\s+branch\s+-D\b", "force-deleting a branch"),
    (r"\bhistory\s+-c\b|\bunset\s+HIST", "shell history tampering"),
    (r"\b(crontab\s+-r)\b", "wiping crontab"),
    (r"\bkill\s+-9\s+-1\b|\bpkill\s+-9\s+-f\s+\.", "killing everything"),
    (r"\b(truncate|shred)\b.*\s/(etc|boot|usr|var)\b", "destroying system files"),
    (r"\bnpm\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b|\bgem\s+push\b", "publishing a package to a public registry"),
    (r"\bdocker\s+(system\s+prune|rm\s+-f|volume\s+rm)\b", "destroying docker state"),
    (r"\b(aws|gcloud|az)\b.*\b(delete|destroy|rm|terminate)\b", "cloud resource deletion"),
    (r"\bterraform\s+destroy\b", "terraform destroy"),
    (r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", "dropping a database object"),
    # Windows / PowerShell
    (r"(?i)\bdel\s+/[sq]", "recursive/quiet delete (cmd)"),
    (r"(?i)\b(rd|rmdir)\s+/s", "recursive directory removal (cmd)"),
    (r"(?i)\bformat\s+[a-z]:", "formatting a drive"),
    (r"(?i)remove-item\b.*-recurse.*(c:\\|\$env:systemroot|\$env:windir|\$home|~)", "recursive PowerShell delete near system/home"),
    (r"(?i)\bdiskpart\b", "disk partitioning"),
    (r"(?i)\breg\s+delete\b|remove-itemproperty.*hklm", "registry deletion"),
    (r"(?i)stop-computer|restart-computer|\bshutdown(\.exe)?\s+/[sr]", "system shutdown/restart (win)"),
    (r"(?i)\bvssadmin\s+delete\b", "shadow-copy deletion"),
    (r"(?i)icacls\s+.*\beveryone\b", "granting permissions to Everyone"),
    (r"(?i)(iwr|invoke-webrequest|invoke-restmethod)[^|]*\|\s*(iex|invoke-expression)", "piping the internet into PowerShell"),
    (r"(?i)set-mppreference.*-disable|add-mppreference.*-exclusionpath", "tampering with Windows Defender"),
]
_DANGER_RX = [(re.compile(p), why) for p, why in DANGEROUS_PATTERNS]


def dangerous_command(cmd):
    """Returns a reason string if the command matches a dangerous pattern, else None."""
    for rx, reason in _DANGER_RX:
        if rx.search(cmd or ""):
            return reason
    return None


def _first_word(cmd):
    cmd = (cmd or "").strip()
    return cmd.split()[0] if cmd else ""


def command_matches_prefix(cmd, prefixes):
    """True if the command (or any chained segment of it) starts with an allowed prefix.
    Chained commands (`a && b`, `a; b`, `a | b`) must have EVERY segment allowed —
    otherwise `git status && rm -rf /` would sneak through on `git status`."""
    segments = [s.strip() for s in re.split(r"&&|\|\||;|\|", cmd or "") if s.strip()]
    if not segments:
        return False
    for seg in segments:
        if not any(seg.startswith(p.strip()) for p in prefixes if p and p.strip()):
            return False
    return True


def command_denied(cmd, deny_prefixes):
    """Returns the matching deny prefix if any segment of the command starts with one."""
    segments = [s.strip() for s in re.split(r"&&|\|\||;|\|", cmd or "") if s.strip()]
    for seg in segments:
        for d in deny_prefixes or []:
            if d and seg.startswith(d.strip()):
                return d
    return None


SECRET_PATTERNS = [
    ("openai/anthropic-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("huggingface token", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
    ("xai key", re.compile(r"\bxai-[A-Za-z0-9]{20,}\b")),
    ("groq key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b")),
    ("stripe key", re.compile(r"\b[sr]k_(live|test)_[A-Za-z0-9]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("private key block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY( BLOCK)?-----[\s\S]*?-----END (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY( BLOCK)?-----")),
    ("generic secret assignment", re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\s*[=:]\s*['\"][A-Za-z0-9_\-/+=]{16,}['\"]")),
]


def redact_secrets(text):
    """Replace secret-looking strings before they get sent to a model API.
    Returns (text, count_redacted)."""
    count = 0
    for _, rx in SECRET_PATTERNS:
        text, n = rx.subn("[REDACTED-SECRET]", text)
        count += n
    return text, count


def scan_for_secrets(text, max_hits=20):
    """Find secret-looking strings. Returns [(kind, preview)] — preview is masked."""
    hits = []
    for kind, rx in SECRET_PATTERNS:
        for m in rx.finditer(text or ""):
            s = m.group(0)
            preview = s[:6] + "…" + s[-3:] if len(s) > 12 else "…"
            hits.append((kind, preview))
            if len(hits) >= max_hits:
                return hits
    return hits


def path_inside_cwd(path, cwd=None):
    try:
        p = Path(path).expanduser().resolve()
        base = Path(cwd or Path.cwd()).resolve()
        tmp = Path(tempfile.gettempdir()).resolve()
        return p == base or base in p.parents or p == tmp or tmp in p.parents
    except Exception:
        return False


SENSITIVE_PATH_PARTS = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".netrc",
                        ".git-credentials", "id_rsa", "id_ed25519", ".env", ".env.local",
                        "credentials", "secrets", ".npmrc", ".pypirc"}


def sensitive_path(path):
    """Paths whose *contents* are secrets. Reading them is fine (you may need to);
    sending them to a model deserves a warning."""
    try:
        parts = {p.lower() for p in Path(path).expanduser().parts}
        return bool(parts & SENSITIVE_PATH_PARTS)
    except Exception:
        return False


_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal", "100.100.100.200", "fd00:ec2::254"}


def ssrf_guard(url, allow_private=True):
    """Return a reason string if the URL is something a web_fetch should never hit."""
    try:
        u = urlparse(url)
    except Exception:
        return "unparseable URL"
    if u.scheme not in ("http", "https"):
        return "only http(s) URLs"
    host = (u.hostname or "").lower()
    if host in _METADATA_HOSTS:
        return "cloud metadata endpoint (credential theft vector)"
    if not allow_private:
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return "private network address"
        except ValueError:
            if host in ("localhost",) or host.endswith(".local"):
                return "private network address"
    return None


def secure_file(path):
    """chmod 600 where that means something (POSIX)."""
    try:
        import os
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        pass
