# cmdvault

**Claude Code writes really good shell commands. Then they scroll away forever.**

cmdvault fixes that. Every time Claude runs a command that works, it gets saved —
automatically, with the plain-English description Claude wrote for it. Later you
fuzzy-search by *what the command does* ("rotate video 90 degrees", "find files
changed last week") instead of trying to remember flag soup.

```
$ ccmd
> rotate video
  Rotate video 90 degrees clockwise      │ ffmpeg -i in.mp4 -vf "transpose=1" out.mp4
  ...
```

No note-taking, no "I should save this", no habit to build. It just accumulates
while you work.

## How it works

A `PostToolUse` hook watches every Bash command Claude Code runs:

- **Succeeded + interesting?** → saved as a markdown note (deduped — repeats bump a
  use counter, so your most-used commands float to the top)
- **Trivial noise** (`ls`, `cat`, `git status`...)? → filtered out by heuristics
- **Everything**, success or failure → appended to a raw JSONL log, so smarter
  curation can mine it later

Your library is a folder of plain markdown files. No database, no lock-in — grep
it, sync it, delete it, or point any notes app at it.

## Install

```
/plugin marketplace add aar-rafi/cmdvault
/plugin install cmdvault@cmdvault
```

Then (optional but recommended) run `/cmdvault:setup` inside Claude Code — it wires
up the `ccmd` picker for your shell (bash/zsh/fish) and lets you choose where notes
are stored.

That's it. Capture starts immediately in new sessions.

## Usage

| Command | What it does |
|---|---|
| `ccmd` | Fuzzy-pick a captured command (fzf if installed, numbered list otherwise); prints it and copies to clipboard |
| `ccmd -p` | Same, but only commands captured in the current project |
| `Ctrl-X Ctrl-R` | Insert a picked command straight into your prompt |
| `cmdvault.py stats` | What's in the vault, sorted by use count |
| `cmdvault.py export --warp` | Export your library as [Warp workflows](https://docs.warp.dev/terminal/entry/yaml-workflows) |

Clipboard works out of the box on Wayland, X11, KDE (via Klipper), macOS, Windows/WSL
(`clip.exe`), and falls back to OSC52 (your terminal sets the clipboard — works over SSH).

## Where notes go

Default: `~/.local/share/cmdvault/commands` (platform-appropriate elsewhere).

**Obsidian user?** Point cmdvault at a folder inside your vault and every captured
command becomes a browsable, taggable, linkable note:

```json
// ~/.config/cmdvault/config.json
{ "vault": "/path/to/YourVault/Claude Commands" }
```

(or set `CMDVAULT_DIR`, or run `/cmdvault:setup`). A note looks like:

````markdown
---
description: "Rebase feature branch onto main"
project: myapp
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

- **Done** — auto-capture, dedupe, heuristic noise filter, `ccmd` picker, Obsidian-friendly storage, Warp export
- **Next** — feed the library back to Claude, so future sessions reuse commands that already worked instead of re-deriving them
- **Later** — team-shared vaults (git), AI curation of the raw log, web view

## Requirements

Python 3 (any recent version, stdlib only). `fzf` optional but worth it. That's the list.
