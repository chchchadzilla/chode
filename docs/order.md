# ORDER — Organize · Record · Document · Export · Release

A repo is in ORDER when a stranger can clone it, understand it, run it, and trust it.
CHODE checks that on every session start and fixes it on request.

## The audit (`/status`, `chode order`, `order_status` tool)

| check | weight | fixable by |
|---|---|---|
| README.md with real content | 14 | model |
| ABOUT.md (story + marketing + social) | 10 | model |
| LICENSE | 8 | scaffold (MIT, author from git) |
| .gitignore | 6 | scaffold (per language) |
| CHANGELOG.md | 6 | scaffold |
| docs/ | 4 | scaffold |
| tests | 10 | model (smoke test) |
| CI workflow | 6 | scaffold (python / node / generic) |
| git repository | 8 | scaffold (`git init`) |
| remote | 6 | `/ship` |
| everything committed | 6 | `/ship` |
| CHODE.md / AGENTS.md | 6 | `/init` |
| no secrets in tracked files | 10 | you (remove + rotate) |
| no huge tracked files (>25 MB) | 3 | git lfs / .gitignore |
| recognizable source layout | 3 | — |
| CONTRIBUTING.md | 2 | scaffold |
| SECURITY.md | 2 | scaffold |

Score = weighted percentage. Labels: `flat 📏` (<35) · `skipping leg day 🦵` · `getting there 🏋️` ·
`thicc 💪` (≥75) · `tuna can 🥫` (≥90).

## The fix (`/order`, `chode order fix`)

1. Deterministic scaffold — never overwrites a file that has content; `.gitignore` is merged line-wise.
2. The model loads the built-in `repo-order` skill and writes README.md / ABOUT.md / a smoke test,
   reading the real code first. It is told to ask one question if the project's purpose is unclear
   rather than invent.

## ABOUT.md spec

(a) origin story · (b) what it does + who it's for · (c) marketing copy: one-liner, 50 words,
150 words · (d) social posts: 3 X posts, 1 LinkedIn, 1 Reddit (title + body), 1 Show HN line ·
(e) hashtags · (f) "explain it to your mom". See this repo's [ABOUT.md](../ABOUT.md).

## Backups

`~/.chode/backups/<project>-<hash>/<timestamp>.tar.gz` + a `.json` sidecar. Respects `.gitignore`
(uses `git ls-files` incl. untracked-but-not-ignored). Rotated to `order.backup_keep`. Auto every
`order.auto_backup_hours` at session start, skipped above `order.backup_max_mb`. The model can call
`backup` before risky refactors. `/backup restore N` extracts to a sibling folder — it never
overwrites your working tree.

## Tidy

`/tidy` lists stray logs, temp/backup/orig files, archives, images, notebooks, data files and loose
tests at the repo root, empty directories and duplicate READMEs, each with a suggestion. It never
moves anything itself.

## Banner

`/banner [name]` → `assets/banner.svg`, `assets/banner.png` (Pillow), `assets/icon.svg`, and
`assets/banner-ai.png` when an image-model key exists. Add `![banner](assets/banner.png)` to the README.
