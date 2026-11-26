#!/usr/bin/env python3
"""Block commits that carry private terms into a public repo.

    private-terms.py pretooluse         PreToolUse hook on Bash and the cg tools; payload on stdin
    private-terms.py pre-commit         git pre-commit hook; checks the staged diff
    private-terms.py commit-msg FILE    git commit-msg hook; checks the message in FILE

Terms come from ~/.config/coding_agent_standards/private-terms.txt, one per line, with blank
lines and # comments ignored. A term matches as a whole word, case-insensitively. Without the
file, every mode allows everything.

Only repos whose visibility is public or unknown are checked. Visibility comes from
`git config codingstandards.visibility`, then from the host through `gh repo view`.

The hook finds a commit by reading the command's words, and it expands nothing. A commit whose
target repo or contents it cannot work out is denied, with the command to rerun. It does not see a
git alias, `make commit`, or a script that commits inside. It runs git in a directory the command
names, so every git call turns off the programs a repo can configure, such as textconv, fsmonitor,
and filter drivers. A hook that cannot read a call denies it when the call mentions a commit, since
an error that exits 1 does not block. See "Private Terms" in hooks/README.md.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from toolcalls import mentions, shell_script_index, tool_commands  # noqa: E402

TERMS = Path.home() / ".config" / "coding_agent_standards" / "private-terms.txt"
CACHE = Path.home() / ".local" / "state" / "coding_agent_standards" / "term-guard" / "visibility.json"

# A public result is kept forever, since a public repo going private only costs extra checks. A
# private one expires so that a repo made public is caught within a day.
PRIVATE_TTL = 24 * 60 * 60

HOST_VISIBILITY = {"PUBLIC": "public", "PRIVATE": "private", "INTERNAL": "protected"}
LEVELS = ("private", "protected", "public")

GIT_COMMIT = re.compile(r"\bgit\b[^\n;&|]*\bcommit\b")

SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "ash"}

# Words that may stand before a command's name without being it.
OPENERS = {"{", "!", "if", "then", "elif", "else", "do", "while", "until", "time", "command", "builtin"}

OPERATORS = ("&&", "||", ";", "|", "&", "(", ")", "`", "\n")

ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)

# Variables that move a commit to another repo or another index. A command sets them for one call,
# or exports them.
REDIRECTING = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")

# A word the shell must expand before anyone can tell what it is.
NEEDS_SHELL = re.compile(r"[$`*?\[{]")

# A command word that is a variable or a substitution may expand to `git`.
EXPANDS_TO_COMMAND = re.compile(r"[$`]")

# Commands that run the command they are given, so that command may follow them.
WRAPPERS = {"sudo", "doas", "env", "exec", "nohup", "nice", "time", "xargs", "command", "timeout"}

# Every long option of `git commit`, and what it takes: nothing, a value that is the next word or
# follows an `=`, or an optional value that only an `=` can give. Git accepts any prefix of a name
# that fits one option, so the names must be git's own. A name missing here reads as unknown.
COMMIT_LONG = {
    "ahead-behind": "",
    "all": "",
    "allow-empty": "",
    "allow-empty-message": "",
    "amend": "",
    "author": "=",
    "branch": "",
    "cleanup": "=",
    "date": "=",
    "dry-run": "",
    "edit": "",
    "file": "=",
    "fixup": "=",
    "gpg-sign": "?",
    "help": "",
    "include": "",
    "interactive": "",
    "long": "",
    "message": "=",
    "null": "",
    "only": "",
    "patch": "",
    "pathspec-file-nul": "",
    "pathspec-from-file": "=",
    "porcelain": "",
    "post-rewrite": "",
    "quiet": "",
    "reedit-message": "=",
    "reset-author": "",
    "reuse-message": "=",
    "short": "",
    "signoff": "",
    "squash": "=",
    "status": "",
    "template": "=",
    "trailer": "=",
    "untracked-files": "?",
    "verbose": "",
    "verify": "",
}

COMMIT_SHORT = {
    "a": "all",
    "C": "reuse-message",
    "c": "reedit-message",
    "e": "edit",
    "F": "file",
    "h": "help",
    "i": "include",
    "m": "message",
    "n": "verify",
    "o": "only",
    "p": "patch",
    "q": "quiet",
    "S": "gpg-sign",
    "s": "signoff",
    "t": "template",
    "u": "untracked-files",
    "v": "verbose",
    "z": "null",
}

# Global options of `git` that take the next word as a value. `-C`, `-c`, `--git-dir`, and
# `--work-tree` are read where they matter. Git matches these by exact name, with no prefixes.
GLOBAL_VALUE_OPTIONS = {"--namespace", "--config-env", "--attr-source"}

# The operands that mean standard input, where no file is read.
STDIN_OPERANDS = {"-", "/dev/stdin"}

# Nesting deeper than this is not followed. A real command does not nest shells this far.
MAX_DEPTH = 5

# The largest `--pathspec-from-file` or message file the hook reads. A real one is far smaller.
MAX_PATHSPEC_FILE = 1 << 20
MAX_MESSAGE_FILE = 1 << 20

# The largest untracked file the hook reads when a commit may add any file. A larger one is denied.
MAX_UNTRACKED_FILE = 16 << 20

# The tree of a repo with no commit, which a first commit is compared with.
EMPTY_TREES = {
    "sha1": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
    "sha256": "6ef19b41225c5369f1c104d45d8d85efa9b057b53b14b4b9b939dd74decc5321",
}

DIFF_FLAGS = ("--no-color", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "-U0")


def load_terms() -> list[str]:
    try:
        lines = TERMS.read_text(errors="replace").splitlines()
    except OSError:
        return []

    return [t.strip() for t in lines if t.strip() and not t.strip().startswith("#")]


def matcher(terms: list[str]) -> re.Pattern:
    alternatives = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9])", re.IGNORECASE)


class Target(NamedTuple):
    """A repo to read.

    `directory` is where git runs, and pathspecs are relative to it. `git_dir` and `work_tree` are
    the absolute paths a command named for GIT_DIR and GIT_WORK_TREE, or None. `index_file` is the
    absolute path a command named for GIT_INDEX_FILE, or None for the repo's own index.
    """

    directory: str
    git_dir: str | None = None
    work_tree: str | None = None
    index_file: str | None = None


class CannotReadSafely(Exception):
    """Git cannot be run here without running a program the repo configures."""


def base_argv(target: Target) -> list[str]:
    argv = ["git", "--no-pager", "-c", "core.fsmonitor=false"]
    if target.git_dir:
        argv += ["--git-dir", target.git_dir]
    if target.work_tree:
        argv += ["--work-tree", target.work_tree]
    return [*argv, "-C", target.directory]


FILTER_KEY = re.compile(r"filter\.(.+)\.(?:clean|process|required)")


@functools.lru_cache(maxsize=None)
def filter_overrides(target: Target) -> tuple[str, ...]:
    """Return `git -c` arguments that turn off every filter driver the repo defines.

    Git runs a driver's clean command or process when it compares the working tree to the index or
    a commit, which `git diff HEAD` does. No flag stops that. A driver with an empty command does
    nothing, and a driver that is not required cannot fail the diff for that. The names come from
    the repo's own config, since an attribute file may name any of them.

    The arguments are `-c` pairs, which every git version reads. A name that holds `=` cannot be
    spelled in a pair, since git splits the pair at the first `=`. Such a driver cannot be turned
    off, so the repo cannot be read.
    """
    try:
        listing = subprocess.run(
            [*base_argv(target), "config", "--list", "-z"], capture_output=True, text=True, errors="replace"
        )
    except OSError as exc:
        raise CannotReadSafely(f"Git could not be run: {exc.strerror}.") from exc

    pairs: dict[str, str] = {}
    for entry in listing.stdout.split("\0") if listing.returncode == 0 else []:
        match = FILTER_KEY.fullmatch(entry.split("\n", 1)[0])
        if not match:
            continue

        name = match.group(1)
        if "=" in name:
            raise CannotReadSafely(
                f"The repo's config defines a filter driver named `{name}`. Git cannot turn off a "
                "driver whose name holds `=`, and a diff would run its program. Remove that driver "
                "from the repo's config, or have the user make the commit."
            )

        pairs[f"filter.{name}.clean"] = ""
        pairs[f"filter.{name}.process"] = ""
        pairs[f"filter.{name}.required"] = "false"

    return tuple(arg for key, value in pairs.items() for arg in ("-c", f"{key}={value}"))


def git(target: Target, *args: str) -> str | None:
    """Run git in a repo the command named, without running the programs the repo configures.

    Hooks run outside the sandbox, and the repo may not be one the user trusts. Git runs a program
    for a textconv, an external diff, a filter driver, and an fsmonitor hook. The flags and config
    here turn each off. `safe.directory` is left as the user set it, so git refuses a repo that
    another user owns, the way the commit itself will.

    Output that is not UTF-8 is decoded with replacement. A strict decode would raise on a file
    in another encoding, and the hook would fail open. Git that cannot be run, or a repo it cannot
    be run on safely, raises CannotReadSafely, and the commit is denied.
    """
    argv = [*base_argv(target), *filter_overrides(target), *args]
    environment = {**os.environ, "GIT_INDEX_FILE": target.index_file} if target.index_file else None
    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace", env=environment)
    except OSError as exc:
        raise CannotReadSafely(f"Git could not be run: {exc.strerror}.") from exc

    if result.returncode != 0:
        return None
    return result.stdout


def remote_url(target: Target) -> str | None:
    upstream = git(target, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    names = (git(target, "remote") or "").split()
    candidates = []
    if upstream and "/" in upstream:
        candidates.append(upstream.strip().split("/", 1)[0])
    candidates += ["origin"] + names

    for name in candidates:
        if name in names:
            url = git(target, "remote", "get-url", "--push", name)
            if url:
                return url.strip()
    return None


def read_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def write_cache(cache: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
        tmp.replace(CACHE)
    except OSError:
        pass


def host_visibility(url: str) -> str | None:
    cache = read_cache()
    hit = cache.get(url)
    if hit and (hit["visibility"] == "public" or time.time() - hit["checked"] < PRIVATE_TTL):
        return hit["visibility"]

    try:
        result = subprocess.run(
            ["gh", "repo", "view", url, "--json", "visibility", "--jq", ".visibility"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    visibility = HOST_VISIBILITY.get(result.stdout.strip()) if result.returncode == 0 else None
    if visibility is None:
        return None

    cache[url] = {"visibility": visibility, "checked": int(time.time())}
    write_cache(cache)
    return visibility


def visibility(target: Target) -> str | None:
    declared = (git(target, "config", "--get", "codingstandards.visibility") or "").strip().lower()
    if declared in LEVELS:
        return declared

    url = remote_url(target)
    return host_visibility(url) if url else None


def added_lines(diff: str) -> list[tuple[str, int, str]]:
    """Return (path, line number, text) for every added line in a unified diff."""
    out = []
    path, line = "", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line = int(m.group(1)) if m else 0
        elif raw.startswith("+"):
            out.append((path, line, raw[1:]))
            line += 1
        elif not raw.startswith("-"):
            line += 1
    return out


class Place(NamedTuple):
    """The directory a command runs in.

    `directory` is None when the hook could not follow how the command got there. `why` then says
    which step it could not follow.
    """

    directory: str | None
    why: str = ""


class Commit(NamedTuple):
    """A `git commit` found in a command.

    `directory` is where git runs it, or None when the hook could not place it, and `why` says
    what stopped it. Pathspecs are relative to `directory`. `git_dir` and `work_tree` are the
    absolute paths a command set through GIT_DIR, GIT_WORK_TREE, or the flags of the same names.
    `pathspec_file` is the raw operand of `--pathspec-from-file`. `index_file` is the raw value of
    GIT_INDEX_FILE. `message_files` are the raw operands of `-F` and `-t`. `widen` is "" when the
    commit takes the index, the paths, or `-a`. It is "worktree" when the commit may take any change
    to a tracked file, and "everything" when it may take any file.
    """

    directory: str | None
    paths: tuple[str, ...]
    commit_all: bool
    git_dir: str | None = None
    work_tree: str | None = None
    pathspec_file: str | None = None
    pathspec_nul: bool = False
    why: str = ""
    index_file: str | None = None
    message_files: tuple[str, ...] = ()
    widen: str = ""


class Token(NamedTuple):
    """A piece of a shell script.

    A `kind` of "word" is a word with its quotes removed. An "op" is an operator. A "body" is the
    text of a heredoc. `glued` marks a substitution that starts right after a word, as `x=$(...)`.
    """

    kind: str
    text: str
    glued: bool = False


def heredoc_at(script: str, i: int) -> tuple[str, bool, int] | None:
    """Read a heredoc operator at script[i]. Return (delimiter, strip tabs, end), or None."""
    j = i + 2
    strip_tabs = j < len(script) and script[j] == "-"
    j += strip_tabs
    while j < len(script) and script[j] in " \t":
        j += 1

    start = j
    delimiter: list[str] = []
    while j < len(script) and script[j] not in " \t\r\n;&|()<>":
        c = script[j]
        if c == "\\" and j + 1 < len(script):
            delimiter.append(script[j + 1])
            j += 2
        elif c in "'\"":
            close = script.find(c, j + 1)
            if close < 0:
                return None
            delimiter.append(script[j + 1 : close])
            j = close + 1
        else:
            delimiter.append(c)
            j += 1

    if j == start:
        return None
    return "".join(delimiter), strip_tabs, j


def heredoc_body(script: str, start: int, delimiter: str, strip_tabs: bool) -> tuple[str, int] | None:
    """Find the heredoc body that begins at script[start]. Return (body, where the script resumes).

    The body ends at a line that is the delimiter. A body with no such line is None. A `<<` in
    `$((1 << 2))` has none, so it is a shift and not a heredoc. Reading it as a heredoc would hide
    every command after it.
    """
    pos = start
    while pos <= len(script):
        end = script.find("\n", pos)
        line = script[pos : len(script) if end < 0 else end]
        if (line.lstrip("\t") if strip_tabs else line) == delimiter:
            return script[start:pos], len(script) if end < 0 else end + 1
        if end < 0:
            return None
        pos = end + 1
    return None


def take_bodies(script: str, start: int, pending: list[tuple[str, bool]], tokens: list[Token]) -> int:
    """Skip the heredoc bodies that start after a newline. Return where the script resumes."""
    pos = start
    for delimiter, strip_tabs in pending:
        body = heredoc_body(script, pos, delimiter, strip_tabs)
        if body is None:
            break
        text, pos = body
        tokens.append(Token("body", text))
    return pos


def tokenize(script: str) -> list[Token]:
    """Split a shell script into word, operator, and heredoc body tokens.

    Quotes group a word and are dropped. An unterminated quote runs to the end. This finds commit
    commands. It expands nothing, so a word that needs expansion keeps its `$` or backtick. A `$(`
    comes out as one operator, so the words after the substitution still join the outer command.
    """
    tokens: list[Token] = []
    word: list[str] = []
    in_word = False
    pending: list[tuple[str, bool]] = []
    i = 0

    def flush() -> None:
        nonlocal word, in_word
        if in_word:
            tokens.append(Token("word", "".join(word)))
        word, in_word = [], False

    while i < len(script):
        c = script[i]
        heredoc = None
        if script.startswith("<<", i) and not script.startswith("<<<", i):
            heredoc = heredoc_at(script, i)

        if c == "\\" and i + 1 < len(script):
            if script[i + 1] != "\n":
                word.append(script[i + 1])
                in_word = True
            i += 2
        elif c == "'":
            close = script.find("'", i + 1)
            close = len(script) if close < 0 else close
            word.append(script[i + 1 : close])
            in_word = True
            i = close + 1
        elif c == '"':
            i += 1
            while i < len(script) and script[i] != '"':
                if script[i] == "\\" and i + 1 < len(script) and script[i + 1] in '"\\$`\n':
                    if script[i + 1] != "\n":
                        word.append(script[i + 1])
                    i += 2
                else:
                    word.append(script[i])
                    i += 1
            in_word = True
            i += 1
        elif c in " \t\r":
            flush()
            i += 1
        elif c == "#" and not in_word:
            while i < len(script) and script[i] != "\n":
                i += 1
        elif script.startswith("<<<", i):
            word.append("<<<")
            in_word = True
            i += 3
        elif heredoc:
            delimiter, strip_tabs, i = heredoc
            digits = "".join(word) if in_word else ""
            if digits.isdigit():
                word, in_word = [], False
            else:
                flush()
                digits = ""
            tokens.append(Token("word", f"{digits}<<{'-' if strip_tabs else ''}{delimiter}"))
            pending.append((delimiter, strip_tabs))
        else:
            op = next((o for o in OPERATORS if script.startswith(o, i)), None)

            # The & of `2>&1`, `>&2`, and `&>file` belongs to a redirection, not a background job.
            if op == "&" and (script.startswith("&>", i) or "".join(word).endswith((">", "<"))):
                op = None

            if op is None:
                word.append(c)
                in_word = True
                i += 1
                continue

            width = len(op)
            text = "".join(word)
            if op == "(" and text.endswith("$"):
                word, in_word, op = [text[:-1]], text != "$", "$("
            glued = in_word

            flush()
            tokens.append(Token("op", op, glued))
            i += width

            if op == "\n" and pending:
                i = take_bodies(script, i, pending, tokens)
                pending = []

    flush()
    return tokens


def moved(here: Place, operand: str | None, what: str) -> Place:
    """Return the place that `cd operand` reaches from `here`.

    `what` names the command in a reason, as in "cd ".

    No operand means the home directory. An operand that needs the shell to expand it, or that names
    the previous directory, cannot be told. An absolute operand needs no starting point.
    """
    if operand is None:
        return Place(os.path.expanduser("~"))
    if operand == "-":
        return Place(None, f"`{what}{operand}` goes to the previous directory")
    if NEEDS_SHELL.search(operand):
        return Place(None, f"`{what}{operand}` needs the shell to expand it")

    target = os.path.expanduser(operand)
    if target.startswith("~"):
        return Place(None, f"`{what}{operand}` needs the shell to expand it")
    if os.path.isabs(target):
        return Place(os.path.normpath(target))
    if here.directory is None:
        return here
    return Place(os.path.normpath(os.path.join(here.directory, target)))


def is_redirect(word: str) -> bool:
    return re.match(r"(\d*|&)[<>]", word) is not None


def cd_operand(args: list[str]) -> str | None:
    args = [a for a in args if not is_redirect(a)]
    i = 0
    while i < len(args) and args[i] != "-" and args[i].startswith("-"):
        i += 1
        if args[i - 1] == "--":
            break
    return args[i] if i < len(args) else None


def resolve_option(name: str, options: dict, negatable: bool = True) -> tuple[str, bool] | None:
    """Resolve a long option's name the way git's option parser does.

    An exact name wins. Otherwise any prefix that fits one option stands for it, and `no-` plus a
    prefix fits the negation of an option when `negatable` is set. Return (option, negated), or None
    when the name fits no option or fits more than one. Git refuses the second case, and a caller
    treats both as unknown.
    """
    if name in options:
        return name, False
    if negatable and name.startswith("no-") and name[3:] in options:
        return name[3:], True

    found = {(option, False) for option in options if option.startswith(name)}
    if negatable:
        found |= {(option, True) for option in options if f"no-{option}".startswith(name)}

    if len({option for option, _ in found}) == 1:
        return next(iter(found))
    return None


class Args(NamedTuple):
    paths: tuple[str, ...]
    commit_all: bool
    pathspec_file: str | None
    pathspec_nul: bool
    message_files: tuple[str, ...]
    widen: str


def commit_args(args: list[str]) -> Args:
    """Read what a commit takes from the words after `commit`, as git reads its options.

    Long options may be abbreviated, short ones may be clustered, and a value may follow its option
    as the next word or sit inside the word. Pathspecs may come before, between, or after options.
    `-p` and `--patch` take working-tree hunks that nothing staged. `--interactive` may take any
    file. An option this does not know may take anything. Each reads the working tree instead of
    the index, which holds whatever the commit could take.

    A negated option such as `--no-all` keeps the effect of its positive form. That reads more than
    the commit takes, which is the safe error.
    """
    paths: list[str] = []
    events: list[tuple[str, bool, str | None]] = []
    unknown = False
    options = True
    i = 0

    while i < len(args):
        word = args[i]
        i += 1

        if is_redirect(word):
            if re.fullmatch(r"(\d*|&)(<<?<?|>>?)", word):
                i += 1
        elif not options or word == "-" or not word.startswith("-"):
            paths.append(word)
        elif word == "--":
            options = False
        elif word.startswith("--"):
            name, has_value, value = word[2:].partition("=")
            found = resolve_option(name, COMMIT_LONG)
            if found is None:
                unknown = True
                continue

            option, negated = found
            takes = "" if negated else COMMIT_LONG[option]
            if has_value:
                given = value
            elif takes == "=":
                given = args[i] if i < len(args) else None
                i += 1
            else:
                given = None
            events.append((option, negated, given))
        else:
            letters = word[1:]
            j = 0
            while j < len(letters):
                option = COMMIT_SHORT.get(letters[j])
                j += 1
                if option is None:
                    unknown = True
                    break

                takes = COMMIT_LONG[option]
                rest = letters[j:]
                if takes == "=" and not rest:
                    events.append((option, False, args[i] if i < len(args) else None))
                    i += 1
                    break
                if takes:
                    events.append((option, False, rest or None))
                    break
                events.append((option, False, None))

    commit_all = False
    pathspec_file = None
    pathspec_nul = False
    message_files: list[str] = []
    widen = "everything" if unknown else ""

    for option, negated, value in events:
        if option == "all":
            commit_all = True
        elif option == "patch" and not widen:
            widen = "worktree"
        elif option == "interactive":
            widen = "everything"
        elif option in ("file", "template") and not negated and value is not None:
            message_files.append(value)
        elif option == "pathspec-from-file" and not negated:
            pathspec_file = value or ""
        elif option == "pathspec-file-nul":
            pathspec_nul = True

    return Args(tuple(paths), commit_all, pathspec_file, pathspec_nul, tuple(message_files), widen)


def git_invocation(words: list[str], i: int, here: Place, env: dict) -> tuple[Commit | None, int]:
    """Read the git command whose arguments start at words[i]. Return its commit and its end."""
    place = here
    git_dir = env.get("GIT_DIR")
    work_tree = env.get("GIT_WORK_TREE")

    while i < len(words):
        word = words[i]
        if word == "-C" and i + 1 < len(words):
            place = moved(place, words[i + 1], "git -C ")
            i += 2
        elif word == "-c" and i + 1 < len(words):
            i += 2
        elif word == "--git-dir" and i + 1 < len(words):
            git_dir = words[i + 1]
            i += 2
        elif word == "--work-tree" and i + 1 < len(words):
            work_tree = words[i + 1]
            i += 2
        elif word in GLOBAL_VALUE_OPTIONS and i + 1 < len(words):
            i += 2
        elif word.startswith("--git-dir="):
            git_dir = word.split("=", 1)[1]
            i += 1
        elif word.startswith("--work-tree="):
            work_tree = word.split("=", 1)[1]
            i += 1
        elif word.startswith("-"):
            i += 1
        else:
            break

    if i >= len(words) or words[i] != "commit":
        return None, i

    args = commit_args(words[i + 1 :])
    resolved = {}
    for name, operand in (("GIT_DIR", git_dir), ("GIT_WORK_TREE", work_tree)):
        if operand and place.directory is not None:
            found = moved(place, operand, f"{name}=")
            if found.directory is None:
                place = found
            resolved[name] = found.directory

    if place.directory is None:
        return Commit(None, args.paths, args.commit_all, why=place.why), len(words)

    commit = Commit(
        place.directory,
        args.paths,
        args.commit_all,
        resolved.get("GIT_DIR"),
        resolved.get("GIT_WORK_TREE"),
        args.pathspec_file,
        args.pathspec_nul,
        index_file=env.get("GIT_INDEX_FILE") or None,
        message_files=args.message_files,
        widen=args.widen,
    )
    return commit, len(words)


def shell_script(words: list[str], i: int) -> str | None:
    """Return the script a shell is given with -c, from the words after the shell's name."""
    index = shell_script_index(words[i:])
    return words[i + index] if index is not None else None


class WrapperOptions(NamedTuple):
    """The options of a command that runs another command, as far as the hook reads them.

    `long` maps each long option to what it takes, as `COMMIT_LONG` does. `values` maps the short
    letters that take a value to the long name they stand for, and `flags` does the same for the
    letters that take none and matter. A letter in neither is a flag the hook does not read.
    """

    long: dict
    values: dict
    flags: dict
    lone_dash_clears_env: bool = False


ENV_OPTIONS = WrapperOptions(
    {
        "argv0": "=",
        "block-signal": "?",
        "chdir": "=",
        "debug": "",
        "default-signal": "?",
        "help": "",
        "ignore-environment": "",
        "ignore-signal": "?",
        "list-signal-handling": "",
        "null": "",
        "split-string": "=",
        "unset": "=",
        "version": "",
    },
    {"a": "argv0", "C": "chdir", "P": "path", "S": "split-string", "u": "unset"},
    {"i": "ignore-environment"},
    lone_dash_clears_env=True,
)

SUDO_OPTIONS = WrapperOptions(
    {
        "auth-type": "=",
        "chdir": "=",
        "chroot": "=",
        "close-from": "=",
        "command-timeout": "=",
        "group": "=",
        "host": "=",
        "login-class": "=",
        "other-user": "=",
        "preserve-env": "?",
        "prompt": "=",
        "role": "=",
        "type": "=",
        "user": "=",
    },
    {
        "C": "close-from",
        "c": "login-class",
        "D": "chdir",
        "g": "group",
        "h": "host",
        "p": "prompt",
        "R": "chroot",
        "r": "role",
        "T": "command-timeout",
        "t": "type",
        "U": "other-user",
        "u": "user",
    },
    {},
)


def wrapper_options(
    options: WrapperOptions, words: list[str], i: int
) -> tuple[list[tuple[str, str | None]], int]:
    """Read the options after `env` or `sudo`. Return (option, value) pairs and the next index.

    The options end at the first word that is not one, which is an assignment or the command. A
    long option may be abbreviated, as getopt allows.
    """
    events: list[tuple[str, str | None]] = []

    while i < len(words):
        word = words[i]
        if word == "-" and options.lone_dash_clears_env:
            events.append(("ignore-environment", None))
            i += 1
            continue
        if not word.startswith("-") or word == "-":
            break

        i += 1
        if word == "--":
            break

        if word.startswith("--"):
            name, has_value, value = word[2:].partition("=")
            found = resolve_option(name, options.long, negatable=False)
            if found is None:
                continue

            option = found[0]
            if has_value:
                given = value
            elif options.long[option] == "=":
                given = words[i] if i < len(words) else None
                i += 1
            else:
                given = None
            events.append((option, given))
            continue

        letters = word[1:]
        for j, letter in enumerate(letters, 1):
            if letter in options.values:
                rest = letters[j:]
                if rest:
                    events.append((options.values[letter], rest))
                else:
                    events.append((options.values[letter], words[i] if i < len(words) else None))
                    i += 1
                break
            if letter in options.flags:
                events.append((options.flags[letter], None))

    return events, i


def commits_in_command(words: list[str], here: Place, env: dict, depth: int) -> list[Commit]:
    found: list[Commit] = []
    env = dict(env)
    place = here
    at_command = True
    i = 0

    while i < len(words):
        word = words[i]
        name = os.path.basename(word)
        i += 1

        assignment = ASSIGNMENT.match(word)
        if assignment:
            if assignment.group(1) in REDIRECTING:
                env[assignment.group(1)] = assignment.group(2)
            continue

        expands = at_command and EXPANDS_TO_COMMAND.search(word) and "commit" in words[i:]
        at_command = name in WRAPPERS or (at_command and word.startswith("-"))

        if name == "git":
            commit, i = git_invocation(words, i, place, env)
            if commit:
                found.append(commit)
        elif name in SHELLS and depth < MAX_DEPTH:
            script = shell_script(words, i)
            if script is not None:
                found += commits_in(script, place, depth + 1, env)
        elif name == "eval" and depth < MAX_DEPTH:
            found += commits_in(" ".join(words[i:]), place, depth + 1, env)
        elif name in ("env", "sudo"):
            events, i = wrapper_options(ENV_OPTIONS if name == "env" else SUDO_OPTIONS, words, i)
            for option, value in events:
                if option == "chdir" and value is not None:
                    place = moved(place, value, f"{name} --chdir=")
                elif option == "unset" and value is not None:
                    env = {k: v for k, v in env.items() if k != value}
                elif option == "ignore-environment":
                    env = {}
                elif option == "split-string" and value is not None and depth < MAX_DEPTH:
                    found += commits_in(value, place, depth + 1, env)
        elif expands:
            found.append(Commit(None, (), False, why=f"`{word}` may expand to git"))
            break

    return found


class Scope(NamedTuple):
    """What a subshell or a command substitution saves, so its end can restore it."""

    kind: str
    here: Place
    env: dict
    words: list[str]
    glued: bool
    after: Place | None


def exported(env: dict, args: list[str]) -> dict:
    """Return env after `export args`."""
    out = dict(env)
    for arg in args:
        assignment = ASSIGNMENT.match(arg)
        if assignment and assignment.group(1) in REDIRECTING:
            out[assignment.group(1)] = assignment.group(2)
    return out


def nearest_existing(path: str) -> str:
    """Return the closest directory at or above `path` that exists."""
    while not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def commits_in(script: str, start: Place, depth: int = 0, env: dict | None = None) -> list[Commit]:
    """Find each `git commit` in a shell script, with the directory it runs in.

    A `cd` carries to the commands after it. A `cd` in a subshell, a command substitution, or a
    pipeline does not. A `cd` that cannot be followed leaves the directory unknown until an absolute
    `cd` sets it again.

    A `cd` to a directory that does not exist may be followed by a command that makes it, as in
    `mkdir x && cd x`. When an `&&` follows, the commands up to the end of that chain run in the
    nearest directory that exists, so the commit is checked against that repo. After the chain
    they may run there or here, and so does a command after a `||` or a `;`. Those are unknown.
    GIT_DIR and GIT_WORK_TREE follow the same scopes as `cd`.
    """
    found: list[Commit] = []
    here = start
    env = dict(env or {})
    scopes: list[Scope] = []
    words: list[str] = []
    last: list[str] = []
    after: Place | None = None

    def run(op: str) -> None:
        nonlocal here, env, words, last, after
        command, words, last = words, [], []
        inline = dict(env)
        while command and (command[0] in OPENERS or ASSIGNMENT.match(command[0])):
            assignment = ASSIGNMENT.match(command[0])
            if assignment and assignment.group(1) in REDIRECTING:
                inline[assignment.group(1)] = assignment.group(2)
            command = command[1:]

        persists = op not in ("|", "&")
        name = os.path.basename(command[0]) if command else ""

        if not command:
            if persists:
                env = inline
        elif name in ("cd", "pushd"):
            if persists:
                operand = cd_operand(command[1:])
                if name == "pushd" and operand is None:
                    here = Place(None, "`pushd` with no operand swaps in a directory it cannot know")
                else:
                    here = moved(here, operand, f"{name} ")

                if here.directory is not None and not os.path.isdir(here.directory):
                    lost = Place(None, f"`{name} {operand}` names a directory that does not exist")
                    if op == "&&":
                        here = Place(nearest_existing(here.directory))
                        after = after or lost
                    else:
                        here = lost
        elif name == "popd":
            if persists:
                here = Place(None, "`popd` returns to a directory it cannot know")
        elif name == "export":
            if persists:
                env = exported(env, command[1:])
        elif name == "unset":
            if persists:
                env = {k: v for k, v in env.items() if k not in command[1:]}
        else:
            found.extend(commits_in_command(command, here, inline, depth))
            last = command

        if after is not None and op not in ("&&", "("):
            here, after = after, None

    for token in tokenize(script):
        if token.kind == "word":
            words.append(token.text)
        elif token.kind == "body":
            if depth < MAX_DEPTH and any(os.path.basename(w) in SHELLS for w in last):
                found += commits_in(token.text, here, depth + 1, env)
        elif token.text == "$(" or (token.text == "`" and not (scopes and scopes[-1].kind == "`")):
            scopes.append(Scope(token.text, here, env, words, token.glued, after))
            words = []
        elif token.text == "`" or (token.text == ")" and scopes and scopes[-1].kind != "`"):
            run(token.text)
            scope = scopes.pop()
            here, env, after = scope.here, scope.env, scope.after
            if scope.kind == "(":
                words = []
            elif scope.glued and scope.words:
                words = [*scope.words[:-1], scope.words[-1] + "$(...)"]
            else:
                words = [*scope.words, "$(...)"]
        else:
            run(token.text)
            if token.text == "(":
                scopes.append(Scope("(", here, env, [], False, after))

    run("\n")
    return found


def commit_scopes(command: str, cwd: str) -> list[Commit]:
    """Return each `git commit` in a command that starts in cwd."""
    found = commits_in(command, Place(cwd))

    # A commit the parser cannot place, such as one inside a string passed to another program, is
    # still checked against the repo the command starts in.
    if not found and GIT_COMMIT.search(command):
        return [Commit(cwd, (), False)]
    return found


def head_ref(target: Target) -> str:
    """Return what a commit is compared with. A repo with no commit yet has the empty tree.

    `git diff HEAD` fails there, and the hook then read nothing, though `-a` takes the working tree
    of every file the index knows.
    """
    if git(target, "rev-parse", "--verify", "--quiet", "HEAD") is not None:
        return "HEAD"

    algorithm = (git(target, "rev-parse", "--show-object-format") or "sha1").strip()
    return EMPTY_TREES.get(algorithm, EMPTY_TREES["sha1"])


def name_hits(name: str, pattern: re.Pattern) -> list[str]:
    """Find terms in a path. An added path is never an added line, so a diff's lines miss it."""
    seen: list[str] = []
    for term in pattern.findall(name):
        if term.lower() not in (s.lower() for s in seen):
            seen.append(term)
    return [f"{term} (file name {name})" for term in seen]


def untracked_hits(target: Target, pattern: re.Pattern, top: str) -> list[str]:
    """Find terms in the name and text of each untracked file that the ignore rules leave in view.

    A symlink is read as the text of its target, which is what git would store. Anything that is
    not a file or a symlink is skipped. A file too large to read is denied, since the hook cannot
    tell what it holds.
    """
    listing = git(target, "ls-files", "--others", "--exclude-standard", "--full-name", "-z")
    if listing is None:
        raise CannotReadSafely("Git could not list the untracked files, which this commit may add.")

    hits: list[str] = []
    for name in filter(None, listing.split("\0")):
        hits += name_hits(name, pattern)

        path = os.path.join(top, name)
        try:
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                text = os.readlink(path)
            elif not stat.S_ISREG(info.st_mode):
                continue
            elif info.st_size > MAX_UNTRACKED_FILE:
                raise CannotReadSafely(
                    f"The untracked file `{name}` is larger than {MAX_UNTRACKED_FILE >> 20} MiB, and this "
                    "commit may add it. Name the files to commit on the command line."
                )
            else:
                text = Path(path).read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            raise CannotReadSafely(f"The untracked file `{name}` could not be read: {exc.strerror}.") from exc

        for number, line in enumerate(text.splitlines(), 1):
            for term in pattern.findall(line):
                hit = f"{term} ({name}:{number})"
                if hit not in hits:
                    hits.append(hit)
    return hits


def diff_hits(
    target: Target,
    pattern: re.Pattern,
    paths: Sequence[str],
    commit_all: bool,
    widen: str = "",
    top: str = "",
) -> list[str]:
    """Find terms in the lines a commit adds, and in the paths it changes.

    Git runs in the target's directory, which a pathspec is relative to. It need not be the top.
    A path counts on both sides of a rename, and when it is deleted. A commit that may take any
    working-tree change reads the whole working-tree diff and ignores the pathspecs. One that may
    take any file reads the untracked files too.
    """
    views = [(["--cached"], [])]
    if widen or paths or commit_all:
        # A commit by path or with -a takes the working tree, not the index.
        views.append(([head_ref(target)], [] if widen else list(paths)))

    hits: list[str] = []

    def add(found: list[str]) -> None:
        hits.extend(hit for hit in found if hit not in hits)

    for revs, scope in views:
        patch = git(target, "diff", *DIFF_FLAGS, *revs, "--", *scope) or ""
        add([f"{term} ({path}:{line})" for path, line, text in added_lines(patch) for term in pattern.findall(text)])

        names = git(target, "diff", "--name-only", "-z", "--no-renames", "--ignore-submodules=all", *revs, "--", *scope)
        for name in filter(None, (names or "").split("\0")):
            add(name_hits(name, pattern))

    if widen == "everything":
        add(untracked_hits(target, pattern, top or target.directory))
    return hits


def text_hits(text: str, pattern: re.Pattern, where: str) -> list[str]:
    seen = []
    for term in pattern.findall(text):
        if term.lower() not in (s.lower() for s in seen):
            seen.append(term)
    return [f"{t} ({where})" for t in seen]


def reason(repo: str, level: str | None, hits: list[str]) -> str:
    audience = "a public repo" if level == "public" else "a repo whose visibility is unknown"
    lines = [
        f"This commit goes to {audience} and contains private terms: {', '.join(hits)}.",
        "Generalize or remove them, then commit again. See rules/disclosure.md.",
    ]
    if level is None:
        lines.append(
            "If the repo is private, the user declares it once by running: "
            f"git -C {shlex.quote(repo)} config codingstandards.visibility private"
        )
    return " ".join(lines)


def unplaced_reason(why: str) -> str:
    return " ".join(
        [
            f"The hook cannot tell which repo this commit goes to, because {why}.",
            "It denies a commit whose target it cannot see.",
            "Rerun the command as `git -C <path> commit ...`, with the repo's literal path, so the",
            "guard can see the target. See rules/disclosure.md.",
        ]
    )


def unsafe_reason(why: str) -> str:
    return " ".join(
        [
            "The hook cannot read this commit's changes safely, so it denies the commit.",
            f"{why} See rules/disclosure.md.",
        ]
    )


def index_reason(operand: str) -> str:
    return " ".join(
        [
            f"This commit uses the index `GIT_INDEX_FILE={operand}`, and the hook cannot read that index.",
            "The value must be a literal path to an index file that exists when the command is checked.",
            "Write the index in an earlier command, or commit from the repo's own index.",
            "See rules/disclosure.md.",
        ]
    )


def message_file_reason(operand: str) -> str:
    return " ".join(
        [
            f"This commit reads a message file, `{operand}`, and the hook cannot read it.",
            "The operand must be a literal path to a regular file that exists when the command is checked.",
            "Write the message in an earlier command, or give it to `-F -` on standard input.",
            "See rules/disclosure.md.",
        ]
    )


def unreadable_reason(exc: Exception) -> str:
    return " ".join(
        [
            f"The hook could not read this call ({type(exc).__name__}: {exc}), and the call mentions a commit.",
            "It cannot check what the commit carries, so it denies the call.",
            "Send the command in the form its tool expects, as `git -C <path> commit ...` with the repo's",
            "literal path. See rules/disclosure.md.",
        ]
    )


def pathspec_reason() -> str:
    return " ".join(
        [
            "This commit takes its paths from `--pathspec-from-file`, and the hook cannot read",
            "that file as plain paths.",
            "The file must be a literal path to a file inside the repo, and it must exist when the",
            "command is checked. It holds one unquoted path per line, or NUL-separated paths with",
            "`--pathspec-file-nul`.",
            "Name the paths on the command line, or write the list in an earlier command.",
            "See rules/disclosure.md.",
        ]
    )


def read_pathspec_file(commit: Commit, top: str) -> list[str] | None:
    """Return the pathspecs in the commit's `--pathspec-from-file`, or None when unreadable.

    The hook reads the file only when its operand is a literal path to a regular file inside the
    repo. Stdin, an expansion, a missing file, a file elsewhere, and a quoted entry are None.
    """
    operand = commit.pathspec_file
    if not operand:
        return None

    place = moved(Place(commit.directory), operand, "--pathspec-from-file=")
    if place.directory is None:
        return None

    try:
        path, root = os.path.realpath(place.directory), os.path.realpath(top)
        if os.path.commonpath([path, root]) != root:
            return None

        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PATHSPEC_FILE:
            return None
        text = Path(path).read_bytes().decode()
    except (OSError, ValueError):
        return None

    entries = text.split("\0") if commit.pathspec_nul else re.split(r"\r?\n", text)
    entries = [e for e in entries if e]
    if not commit.pathspec_nul and any(e.startswith('"') for e in entries):
        return None
    return entries


def read_message_file(commit: Commit, operand: str, what: str) -> str | None:
    """Return the text of a message or template file, or None when the hook cannot read it.

    The file may be anywhere. Its operand must be a literal path to a regular file, read from the
    directory git runs in. A message on standard input reads no file, and its text is already in
    the command.
    """
    if operand in STDIN_OPERANDS:
        return ""

    place = moved(Place(commit.directory), operand, what)
    if place.directory is None:
        return None

    try:
        info = os.stat(place.directory)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MESSAGE_FILE:
            return None
        return Path(place.directory).read_bytes().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return None


def index_path(operand: str, top: str) -> str | None:
    """Return the absolute path of the index a commit uses, or None when the hook cannot read it.

    Git moves to the top of the work tree before it opens the index, so a relative path is read
    from there.
    """
    place = moved(Place(top), operand, "GIT_INDEX_FILE=")
    if place.directory is None:
        return None

    try:
        if not stat.S_ISREG(os.stat(place.directory).st_mode):
            return None
    except (OSError, ValueError):
        return None
    return place.directory


def checked(target: Target) -> tuple[bool, str | None]:
    level = visibility(target)
    return level in ("public", None), level


def scan_commit(commit: Commit, command: str, pattern: re.Pattern) -> str | None:
    """Return a deny reason when this commit carries a private term, else None."""
    if commit.directory is None:
        return unplaced_reason(commit.why)

    target = Target(commit.directory, commit.git_dir, commit.work_tree)
    top = git(target, "rev-parse", "--show-toplevel")
    if top is None:
        return None
    repo = top.strip()

    check, level = checked(target)
    if not check:
        return None

    if commit.index_file:
        index = index_path(commit.index_file, repo)
        if index is None:
            return index_reason(commit.index_file)
        target = target._replace(index_file=index)

    paths: list[str] = []
    if not commit.widen:
        paths = list(commit.paths)
        if commit.pathspec_file is not None:
            listed = read_pathspec_file(commit, repo)
            if listed is None:
                return pathspec_reason()
            paths += listed

    hits = text_hits(command, pattern, "commit command")
    for operand in commit.message_files:
        text = read_message_file(commit, operand, "the message file ")
        if text is None:
            return message_file_reason(operand)
        hits += text_hits(text, pattern, f"message file {operand}")

    hits += diff_hits(target, pattern, paths, commit.commit_all, commit.widen, repo)
    return reason(repo, level, hits) if hits else None


def deny(denial: str) -> None:
    decision = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": denial,
    }
    print(json.dumps({"hookSpecificOutput": decision}))


def pretooluse(payload: object) -> int:
    commits = {}
    for command, cwd in tool_commands(payload):
        for commit in commit_scopes(command, cwd):
            commits[(command, commit)] = None
    if not commits:
        return 0

    terms = load_terms()
    if not terms:
        return 0

    pattern = matcher(terms)
    for command, commit in commits:
        try:
            denial = scan_commit(commit, command, pattern)
        except CannotReadSafely as exc:
            denial = unsafe_reason(str(exc))

        if denial:
            deny(denial)
            return 0
    return 0


def run_pretooluse() -> int:
    """Run the PreToolUse hook. An error never escapes, since an exit of 1 does not block the call.

    A call the hook cannot read is denied when its text may spell a commit and the user keeps terms.
    The text is the raw payload, and the decoded one when it decoded, since either may hide the word.
    """
    raw = ""
    payload: object = None
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        return pretooluse(payload)
    except Exception as exc:
        text = raw + json.dumps(payload, ensure_ascii=False, default=str)
        if mentions(text, "commit") and load_terms():
            deny(unreadable_reason(exc))
        return 0


def git_hook(mode: str, args: list[str]) -> int:
    terms = load_terms()
    if not terms:
        return 0

    try:
        top = git(Target(os.getcwd()), "rev-parse", "--show-toplevel")
        if top is None:
            return 0
        target = Target(top.strip())

        check, level = checked(target)
        if not check:
            return 0

        pattern = matcher(terms)
        if mode == "pre-commit":
            hits = diff_hits(target, pattern, [], False, top=target.directory)
        else:
            message = "\n".join(l for l in Path(args[0]).read_text().splitlines() if not l.startswith("#"))
            hits = text_hits(message, pattern, "commit message")
    except CannotReadSafely as exc:
        print(unsafe_reason(str(exc)), file=sys.stderr)
        return 1

    if hits:
        print(reason(target.directory, level, hits), file=sys.stderr)
        print("A false positive can be committed with --no-verify.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "pretooluse":
        return run_pretooluse()
    if mode == "pre-commit" or (mode == "commit-msg" and len(sys.argv) == 3):
        return git_hook(mode, sys.argv[2:])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
