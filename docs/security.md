# Security model

## Decision flow for every tool call

```
hook pre_tool (exit 2 → blocked)
→ tool is "safe" (read-only)?            → run
→ plan mode?                              → blocked
→ bash on the deny list?                  → blocked (ledger)
→ dangerous pattern / outside cwd /
  sensitive path?                         → always prompt (dangerous needs a typed "yes")
→ yolo, or "always" for this tool,
  or edits-mode file tool,
  or allow-listed bash prefix?            → run
→ otherwise                               → prompt: y / n / a(lways) / p(refix-allow)
→ run → redact secrets → hook post_tool → result to the model
```

Prefix allow-listing checks **every** segment of `a && b`, `a; b`, `a || b`, `a | b`.

## Dangerous patterns (needs `yes`, every mode)

Recursive deletes near root/home or with wildcards, `sudo`/`doas`, `mkfs`/`fdisk`/`parted`, `dd of=/dev`,
`curl|sh`, `chmod 777 /`, recursive `chown` on `/`, fork bombs, shutdown/reboot, writes to block
devices, `git push --force`, `git reset --hard` / `git clean -f` / `git checkout -- .`,
`git branch -D`, history tampering, `crontab -r`, kill-everything, shredding system dirs,
`npm publish` / `twine upload` / `cargo publish` / `gem push`, docker prunes, `aws|gcloud|az …
delete|destroy|terminate`, `terraform destroy`, `DROP TABLE|DATABASE`, and the PowerShell/cmd
equivalents (`del /s`, `rd /s`, `format`, `Remove-Item -Recurse` near system/home, `diskpart`,
`reg delete`, `Stop-Computer`, `vssadmin delete`, `icacls … Everyone`, `iwr | iex`, Defender tampering).

## Secrets

Patterns: OpenAI/Anthropic `sk-…`, GitHub `gh?_…`/`github_pat_…`, AWS `AKIA…`, Slack `xox…`, Google
`AIza…`, Hugging Face `hf_…`, xAI, Groq, Stripe, JWTs, PEM private keys, and generic
`api_key = "…"`-style assignments. Applied to: tool output (before the model), `/ship` and autocommit
staged diffs (refuse), imported rule files (strip), MCP-server results, GUI payloads.

## Network

`web_fetch` refuses non-http(s) URLs and cloud-metadata hosts; private addresses are allowed unless
`allow_private_urls` is false. Fetched text is wrapped in UNTRUSTED markers and scanned for
injection phrases ("ignore previous instructions", "you are now", …) → ledger `injection` + a note to
the model. The Deck binds `127.0.0.1`, uses a per-launch token in every route, sets `X-Frame-Options:
DENY`, and never stores the token anywhere.

## Files & state

`~/.chode/config.json` is `chmod 600`. Checkpoints of every file CHODE modifies are kept per session
for `/undo`. Backups are tarballs of the project only. Restores never overwrite the working tree.

## What CHODE does not do

Sandbox the shell (use `plan`/`ask`, a container, or hooks for that), guarantee redaction of
every secret format, or vet MCP servers you add.
