#!/usr/bin/env python3
"""cmdvault: auto-capture successful Claude Code Bash commands into an Obsidian vault.

Subcommands:
  capture   read a PostToolUse hook payload on stdin, log it, store a note if worthy
  pick      fuzzy-pick a stored command with fzf (prints it, copies to clipboard)
  show ID   print the note for a command id
  stats     summary of the stored library
"""

import base64
import datetime
import glob
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import traceback

def _default_vault():
    # Neutral, platform-appropriate default. Point it at an Obsidian vault
    # folder via config/env if you want the notes to show up there.
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "cmdvault", "commands")
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(xdg, "cmdvault", "commands")


def _config_path():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "cmdvault", "config.json")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg, "cmdvault", "config.json")


DEFAULT_VAULT = _default_vault()
CONFIG_PATH = _config_path()

BLOCKLIST = {
    "ls", "ll", "pwd", "cd", "cat", "head", "tail", "less", "more", "echo",
    "printf", "which", "whereis", "whoami", "hostname", "date", "clear",
    "history", "man", "help", "true", "false", "exit", "env", "printenv",
    "type", "file", "stat", "du", "df", "free", "uptime", "wc", "sleep",
    "touch", "mkdir", "basename", "dirname", "realpath", "readlink",
}

TRIVIAL_GIT_SUBCOMMANDS = {"status", "diff", "log", "branch", "show", "add"}

STRUCTURE_RE = re.compile(r"\|\||&&|[|;><`]|\$\(")

ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


# ---------------------------------------------------------------- vault/config

def vault_dir():
    env = os.environ.get("CMDVAULT_DIR")
    if env:
        return os.path.expanduser(env)
    try:
        with open(_config_path(), encoding="utf-8") as f:
            configured = json.load(f).get("vault")
        if configured:
            return os.path.expanduser(configured)
    except Exception:
        pass
    return _default_vault()


def raw_dir(vault):
    return os.path.join(vault, ".raw")


def _today():
    return datetime.date.today().isoformat()


def log_error(vault, message):
    """Record an internal failure without ever raising."""
    try:
        os.makedirs(raw_dir(vault), exist_ok=True)
        with open(os.path.join(raw_dir(vault), "capture-errors.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.datetime.now().isoformat(), message))
    except Exception:
        pass


# ---------------------------------------------------------------- filtering

def normalize(command):
    return re.sub(r"\s+", " ", command).strip()


def cmd_id(command):
    return hashlib.sha1(normalize(command).encode("utf-8")).hexdigest()[:8]


def has_structure(command):
    return bool(STRUCTURE_RE.search(command)) or "\n" in command.strip()


def tokenize(command):
    norm = normalize(command)
    try:
        return shlex.split(norm)
    except ValueError:
        return norm.split()


def effective_tokens(tokens):
    """Tokens with leading sudo / VAR=value assignments stripped."""
    out = list(tokens)
    while out and (out[0] == "sudo" or ENV_ASSIGN_RE.match(out[0])):
        out.pop(0)
    return out


def primary_binary(command):
    eff = effective_tokens(tokenize(command))
    if not eff:
        return ""
    return os.path.basename(eff[0])


def should_store(command):
    norm = normalize(command)
    if not norm:
        return False
    tokens = tokenize(norm)
    if not tokens:
        return False
    if has_structure(command):
        return True
    eff = effective_tokens(tokens)
    if not eff:
        return False
    binary = os.path.basename(eff[0])
    if binary in BLOCKLIST:
        return False
    if binary == "git" and len(eff) == 2 and eff[1] in TRIVIAL_GIT_SUBCOMMANDS:
        return False
    if len(tokens) == 1:
        return False
    flags = sum(1 for t in tokens if t.startswith("-"))
    return flags >= 2 or len(tokens) >= 4


def is_success(tool_response):
    if not isinstance(tool_response, dict):
        return True
    if tool_response.get("interrupted"):
        return False
    if tool_response.get("is_error"):
        return False
    if "error" in tool_response:
        return False
    for key in ("exit_code", "exitCode", "return_code", "returnCode"):
        if key in tool_response:
            try:
                if int(tool_response[key]) != 0:
                    return False
            except (TypeError, ValueError):
                pass
    return True


# ---------------------------------------------------------------- notes

def slugify(text, max_len=40):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].strip("-")
    return slug or "cmd"


def code_fence(command):
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", command)), default=0)
    return "`" * max(3, longest + 1)


def render_note(meta, command):
    fence = code_fence(command)
    lines = [
        "---",
        "description: %s" % json.dumps(meta["description"]),
        "project: %s" % json.dumps(meta["project"]),
        "cwd: %s" % json.dumps(meta["cwd"]),
        "first_used: %s" % meta["first_used"],
        "last_used: %s" % meta["last_used"],
        "uses: %d" % meta["uses"],
        "tags: [%s]" % ", ".join(meta["tags"]),
        "id: %s" % meta["id"],
        "---",
        "",
        fence + "bash",
        command.rstrip("\n"),
        fence,
        "",
    ]
    return "\n".join(lines)


def parse_note(path):
    """Return (meta, command) parsed from a note file."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    meta = {}
    body_start = 0
    if lines and lines[0] == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line == "---":
                body_start = i + 1
                break
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            elif key == "tags" and value.startswith("["):
                value = [t.strip() for t in value[1:-1].split(",") if t.strip()]
            elif key == "uses":
                try:
                    value = int(value)
                except ValueError:
                    value = 1
            meta[key] = value
    command_lines = []
    fence = None
    for line in lines[body_start:]:
        if fence is None:
            m = re.match(r"^(`{3,})\w*$", line)
            if m:
                fence = m.group(1)
            continue
        if line == fence:
            break
        command_lines.append(line)
    return meta, "\n".join(command_lines)


def note_path_for_id(vault, cid):
    matches = sorted(glob.glob(os.path.join(vault, "*-%s.md" % cid)))
    return matches[0] if matches else None


def upsert(vault, command, description, cwd, project):
    os.makedirs(vault, exist_ok=True)
    cid = cmd_id(command)
    today = _today()
    existing = note_path_for_id(vault, cid)
    if existing:
        meta, stored_command = parse_note(existing)
        meta.setdefault("description", description)
        meta.setdefault("project", project)
        meta.setdefault("cwd", cwd)
        meta.setdefault("first_used", today)
        meta.setdefault("tags", ["claude-cmd"])
        meta.setdefault("id", cid)
        meta["uses"] = int(meta.get("uses", 1)) + 1
        meta["last_used"] = today
        with open(existing, "w", encoding="utf-8") as f:
            f.write(render_note(meta, stored_command or command))
        return existing

    slug = slugify(description or command)
    path = os.path.join(vault, "%s-%s.md" % (slug, cid))
    binary = primary_binary(command)
    tags = ["claude-cmd"]
    if binary and re.fullmatch(r"[A-Za-z0-9._+-]+", binary):
        tags.append(binary)
    meta = {
        "description": re.sub(r"\s+", " ", description).strip(),
        "project": project,
        "cwd": cwd,
        "first_used": today,
        "last_used": today,
        "uses": 1,
        "tags": tags,
        "id": cid,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_note(meta, command))
    return path


# ---------------------------------------------------------------- capture

def project_name(cwd):
    if not cwd:
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return os.path.basename(result.stdout.strip())
    except Exception:
        pass
    return os.path.basename(os.path.normpath(cwd)) or "unknown"


def cmd_capture():
    vault = vault_dir()
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    try:
        payload = json.loads(raw)
    except Exception:
        log_error(vault, "unparseable stdin payload (%d bytes)" % len(raw or ""))
        return 0
    try:
        os.makedirs(raw_dir(vault), exist_ok=True)
        event = dict(payload) if isinstance(payload, dict) else {"payload": payload}
        event["ts"] = datetime.datetime.now().isoformat()
        with open(os.path.join(raw_dir(vault), "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        log_error(vault, "raw log append failed:\n" + traceback.format_exc())
    try:
        if not isinstance(payload, dict):
            return 0
        if payload.get("tool_name") not in (None, "Bash"):
            return 0
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command") or ""
        if not command.strip():
            return 0
        if not is_success(payload.get("tool_response")):
            return 0
        if not should_store(command):
            return 0
        cwd = payload.get("cwd") or ""
        description = tool_input.get("description") or ""
        upsert(vault, command, description, cwd, project_name(cwd))
    except Exception:
        log_error(vault, "capture failed:\n" + traceback.format_exc())
    return 0


# ---------------------------------------------------------------- reading

def load_entries(vault):
    entries = []
    for path in sorted(glob.glob(os.path.join(vault, "*.md"))):
        try:
            meta, command = parse_note(path)
        except Exception:
            continue
        if not command or not meta.get("id"):
            continue
        entries.append({
            "id": meta.get("id", ""),
            "description": meta.get("description", "") or "(no description)",
            "command": command,
            "project": meta.get("project", "") or "unknown",
            "uses": int(meta.get("uses", 1) or 1),
            "last_used": str(meta.get("last_used", "")),
            "path": path,
        })
    entries.sort(key=lambda e: (e["uses"], e["last_used"]), reverse=True)
    return entries


def clipboard_backends():
    """Ordered clipboard tool candidates for the current environment."""
    wayland = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    tools = [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["pbcopy"],
        ["clip.exe"],  # native Windows and WSL
    ]
    if not wayland:
        tools = tools[1:] + tools[:1]  # try X11 tools before wl-copy
    return tools


def copy_clipboard(text):
    for tool in clipboard_backends():
        if shutil.which(tool[0]):
            try:
                r = subprocess.run(
                    tool, input=text.encode("utf-8"), check=False,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if r.returncode == 0:
                    return True
            except Exception:
                continue
    # KDE Klipper over D-Bus (stock KDE has no wl-copy/xclip installed)
    for qdbus in ("qdbus6", "qdbus-qt6", "qdbus"):
        if shutil.which(qdbus):
            try:
                r = subprocess.run(
                    [qdbus, "org.kde.klipper", "/klipper", "setClipboardContents", text],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if r.returncode == 0:
                    return True
            except Exception:
                pass
    # Last resort: OSC 52 — asks the terminal emulator itself to set the
    # clipboard. Works in Konsole, kitty, alacritty, wezterm, even over SSH.
    try:
        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        with open("/dev/tty", "wb") as tty:
            tty.write(b"\033]52;c;" + payload.encode("ascii") + b"\a")
            tty.flush()
        return True
    except Exception:
        return False


def pick_numbered(entries, input_fn=input):
    """Plain numbered picker for machines without fzf."""
    top = entries[:20]
    for i, e in enumerate(top, 1):
        oneline = " ⏎ ".join(e["command"].splitlines())
        print("%2d) %-45s %s" % (i, e["description"][:45], oneline[:60]), file=sys.stderr)
    if len(entries) > len(top):
        print("    ... %d more (install fzf for fuzzy search)" % (len(entries) - len(top)),
              file=sys.stderr)
    try:
        choice = input_fn("pick> ").strip()
        idx = int(choice)
        entry = top[idx - 1]
    except (ValueError, IndexError, EOFError, KeyboardInterrupt):
        return 1
    copy_clipboard(entry["command"])
    print(entry["command"])
    return 0


def cmd_pick(argv):
    vault = vault_dir()
    entries = load_entries(vault)
    if "-p" in argv:
        current = project_name(os.getcwd())
        entries = [e for e in entries if e["project"] == current]
    if not entries:
        print("cmdvault: no stored commands%s" % (" for this project" if "-p" in argv else ""),
              file=sys.stderr)
        return 1
    if not shutil.which("fzf"):
        return pick_numbered(entries)
    self_path = os.path.abspath(__file__)
    lines = []
    for e in entries:
        oneline = " ⏎ ".join(e["command"].splitlines())
        lines.append("\t".join([e["id"], e["description"], oneline, e["project"]]))
    fzf = subprocess.run(
        [
            "fzf",
            "--delimiter=\t",
            "--with-nth=2,3,4",
            "--preview", "python3 %s show {1}" % shlex.quote(self_path),
            "--preview-window=down,10,wrap",
        ],
        input="\n".join(lines), capture_output=True, text=True,
    )
    if fzf.returncode != 0 or not fzf.stdout.strip():
        return 1
    selected_id = fzf.stdout.split("\t", 1)[0].strip()
    entry = next((e for e in entries if e["id"] == selected_id), None)
    if entry is None:
        return 1
    copy_clipboard(entry["command"])
    print(entry["command"])
    return 0


def cmd_show(argv):
    if not argv:
        print("usage: cmdvault show <id>", file=sys.stderr)
        return 1
    vault = vault_dir()
    path = note_path_for_id(vault, argv[0])
    if not path:
        print("cmdvault: no command with id %s" % argv[0], file=sys.stderr)
        return 1
    with open(path, encoding="utf-8") as f:
        sys.stdout.write(f.read())
    return 0


def default_warp_workflows_dir():
    if sys.platform == "darwin":
        return os.path.expanduser("~/.warp/workflows")
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA", ""), "warp", "Warp", "data", "workflows")
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(xdg, "warp-terminal", "workflows")


def yaml_scalar(text):
    # JSON string encoding is a valid YAML flow scalar; multiline commands
    # use a literal block instead so they stay readable.
    if "\n" in text:
        return "|\n" + "\n".join("  " + line for line in text.splitlines())
    return json.dumps(text, ensure_ascii=False)


def warp_workflow_yaml(entry):
    lines = [
        "---",
        "name: %s" % yaml_scalar(entry["description"]),
        "command: %s" % yaml_scalar(entry["command"]),
    ]
    tags = ["cmdvault"]
    binary = entry.get("tags_binary")
    if binary:
        tags.append(binary)
    lines.append("tags: [%s]" % ", ".join(json.dumps(t) for t in tags))
    lines.append("description: %s" % yaml_scalar(
        "Captured by cmdvault from a Claude Code session in project '%s' (used %dx)."
        % (entry["project"], entry["uses"])))
    return "\n".join(lines) + "\n"


def cmd_export(argv):
    if "--warp" not in argv:
        print("usage: cmdvault export --warp [--out DIR] [-p]", file=sys.stderr)
        return 1
    out_dir = default_warp_workflows_dir()
    if "--out" in argv:
        try:
            out_dir = argv[argv.index("--out") + 1]
        except IndexError:
            print("cmdvault: --out needs a directory", file=sys.stderr)
            return 1
    vault = vault_dir()
    entries = load_entries(vault)
    if "-p" in argv:
        current = project_name(os.getcwd())
        entries = [e for e in entries if e["project"] == current]
    if not entries:
        print("cmdvault: nothing to export", file=sys.stderr)
        return 1
    os.makedirs(out_dir, exist_ok=True)
    for e in entries:
        meta, _ = parse_note(e["path"])
        tags = meta.get("tags") or []
        if not isinstance(tags, list):
            tags = [t.strip() for t in str(tags).strip("[]").split(",")]
        extra = [t for t in tags if t and t != "claude-cmd"]
        e["tags_binary"] = extra[0] if extra else ""
        name = "cmdvault-%s-%s.yaml" % (slugify(e["description"]), e["id"])
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write(warp_workflow_yaml(e))
    print("cmdvault: exported %d workflows to %s" % (len(entries), out_dir))
    return 0


def cmd_stats():
    vault = vault_dir()
    entries = load_entries(vault)
    total_uses = sum(e["uses"] for e in entries)
    print("cmdvault: %d commands, %d total uses (vault: %s)" % (len(entries), total_uses, vault))
    for e in entries[:10]:
        print("%5d  %-50s %s" % (e["uses"], e["description"][:50], e["id"]))
    return 0


# ---------------------------------------------------------------- entrypoint

USAGE = "usage: cmdvault.py {capture|pick [-p]|show <id>|stats|export --warp [--out DIR] [-p]}"


def main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if not argv:
        print(USAGE, file=sys.stderr)
        return 1
    sub, rest = argv[0], argv[1:]
    if sub == "capture":
        try:
            return cmd_capture()
        except Exception:
            return 0
    if sub == "pick":
        return cmd_pick(rest)
    if sub == "show":
        return cmd_show(rest)
    if sub == "stats":
        return cmd_stats()
    if sub == "export":
        return cmd_export(rest)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
