# cmdvault

A Warp-drive-style **auto-captured command cookbook** for Claude Code.

Every shell command Claude Code runs comes pre-annotated with a human-readable
description. cmdvault captures the ones that succeed and are worth keeping, stores
them as markdown notes in your Obsidian vault, and gives you a terminal fuzzy
picker (`ccmd`) to reuse them — searchable by what the command *does*, not just
what it says.

## How it works

1. A `PostToolUse` hook fires after every Bash command Claude runs.
2. The raw event (success or failure) is appended to `.raw/events.jsonl` inside the
   vault folder — nothing is ever thrown away, so smarter AI curation can be added
   later.
3. Successful commands pass through a heuristic filter that drops trivial noise
   (`ls`, `cat`, `git status`, single-word commands, …) and keeps anything with
   pipes, multiple flags, redirects, or real substance.
4. Kept commands are upserted as one markdown note per unique command. Repeats bump
   a `uses` counter instead of duplicating.

The hook is fully defensive: it always exits 0 and can never break a Claude Code
session. Internal errors go to `.raw/capture-errors.log`.

## Install

```
# inside Claude Code
/plugin marketplace add /home/torr20/Documents/plugin-for-claude
/plugin install cmdvault@plugin-for-claude
```

Then add the shell integration to your `~/.bashrc` or `~/.zshrc`:

```sh
source /home/torr20/Documents/plugin-for-claude/shell/cmdvault.sh
```

Requires `python3` (stdlib only) and [`fzf`](https://github.com/junegunn/fzf) for
the picker. Clipboard support autodetects `wl-copy`, `xclip`, or `pbcopy`.

## Usage

| Command | What it does |
| --- | --- |
| `ccmd` | Fuzzy-search all captured commands; selection is printed and copied to the clipboard |
| `ccmd -p` | Same, filtered to commands captured in the current project |
| `Ctrl-X Ctrl-R` | Pick a command and insert it directly into your prompt line (bash & zsh) |
| `python3 scripts/cmdvault.py stats` | Vault statistics (counts by project/tag) |

Or just browse the vault in Obsidian — every command is a note with frontmatter
(description, project, usage count, tags) and renders as a syntax-highlighted code
block.

## Configuration

Vault location resolution order:

1. `CMDVAULT_DIR` environment variable
2. `~/.config/cmdvault/config.json` → `{"vault": "/path/to/folder"}`
3. Default: `~/Obsidian Vault/Claude Commands`

## Note format

`Claude Commands/git-rebase-onto-a1b2c3d4.md`:

````markdown
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
````

## Roadmap

- **Phase A (this)** — auto-capture + Obsidian storage + `ccmd` picker
- **Phase B** — feed the library back to Claude Code, so future sessions reuse
  commands that already worked instead of re-deriving them
- **Phase C** — team sharing: vault as a git repo / lightweight web view, plus an
  AI curation pass over the raw event log

Design spec: [`docs/superpowers/specs/2026-07-16-cmdvault-design.md`](docs/superpowers/specs/2026-07-16-cmdvault-design.md)
