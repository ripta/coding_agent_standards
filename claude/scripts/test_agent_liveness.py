"""Tests for agent_liveness.py. Run: uv run --with pytest pytest claude/scripts"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import agent_liveness


def _use(ts, call_id, name, command=None):
    tool_input = {"command": command} if command is not None else {"file_path": "x"}
    block = {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {"content": [block]}})


def _result(ts, call_id):
    block = {"type": "tool_result", "tool_use_id": call_id, "content": "ok"}
    return json.dumps({"type": "user", "timestamp": ts, "message": {"content": [block]}})


def test_pending_call_reports_name_and_command():
    lines = [
        _use("t1", "a", "Read"),
        _result("t2", "a"),
        _use("t3", "b", "mcp__cg__cg_run", ["make", "test"]),
    ]
    assert agent_liveness.liveness(lines) == {
        "last": "t3",
        "pending": [{"name": "mcp__cg__cg_run", "command": ["make", "test"]}],
    }


def test_finished_calls_are_not_pending():
    lines = [_use("t1", "a", "Bash", "ls"), _result("t2", "a")]
    assert agent_liveness.liveness(lines) == {"last": "t2", "pending": []}


def test_partial_and_untimed_lines_are_skipped():
    lines = [
        _use("t1", "a", "Read"),
        json.dumps({"type": "api-request-blob", "message": {"content": "text"}}),
        '{"type": "user", "timest',
    ]
    result = agent_liveness.liveness(lines)
    assert result["last"] == "t1"
    assert result["pending"] == [{"name": "Read", "command": None}]


def test_missing_file_exits_1(tmp_path, capsys):
    assert agent_liveness.main(["agent_liveness.py", str(tmp_path / "nope.jsonl")]) == 1
    assert "agent_liveness:" in capsys.readouterr().err
