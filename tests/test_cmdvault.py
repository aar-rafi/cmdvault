import importlib.util
import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("cmdvault", ROOT / "scripts" / "cmdvault.py")
cv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cv)


@pytest.fixture
def vault(tmp_path, monkeypatch):
    path = tmp_path / "vault"
    monkeypatch.setenv("CMDVAULT_DIR", str(path))
    return path


def capture(monkeypatch, payload):
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    return cv.main(["capture"])


def bash_payload(command, description="", cwd="/tmp/proj", tool_response=None):
    return {
        "session_id": "s1",
        "cwd": cwd,
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": description},
        "tool_response": tool_response if tool_response is not None else {"stdout": "", "stderr": ""},
    }


def notes(vault):
    return sorted(vault.glob("*.md"))


def raw_events(vault):
    path = vault / ".raw" / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------- normalize/id

def test_hash_stable_across_whitespace():
    assert cv.cmd_id("git   status\n") == cv.cmd_id("git status")
    assert cv.normalize("  a\t b \n c ") == "a b c"


def test_hash_differs_for_different_commands():
    assert cv.cmd_id("git status") != cv.cmd_id("git stash")


# ---------------------------------------------------------------- filter

@pytest.mark.parametrize("command", [
    "ls",
    "ls -la /tmp",
    "pwd",
    "cat foo.txt",
    "git status",
    "git diff",
    "git log",
    "git add",
    "npm install",
    "make",
    "mkdir -p some/deep/dir",
    "sudo ls -la /root",
    "FOO=bar env",
])
def test_filter_rejects(command):
    assert not cv.should_store(command)


@pytest.mark.parametrize("command", [
    "ls | grep foo",
    "cat foo.txt | wc -l",
    "git rebase --onto main old feature",
    "git log --oneline --graph",
    "docker run -it --rm ubuntu bash",
    "curl -sL https://example.com/install.sh | sh",
    "find . -name '*.tmp' -delete",
    "for f in *.txt; do mv \"$f\" \"${f%.txt}.md\"; done",
    "line1\nline2",
    "echo hi > out.txt",
])
def test_filter_accepts(command):
    assert cv.should_store(command)


def test_single_token_always_dropped():
    assert not cv.should_store("htop")
    assert not cv.should_store("cargo")


# ---------------------------------------------------------------- success

def test_is_success_variants():
    assert cv.is_success({"stdout": "ok", "stderr": ""})
    assert cv.is_success("plain string response")
    assert not cv.is_success({"interrupted": True})
    assert not cv.is_success({"is_error": True})
    assert not cv.is_success({"error": "boom"})
    assert not cv.is_success({"exit_code": 1})
    assert not cv.is_success({"returnCode": 2})
    assert cv.is_success({"exit_code": 0})


# ---------------------------------------------------------------- capture/upsert

def test_capture_creates_note(vault, monkeypatch):
    rc = capture(monkeypatch, bash_payload(
        "git rebase --onto main old feature", description="Rebase feature onto main"))
    assert rc == 0
    files = notes(vault)
    assert len(files) == 1
    cid = cv.cmd_id("git rebase --onto main old feature")
    assert files[0].name.endswith("-%s.md" % cid)
    meta, command = cv.parse_note(str(files[0]))
    assert command == "git rebase --onto main old feature"
    assert meta["description"] == "Rebase feature onto main"
    assert meta["uses"] == 1
    assert meta["id"] == cid
    assert meta["project"] == "proj"
    assert "claude-cmd" in meta["tags"] and "git" in meta["tags"]
    text = files[0].read_text()
    assert "```bash" in text


def test_repeat_capture_increments_uses(vault, monkeypatch):
    monkeypatch.setattr(cv, "_today", lambda: "2026-07-15")
    capture(monkeypatch, bash_payload("git rebase --onto main old feature", description="Rebase"))
    monkeypatch.setattr(cv, "_today", lambda: "2026-07-16")
    capture(monkeypatch, bash_payload("git rebase   --onto main old feature", description="Rebase again"))
    files = notes(vault)
    assert len(files) == 1
    meta, _ = cv.parse_note(str(files[0]))
    assert meta["uses"] == 2
    assert meta["first_used"] == "2026-07-15"
    assert meta["last_used"] == "2026-07-16"
    assert meta["description"] == "Rebase"  # original description kept


def test_failed_command_not_stored_but_raw_logged(vault, monkeypatch):
    capture(monkeypatch, bash_payload(
        "git rebase --onto main old feature", tool_response={"exit_code": 1, "stderr": "conflict"}))
    assert notes(vault) == []
    events = raw_events(vault)
    assert len(events) == 1
    assert events[0]["tool_input"]["command"] == "git rebase --onto main old feature"
    assert "ts" in events[0]


def test_trivial_command_not_stored_but_raw_logged(vault, monkeypatch):
    capture(monkeypatch, bash_payload("git status"))
    assert notes(vault) == []
    assert len(raw_events(vault)) == 1


def test_garbage_stdin_exits_zero(vault, monkeypatch):
    assert capture(monkeypatch, "this is {{{ not json") == 0
    assert notes(vault) == []


def test_non_bash_tool_ignored(vault, monkeypatch):
    payload = bash_payload("git rebase --onto main old feature")
    payload["tool_name"] = "Write"
    capture(monkeypatch, payload)
    assert notes(vault) == []


def test_backtick_command_gets_longer_fence(vault, monkeypatch):
    command = "echo \"```\" | tee fence.md"
    capture(monkeypatch, bash_payload(command, description="Write a fence"))
    files = notes(vault)
    assert len(files) == 1
    text = files[0].read_text()
    assert "````bash" in text
    _, parsed = cv.parse_note(str(files[0]))
    assert parsed == command


def test_multiline_command_roundtrip(vault, monkeypatch):
    command = "for f in *.txt; do\n  mv \"$f\" \"${f%.txt}.md\"\ndone"
    capture(monkeypatch, bash_payload(command, description="Bulk rename txt to md"))
    files = notes(vault)
    assert len(files) == 1
    _, parsed = cv.parse_note(str(files[0]))
    assert parsed == command


# ---------------------------------------------------------------- helpers

def test_slugify():
    assert cv.slugify("Rebase feature onto main!") == "rebase-feature-onto-main"
    assert cv.slugify("///") == "cmd"
    assert len(cv.slugify("x" * 100)) <= 40


def test_vault_dir_env_override(monkeypatch):
    monkeypatch.setenv("CMDVAULT_DIR", "/some/where")
    assert cv.vault_dir() == "/some/where"


def test_load_entries_sorted_by_uses(vault, monkeypatch):
    capture(monkeypatch, bash_payload("docker run -it --rm ubuntu bash", description="Run ubuntu"))
    capture(monkeypatch, bash_payload("git rebase --onto main old feature", description="Rebase"))
    capture(monkeypatch, bash_payload("git rebase --onto main old feature", description="Rebase"))
    entries = cv.load_entries(str(vault))
    assert [e["uses"] for e in entries] == [2, 1]
    assert entries[0]["command"] == "git rebase --onto main old feature"


# ---------------------------------------------------------------- clipboard

def test_clipboard_backends_x11_order(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    backends = cv.clipboard_backends()
    assert backends[0][0] == "xclip"
    assert backends[-1][0] == "wl-copy"


def test_clipboard_backends_wayland_order(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert cv.clipboard_backends()[0][0] == "wl-copy"


def test_copy_clipboard_skips_failing_tool(monkeypatch):
    # every CLI tool "exists" but fails -> falls through to qdbus/OSC52 path
    monkeypatch.setattr(cv.shutil, "which", lambda name: None)
    monkeypatch.setattr(cv, "open", lambda *a, **k: (_ for _ in ()).throw(OSError()), raising=False)
    assert cv.copy_clipboard("x") is False


# ---------------------------------------------------------------- warp export

def test_warp_workflow_yaml_singleline():
    entry = {"description": "Rebase onto main", "command": "git rebase --onto main old feature",
             "project": "myapp", "uses": 3, "tags_binary": "git"}
    y = cv.warp_workflow_yaml(entry)
    assert 'name: "Rebase onto main"' in y
    assert 'command: "git rebase --onto main old feature"' in y
    assert 'tags: ["cmdvault", "git"]' in y


def test_warp_workflow_yaml_multiline_block():
    entry = {"description": "Loop", "command": "for f in *.txt\ndo\n  echo $f\ndone",
             "project": "p", "uses": 1, "tags_binary": ""}
    y = cv.warp_workflow_yaml(entry)
    assert "command: |\n  for f in *.txt\n  do\n    echo $f\n  done" in y


def test_export_warp_writes_files(vault, tmp_path, monkeypatch):
    capture(monkeypatch, bash_payload("git rebase --onto main old feature", description="Rebase"))
    out = tmp_path / "wf"
    rc = cv.main(["export", "--warp", "--out", str(out)])
    assert rc == 0
    files = list(out.glob("cmdvault-*.yaml"))
    assert len(files) == 1
    text = files[0].read_text()
    assert 'name: "Rebase"' in text
    assert '"git"' in text  # binary tag extracted from note


def test_export_warp_empty_vault(vault, tmp_path):
    rc = cv.main(["export", "--warp", "--out", str(tmp_path / "wf")])
    assert rc == 1


# ---------------------------------------------------------------- v0.2 portability

def test_default_vault_respects_xdg(monkeypatch):
    monkeypatch.delenv("CMDVAULT_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/xdg/data")
    assert cv._default_vault() == "/xdg/data/cmdvault/commands"


def test_pick_numbered_selects_and_prints(vault, monkeypatch, capsys):
    capture(monkeypatch, bash_payload("git rebase --onto main old feature", description="Rebase"))
    entries = cv.load_entries(str(vault))
    monkeypatch.setattr(cv, "copy_clipboard", lambda t: True)
    rc = cv.pick_numbered(entries, input_fn=lambda _: "1")
    assert rc == 0
    assert capsys.readouterr().out.strip() == "git rebase --onto main old feature"


def test_pick_numbered_bad_input(vault, monkeypatch):
    capture(monkeypatch, bash_payload("git rebase --onto main old feature", description="Rebase"))
    entries = cv.load_entries(str(vault))
    assert cv.pick_numbered(entries, input_fn=lambda _: "banana") == 1


def test_clipboard_chain_includes_clip_exe():
    assert ["clip.exe"] in cv.clipboard_backends()
