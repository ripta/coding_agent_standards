"""Tests for test_cost.py. Run: uv run --with pytest pytest claude/scripts"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent / "test_cost.py"


def run(*args: str) -> tuple[int, dict, str]:
    proc = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)
    lines = proc.stdout.strip().splitlines()
    record = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
    return proc.returncode, record, proc.stdout


def python(code: str) -> list[str]:
    return ["--", sys.executable, "-c", code]


def test_a_passing_run_reports_its_cost() -> None:
    code, record, _ = run("--label", "tests/test_x.py", *python("pass"))

    assert code == 0
    assert record["label"] == "tests/test_x.py"
    assert record["exit"] == 0
    assert record["wall_s"] >= 0
    assert record["cpu_s"] >= 0
    assert record["max_rss_bytes"] > 0
    assert "budget_s" not in record


def test_peak_memory_is_in_bytes_on_every_platform() -> None:
    # Allocating 64 MiB must show as more than 64 MiB. Linux reports kilobytes, which unscaled would
    # read as about 64 KiB.
    _, record, _ = run(*python("b = bytearray(64 * 1024 * 1024); b[::4096] = b'x' * len(b[::4096])"))

    assert record["max_rss_bytes"] > 64 * 1024 * 1024


def test_the_command_failure_wins_over_the_budget() -> None:
    code, record, _ = run("--budget", "0.001", *python("import time, sys; time.sleep(0.05); sys.exit(5)"))

    assert code == 5
    assert record["exit"] == 5
    assert record["over_budget"] is True


def test_a_passing_run_over_budget_exits_3() -> None:
    code, record, _ = run("--budget", "0.001", *python("import time; time.sleep(0.05)"))

    assert code == 3
    assert record["exit"] == 0
    assert record["budget_s"] == 0.001
    assert record["over_budget"] is True


def test_a_run_within_budget_passes() -> None:
    code, record, _ = run("--budget", "60", *python("pass"))

    assert code == 0
    assert record["over_budget"] is False


def test_a_signal_maps_to_128_plus_its_number() -> None:
    code, record, _ = run(*python("import os, signal; os.kill(os.getpid(), signal.SIGTERM)"))

    assert code == 128 + 15
    assert record["exit"] == 128 + 15


def test_the_command_output_comes_before_the_record() -> None:
    _, record, stdout = run(*python("print('runner output')"))

    assert stdout.splitlines()[0] == "runner output"
    assert record["exit"] == 0


def test_a_missing_command_is_127() -> None:
    code, record, _ = run("--", "/nonexistent/runner")

    assert code == 127
    assert record["exit"] == 127


def test_no_command_is_a_usage_error() -> None:
    code, _, _ = run("--label", "x")

    assert code == 2


def test_a_non_positive_budget_is_a_usage_error() -> None:
    code, _, _ = run("--budget", "0", *python("pass"))

    assert code == 2
