"""Tests for guardian_hooks.py. Run: uv run --with pytest pytest claude/scripts"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).parent / "guardian_hooks.py"
DOMAIN = {"entries": [{"checkout": "/work/cas", "scopes": ["claude/"]}]}


SESSION_END = Path(__file__).parent.parent / "hooks" / "guardian-session-end.sh"
SESSION_ID = "0f9e8d7c-1234-4abc-9def-000000000000"


def run(home: Path, *args: str, stdin: str = "", session_id: str = "") -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home), CLAUDE_CODE_SESSION_ID=session_id)
    return subprocess.run(
        [sys.executable, SCRIPT, *args], input=stdin, capture_output=True, text=True, env=env
    )


def end_session(home: Path, session_id: str) -> None:
    """Run the SessionEnd hook in its own process group, then kill that group as a host may."""
    payload = json.dumps({"hook_event_name": "SessionEnd", "session_id": session_id, "reason": "other"})
    env = dict(os.environ, HOME=str(home))
    proc = subprocess.Popen(
        [SESSION_END], stdin=subprocess.PIPE, text=True, env=env, start_new_session=True
    )
    proc.communicate(payload)
    assert proc.returncode == 0

    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def wait_for(path: Path) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return path.read_text()
        time.sleep(0.05)
    raise AssertionError(f"{path} never appeared")


def add_hook(home: Path, event: str, name: str, body: str, executable: bool = True) -> Path:
    directory = home / ".config" / "coding_agent_standards" / "guardian-hooks" / event
    directory.mkdir(parents=True, exist_ok=True)
    hook = directory / name
    hook.write_text(f"#!/bin/sh\n{body}\n")
    if executable:
        hook.chmod(0o755)
    return hook


def test_no_hook_directory_runs_nothing(tmp_path: Path) -> None:
    result = run(tmp_path, "start", "cas", stdin=json.dumps(DOMAIN))

    assert result.returncode == 0
    assert json.loads(result.stdout) == []


def test_start_saves_the_domain_and_feeds_hooks_the_payload(tmp_path: Path) -> None:
    add_hook(tmp_path, "start", "10-echo", "cat")

    result = run(tmp_path, "start", "cas", stdin=json.dumps(DOMAIN))

    assert result.returncode == 0
    [item] = json.loads(result.stdout)
    assert item["status"] == 0
    assert json.loads(item["stdout"]) == {
        "event": "start",
        "domain_name": "cas",
        "session_name": "cas_guardian",
        "entries": DOMAIN["entries"],
    }
    saved = tmp_path / ".local" / "state" / "coding_agent_standards" / "guardians" / "cas" / "domain.json"
    assert json.loads(saved.read_text()) == DOMAIN


def test_stop_reads_the_domain_start_saved(tmp_path: Path) -> None:
    run(tmp_path, "start", "cas", stdin=json.dumps(DOMAIN))
    add_hook(tmp_path, "stop", "release", "cat")

    result = run(tmp_path, "stop", "cas")

    assert result.returncode == 0
    [item] = json.loads(result.stdout)
    assert json.loads(item["stdout"])["event"] == "stop"
    assert json.loads(item["stdout"])["entries"] == DOMAIN["entries"]


def test_stop_without_hooks_needs_no_saved_domain(tmp_path: Path) -> None:
    result = run(tmp_path, "stop", "cas")

    assert result.returncode == 0
    assert json.loads(result.stdout) == []


def test_hooks_run_in_name_order_and_skip_dotfiles_and_non_executables(tmp_path: Path) -> None:
    add_hook(tmp_path, "start", "20-second", "echo second")
    add_hook(tmp_path, "start", "10-first", "echo first")
    add_hook(tmp_path, "start", ".hidden", "echo hidden")
    add_hook(tmp_path, "start", "30-off", "echo off", executable=False)

    result = run(tmp_path, "start", "cas", stdin=json.dumps(DOMAIN))

    assert [item["stdout"].strip() for item in json.loads(result.stdout)] == ["first", "second"]


def test_a_failing_hook_does_not_stop_the_others(tmp_path: Path) -> None:
    add_hook(tmp_path, "start", "10-fails", "echo broken >&2; exit 3")
    add_hook(tmp_path, "start", "20-works", "echo ok")

    result = run(tmp_path, "start", "cas", stdin=json.dumps(DOMAIN))

    assert result.returncode == 0
    failed, worked = json.loads(result.stdout)
    assert (failed["status"], failed["stderr"].strip()) == (3, "broken")
    assert (worked["status"], worked["stdout"].strip()) == (0, "ok")


def test_scopes_default_to_the_whole_checkout(tmp_path: Path) -> None:
    add_hook(tmp_path, "start", "echo", "cat")

    result = run(tmp_path, "start", "cas", stdin=json.dumps({"entries": [{"checkout": "/work/cas"}]}))

    [item] = json.loads(result.stdout)
    assert json.loads(item["stdout"])["entries"] == [{"checkout": "/work/cas", "scopes": []}]


def test_a_relative_checkout_is_rejected(tmp_path: Path) -> None:
    result = run(tmp_path, "start", "cas", stdin=json.dumps({"entries": [{"checkout": "cas"}]}))

    assert result.returncode == 1
    assert "absolute" in result.stderr


def test_usage_errors(tmp_path: Path) -> None:
    assert run(tmp_path, "begin", "cas").returncode == 1
    assert run(tmp_path, "start").returncode == 1
    assert run(tmp_path, "start", "../x", stdin=json.dumps(DOMAIN)).returncode == 1
    assert run(tmp_path, "start", "cas", "--detach", stdin=json.dumps(DOMAIN)).returncode == 1


def test_session_end_runs_the_stop_hooks_for_the_session_that_started(tmp_path: Path) -> None:
    out = tmp_path / "released"
    add_hook(tmp_path, "stop", "release", f"sleep 1; cat > {out}")
    run(tmp_path, "start", "cas", stdin=json.dumps(DOMAIN), session_id=SESSION_ID)
    record = tmp_path / ".local" / "state" / "coding_agent_standards" / "guardians" / "by-session" / SESSION_ID
    assert record.read_text() == "cas\n"

    end_session(tmp_path, SESSION_ID)

    assert json.loads(wait_for(out))["domain_name"] == "cas"
    assert not record.exists()


def test_session_end_ignores_a_session_that_is_not_a_guardian(tmp_path: Path) -> None:
    out = tmp_path / "released"
    add_hook(tmp_path, "stop", "release", f"cat > {out}")
    run(tmp_path, "start", "cas", stdin=json.dumps(DOMAIN), session_id=SESSION_ID)

    end_session(tmp_path, "another-session")
    time.sleep(0.5)

    assert not out.exists()

