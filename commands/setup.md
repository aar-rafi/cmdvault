---
description: Configure where cmdvault stores captured commands and wire up the ccmd picker
---

You are configuring cmdvault for this user. cmdvault is already capturing successful
Bash commands (the plugin's PostToolUse hook is active); this command only customizes
*where* notes go and sets up the terminal picker.

Steps:

1. Show the current state: run `"${CLAUDE_PLUGIN_ROOT}/scripts/cmdvault.py" stats`
   (probe `python3` then `python` to run it). This prints the active store location
   and what has been captured so far.

2. Ask the user where captured command notes should live, offering:
   - **Keep the default** (`~/.local/share/cmdvault/commands` or platform equivalent) — zero setup, plain markdown folder.
   - **Point it at a notes vault** (e.g. an Obsidian vault subfolder) — ask for the path. If they use Obsidian, suggest a subfolder like `<vault>/Claude Commands` so captured notes stay grouped.

3. If they choose a custom path: write it to the config file —
   `~/.config/cmdvault/config.json` (Linux/macOS, honoring `XDG_CONFIG_HOME`) or
   `%APPDATA%\cmdvault\config.json` (Windows) — as `{"vault": "<absolute path>"}`.
   Create parent directories as needed. If a config file already exists, update only
   the `vault` key. If they had captures in the old location, offer to move the
   existing `*.md` notes and `.raw/` folder to the new location.

4. Offer shell integration for the `ccmd` picker. Detect their shell from `$SHELL`:
   - bash: append a guarded source line for `${CLAUDE_PLUGIN_ROOT}/shell/cmdvault.sh` to `~/.bashrc`
   - zsh: same, to `~/.zshrc`
   - fish: symlink (not copy — the file locates the plugin relative to its real path) `${CLAUDE_PLUGIN_ROOT}/shell/cmdvault.fish` into `~/.config/fish/conf.d/`
   Ask before touching any rc file. Note: `${CLAUDE_PLUGIN_ROOT}` changes on plugin
   updates, so prefer writing the resolved current path with a comment marker
   `# cmdvault` so it can be found and updated later.

5. Check optional dependencies and offer to install what's missing (ask first, use
   the system's package manager, show the exact command before running it):
   - `fzf` — makes the picker fuzzy-searchable; without it there's a numbered
     fallback. Detect the package manager (`pacman -S fzf`, `apt install fzf`,
     `dnf install fzf`, `brew install fzf`, `winget install fzf`) and offer to run it.
   - Linux only, and only if `wl-copy`, `xclip`, `xsel`, and a KDE `qdbus` are ALL
     absent: offer `wl-clipboard` (Wayland) or `xclip` (X11) for clipboard support,
     noting the OSC52 terminal fallback usually covers modern terminals anyway.
   Never install anything without explicit user approval in the conversation.

6. Finish by confirming: store path, shell integration status, and remind them that
   capture is automatic — nothing else to do.
