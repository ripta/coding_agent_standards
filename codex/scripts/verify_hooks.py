#!/usr/bin/env python3
"""Verify that Codex discovers the installed standards startup hook and report its trust state."""

import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


PLUGIN_ID = "coding-standards-portable@coding-standards-portable"


def discover(cwd):
    with tempfile.TemporaryFile(mode="w+") as errors:
        process = subprocess.Popen(
            ["codex", "app-server", "--stdio"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=errors, text=True,
        )
        messages = queue.Queue()

        def read_messages():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    pass
            messages.put(None)

        reader = threading.Thread(target=read_messages, daemon=True)
        reader.start()

        def request(identifier, method, params):
            process.stdin.write(json.dumps({"id": identifier, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    message = messages.get(timeout=max(0.1, deadline - time.monotonic()))
                except queue.Empty:
                    raise RuntimeError(f"Codex timed out while handling {method}")
                if message is None:
                    errors.seek(0)
                    raise RuntimeError(f"Codex app-server exited: {errors.read().strip()}")
                if message.get("id") == identifier:
                    if "error" in message:
                        raise RuntimeError(f"{method}: {message['error']}")
                    return message["result"]
            raise RuntimeError(f"Codex timed out while handling {method}")

        try:
            request(1, "initialize", {
                "clientInfo": {"name": "coding-standards-verification", "version": "1.0.0"},
                "capabilities": {"experimentalApi": True},
            })
            process.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
            process.stdin.flush()
            result = request(2, "hooks/list", {"cwds": [str(cwd)]})
            entries = result.get("data", [])
            discovery_errors = [error for entry in entries for error in entry.get("errors", [])]
            if discovery_errors:
                raise RuntimeError(f"Hook discovery failed: {discovery_errors}")
            return [hook for entry in entries for hook in entry.get("hooks", [])
                    if hook.get("pluginId") == PLUGIN_ID and hook.get("eventName") == "sessionStart"]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdin.close()
            reader.join(timeout=1)
            process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print runtime hook metadata as JSON")
    args = parser.parse_args()
    hooks = discover(Path.cwd())
    if args.json:
        print(json.dumps(hooks, indent=2))
    if not hooks:
        print("FAIL: Codex did not discover the installed standards SessionStart hook.", file=sys.stderr)
        return 1
    ready = all(hook["enabled"] and hook["trustStatus"] in ("trusted", "managed") for hook in hooks)
    if not args.json:
        for hook in hooks:
            print(f"SessionStart hook: enabled={hook['enabled']}, trust={hook['trustStatus']}")
    if not ready:
        print("Open /hooks in Codex CLI, review and trust the standards hook, then rerun this check.", file=sys.stderr)
        return 1
    if not args.json:
        print("PASS: Codex discovers the enabled, trusted standards startup hook.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        sys.exit(f"Hook verification failed: {error}")
