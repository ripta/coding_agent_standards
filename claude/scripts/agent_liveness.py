#!/usr/bin/env python3
"""Report what a subagent's transcript says about whether it is still working.

    python3 agent_liveness.py TRANSCRIPT

TRANSCRIPT is the JSONL file a task notification names as its `<output-file>`.
The result is JSON on stdout. `last` is the timestamp of the latest entry.
`pending` lists each tool call that has no result yet, with its tool name and,
when the call has one, its command. Lines that are not JSON are skipped, since
the agent may be writing the last one. Errors go to stderr with exit status 1.
"""

import json
import sys
from typing import Any


def _blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict)]


def liveness(lines: list[str]) -> dict[str, Any]:
    last = None
    calls: dict[str, dict[str, Any]] = {}
    done: set[str] = set()
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("timestamp"):
            last = entry["timestamp"]
        for block in _blocks(entry):
            if entry.get("type") == "assistant" and block.get("type") == "tool_use":
                tool_input = block.get("input")
                command = tool_input.get("command") if isinstance(tool_input, dict) else None
                calls[block.get("id", "")] = {"name": block.get("name"), "command": command}
            elif entry.get("type") == "user" and block.get("type") == "tool_result":
                done.add(block.get("tool_use_id", ""))
    pending = [call for call_id, call in calls.items() if call_id not in done]
    return {"last": last, "pending": pending}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    try:
        with open(argv[1], encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"agent_liveness: {e}", file=sys.stderr)
        return 1
    json.dump(liveness(lines), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
