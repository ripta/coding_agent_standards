#!/usr/bin/env python3
"""Measure one test run's cost, for a project's `make test-cost` target.

    python3 test_cost.py [--label NAME] [--budget SECONDS] -- COMMAND [ARG ...]

Runs COMMAND once and prints one JSON line on stdout: the label, the exit status, wall time,
CPU time, and peak memory. A project's target calls it once per new or changed test file, with
that file's runner command and its budget. The line is stable and appendable, so a project can
collect lines across runs and read the trend. No single run needs to be accurate.

The target owns everything about the project: which runner command measures one file with no
parallelism, and how a file's budget carve-out is written and parsed. This script only measures.

CPU time is user plus system time of COMMAND and every descendant it waited for. Peak memory is
the largest resident set of any one of those processes, not their sum. Both come from getrusage,
so they are absent on a platform without the resource module.

Exit status is COMMAND's own when it fails, or 128 plus the signal number when a signal killed it.
When COMMAND succeeds but wall time exceeds --budget, the exit status is 3. Status 2 is a usage
error. COMMAND's output passes through to this script's stdout and stderr, before the JSON line.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

try:
    import resource
except ImportError:
    resource = None

OVER_BUDGET = 3


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure one test run's cost.")
    parser.add_argument("--label", default="", help="name for the run, such as the test file")
    parser.add_argument("--budget", type=float, default=None, help="wall-time budget in seconds")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="the command, after --")
    args = parser.parse_args(argv)

    if args.command and args.command[0] == "--":
        args.command = args.command[1:]

    if not args.command:
        parser.error("a command is required after --")

    if args.budget is not None and args.budget <= 0:
        parser.error("--budget must be positive")

    return args


def peak_rss_bytes(maxrss: int) -> int:
    # macOS reports ru_maxrss in bytes, and Linux in kilobytes.
    if sys.platform == "darwin":
        return maxrss
    return maxrss * 1024


def measure(command: list[str]) -> dict:
    before = resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None
    start = time.monotonic()

    try:
        returncode = subprocess.call(command)
    except OSError as err:
        print(f"test_cost: cannot run {command[0]}: {err}", file=sys.stderr)
        returncode = 127

    wall = time.monotonic() - start
    result = {"exit": returncode if returncode >= 0 else 128 - returncode, "wall_s": round(wall, 3)}

    if before is not None:
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
        result["cpu_s"] = round(cpu, 3)
        result["max_rss_bytes"] = peak_rss_bytes(after.ru_maxrss)

    return result


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = {"label": args.label or " ".join(args.command)}
    result.update(measure(args.command))

    if args.budget is not None:
        result["budget_s"] = args.budget
        result["over_budget"] = result["wall_s"] > args.budget

    sys.stdout.flush()
    print(json.dumps(result, sort_keys=True))

    if result["exit"] != 0:
        return result["exit"]

    if result.get("over_budget"):
        return OVER_BUDGET

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
