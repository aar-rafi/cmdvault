# cmdvault — auto-captured command cookbook (Phase A design)

Date: 2026-07-16
Status: approved

## Goal

Automatically capture the shell commands Claude Code runs successfully, store them
as browsable markdown notes in the user's Obsidian vault, and provide a terminal
fuzzy picker (`ccmd`) to reuse them. Inspired by Warp's command library, but with a
twist: every command Claude runs arrives pre-annotated with a human-readable
description, which becomes the search key.

Phases B (feed the library back to Claude) and C (team sharing / web view) build on
the same storage and are out of scope here, but the format is chosen so they need no
migration.

## Decisions made with the user

- Consumers: user first (A), then Claude (B), then team (C) — serial delivery.
- Primary interface: terminal fuzzy picker; Obsidian vault is the storage of record.
- Curation: heuristic filter now; raw log of *everything* kept so an AI curation
  pass can be added later without data loss.
- Vault: existing vault at `/home/torr20/Obsidian Vault`, subfolder `Claude Commands/`.
- Capture scope: global — hook active in every Claude Code session on the machine.

## Architecture

A Claude Code **plugin** (this repo) providing:

1. **PostToolUse hook** (matcher `Bash`) → pipes the hook payload into
   `scripts/cmdvault.py capture`, which:
   - appends the raw event (success or failure) to `Claude Commands/.raw/events.jsonl`
   - determines success (not interrupted, no error indicators / nonzero exit)
   - applies the heuristic filter
   - upserts a markdown note into the vault (dedupe by normalized command hash)
2. **`ccmd` picker** — `scripts/cmdvault.py pick`, wrapped by `shell/cmdvault.sh`
   which defines the `ccmd` function and an optional readline/zle widget. fzf list
   shows `description │ command │ project`, preview shows the full note, selection
   copies to clipboard (wl-copy/xclip/pbcopy autodetect) and prints the command.
   `ccmd -p` filters to the current project.

## Storage format

One note per unique command in `Claude Commands/`, filename `<slug>-<hash8>.md`.
The 8-char sha1 hash of the whitespace-normalized command lives in the filename and
frontmatter — that is the dedupe key. Repeat captures bump `uses` and `last_used`.

```markdown
---
description: "Rebase feature branch onto main"
project: myapp
cwd: /home/user/myapp
first_used: 2026-07-16
last_used: 2026-07-16
uses: 3
tags: [claude-cmd, git]
id: a1b2c3d4
---

```bash
git rebase --onto main old-base feature
```
```

Command text lives only in the code block (fence lengthened if the command itself
contains backticks); frontmatter stays single-line-safe. Raw JSONL log is hidden
from Obsidian (dot-folder) but travels with the vault.

## Heuristic filter (v1)

Store only successful commands, then:
- drop single-token commands and a blocklist of trivial reads
  (`ls`, `cat`, `cd`, `pwd`, `echo`, `git status`, `git diff`, plain `git log`, …)
  unless they contain shell structure (pipes, `&&`, redirects, multiline)
- keep anything with shell structure, ≥2 flags, or ≥4 tokens
- `sudo` / leading env-var assignments are skipped when identifying the binary
- auto-tag with the primary binary name

## Error handling

The hook must never break Claude Code: `capture` wraps everything, always exits 0,
and logs internal failures to `.raw/capture-errors.log`. Missing vault folders are
created on demand.

## Configuration

`CMDVAULT_DIR` env var > `~/.config/cmdvault/config.json` (`{"vault": ...}`) >
default `~/Obsidian Vault/Claude Commands`.

## Testing

Pytest over the pure logic (normalize, filter, slug, upsert, frontmatter round-trip)
plus end-to-end capture tests feeding synthetic hook payloads on stdin with
`CMDVAULT_DIR` pointed at a tmp dir. Failed/trivial commands must not create notes;
raw log must always be appended.
