# Security policy

CHODE edits files and runs commands on your machine. That's the product. Here's how it's kept
honest, and how to tell us when it isn't.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Email the maintainer (address in the
git log / GitHub profile of [@chchchadzilla](https://github.com/chchchadzilla)) with details and
steps to reproduce. You'll get a reply within a few days and credit in the changelog if you want it.

## What CHODE does to protect you

- **Permission modes** (`plan` / `ask` / `edits` / `yolo`) decide what runs without asking. Dangerous
  commands (recursive deletes near root, `sudo`, force-push, `git reset --hard`, `curl | sh`, disk and
  registry operations, package publishing, cloud deletes, `DROP TABLE`, …) always require a typed
  `yes`, in every mode. See `chode/security.py` for the full list.
- **Allow lists** apply to every segment of a chained command. **Deny lists** are absolute.
- **Secrets** (API keys, tokens, JWTs, private keys) are redacted from tool output before it reaches
  any model, refused in commits by `/ship` and autocommit, and stripped from imported rule files.
- **Network:** `web_fetch` never hits cloud-metadata endpoints; fetched content is wrapped as untrusted
  data and scanned for prompt-injection phrases. The GUI binds `127.0.0.1` behind a random token.
- **Local only:** config is `chmod 600`; sessions, memory, backups and the ledger live in `~/.chode`.
  CHODE does not phone home. The only network calls are to the provider you configured (or none, for
  local models).
- **Ledger:** every risky moment is appended to `~/.chode/ledger.jsonl` (`/ledger`).
- **Plan Bridge / MCP-server mode** cannot prompt you inside the vendor process; CHODE asks on the
  controlling terminal when one is attached and otherwise refuses anything the mode doesn't allow.

## Known limitations

- `yolo` mode is yolo mode. Use it in sandboxes.
- Redaction is pattern-based; it catches the common key formats, not every possible secret.
- MCP servers you connect run with your user's privileges, like any other program you install.
