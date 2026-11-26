"""Read the shell commands out of a PreToolUse payload. Shared by the hooks that scan command text.

`private-terms.py` and `rm-rf.py` import this. Both import it with a `sys.path` insert of their own
directory, as the plugin's scripts do for their siblings.

The hooks read three tools. `Bash` carries one shell string. `mcp__cg__cg_run` carries one argv list
and `mcp__cg__cg_run_many` carries a list of them. `rules/shell-discipline.md` sends agents through
the cg tools, so a hook that reads only `Bash` misses most of what an agent runs.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Sequence

CG_RUN, CG_RUN_MANY = "mcp__cg__cg_run", "mcp__cg__cg_run_many"


class BadPayload(ValueError):
    """The payload of a tool the hooks read is not in the shape that tool sends.

    A guard that cannot read a call must not let it run. Python exits 1 on an uncaught error, and
    Claude Code does not block on an exit of 1, so each guard catches this and decides by what the
    raw payload mentions.
    """


def env_assignments(given: dict) -> str:
    """Return the `GIT_` variables a cg call sets, as inline assignments to put before a command.

    A cg call takes an `env` mapping beside its argv. `GIT_DIR` there moves a commit to another
    repo just as it does in a shell, so the text a hook reads must carry it. Other variables are
    left out, since a guard that scans the text for words should not read their values.
    """
    env = given.get("env")
    if not isinstance(env, dict):
        return ""

    return "".join(
        f"{key}={shlex.quote(without_nul(str(value)))} "
        for key, value in env.items()
        if re.fullmatch(r"GIT_[A-Za-z0-9_]+", str(key))
    )


def without_nul(text: str) -> str:
    """Drop NUL bytes, as bash does when it reads a script.

    A NUL in a word made `subprocess` and `os.path` raise, and a hook that raises exits 1.
    """
    return text.replace("\0", "")


def start_directories(payload_cwd: str, given_cwd: object) -> list[str]:
    """Return each directory a cg call may start in.

    The payload's cwd follows the Bash tool's persisted `cd`. The cg server keeps the directory it
    started in, which is normally `$CLAUDE_PROJECT_DIR`. A cg call with no cwd, or a relative one,
    runs from the server's directory, so both are listed when they differ. An absolute cwd needs
    neither.
    """
    bases = [payload_cwd]
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        bases.append(without_nul(project))

    relative = without_nul(given_cwd) if isinstance(given_cwd, str) else ""
    found: list[str] = []
    for base in bases:
        start = os.path.normpath(os.path.join(base, os.path.expanduser(relative)))
        if start not in found:
            found.append(start)
    return found


def tool_commands(payload: object) -> list[tuple[str, str]]:
    """Return (shell text, starting directory) for each command a tool call runs.

    The cg tools take argv lists, so each is joined into a shell string. A shell wrapper then reads
    like a Bash call. A cg call with no cwd may run in the payload's directory or the server's, so
    its command appears once for each. A `GIT_` variable in a cg call's `env` leads the text as an
    assignment. A tool the hooks do not read gives no commands. A call to a tool they do read, in
    the wrong shape, raises BadPayload.
    """
    if not isinstance(payload, dict):
        raise BadPayload("the payload is not an object")

    tool = payload.get("tool_name")
    if tool not in ("Bash", CG_RUN, CG_RUN_MANY):
        return []

    given = payload.get("tool_input")
    if given is None:
        given = {}
    if not isinstance(given, dict):
        raise BadPayload("`tool_input` is not an object")

    cwd = payload.get("cwd")
    cwd = without_nul(cwd) if isinstance(cwd, str) and cwd else os.getcwd()

    if tool == "Bash":
        command = given.get("command")
        if command is None:
            command = ""
        if not isinstance(command, str):
            raise BadPayload("`command` is not a string")
        return [(without_nul(command), cwd)]

    if tool == CG_RUN:
        argvs = given.get("command")
        if argvs is not None and not isinstance(argvs, list):
            raise BadPayload("`command` is not a list")
        argvs = [argvs]
    else:
        argvs = given.get("commands")
        if argvs is not None and not isinstance(argvs, list):
            raise BadPayload("`commands` is not a list")

    assignments = env_assignments(given)
    starts = start_directories(cwd, given.get("cwd"))
    return [
        (assignments + shlex.join(without_nul(str(w)) for w in argv), start)
        for argv in argvs or []
        if isinstance(argv, list)
        for start in starts
    ]


def mentions(text: str, word: str) -> bool:
    """Say whether `text` may spell `word`, with quotes or backslashes cut into it.

    A shell joins `com''mit` into `commit`, and a JSON string escapes the quote around it. A guard
    that cannot parse a payload falls back to this, and it errs toward yes.
    """
    letters = r"[^A-Za-z0-9]{0,8}".join(re.escape(c) for c in word)
    return re.search(letters, text, re.IGNORECASE) is not None


# Long options of a shell that take the next word as a value. Short ones are read letter by letter.
SHELL_VALUE_LONG = {"--rcfile", "--init-file"}


def shell_script_index(words: Sequence[str]) -> int | None:
    """Return the index of the script a shell runs with `-c`, in the words after the shell's name.

    A short option cluster such as `-lc` or `-eo` is read letter by letter. `c` makes the first
    word that is not an option the script. `o` and `O` each take the next word, as in `-o pipefail`
    and `+O extglob`, and so do `--rcfile` and `--init-file`. `--` ends the options. A shell that
    is given no `-c`, or a script file first, gets None.
    """
    wants_script = False
    i = 0

    while i < len(words):
        word = words[i]
        i += 1

        if word == "--":
            return i if wants_script and i < len(words) else None
        if word.startswith("--"):
            i += word in SHELL_VALUE_LONG
        elif len(word) > 1 and word[0] in "-+":
            for letter in word[1:]:
                if letter in "oO":
                    i += 1
                elif letter == "c" and word[0] == "-":
                    wants_script = True
        else:
            return i - 1 if wants_script else None

    return None
