#!/usr/bin/env python3
"""Deny an `rm` with both a recursive and a force flag. `block-rm-rf.sh` runs this on PreToolUse.

This is a heuristic scanner for accidents, not a shell parser and not a sandbox. It follows quotes,
escapes, comments, heredocs, and substitutions, and it unwraps `sh -c`, `eval`, and subshells. It
does not expand variables or aliases, and it does not follow `ssh`, `su -c`, or another language's
`-c`. An `rm` word anywhere in a command counts, so `sudo rm` and `xargs rm` are caught, and
`echo rm -rf x` is denied too.

A word's quoting decides whether it is code or text. `grep 'rm -rf' .` holds one word, not an `rm`.
A heredoc body is text unless the command feeding it runs a shell.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

SHELLS = {"ash", "bash", "dash", "fish", "ksh", "sh", "zsh"}
MAX_DEPTH = 8


@dataclass
class Word:
    text: str
    quoted: bool = False
    redirect: bool = False


@dataclass
class Heredoc:
    delimiter: str
    strip_tabs: bool
    command: list[Word] = field(default_factory=list)


def base(word: Word) -> str:
    return word.text.rsplit("/", 1)[-1]


def is_unquoted_or_first(word: Word, index: int) -> bool:
    """A quoted word runs only in command position. `'rm' -rf x` deletes, but `grep 'rm' -rf x` searches."""
    return not word.quoted or index == 0


def runs_shell(command: list[Word]) -> bool:
    return any(base(w) in SHELLS and is_unquoted_or_first(w, i) for i, w in enumerate(command))


def embedded_scripts(command: list[Word]) -> list[str]:
    """Return the source text a command hands to a shell: `sh -c` strings and `eval` arguments."""
    scripts = []

    for index, word in enumerate(command):
        if not is_unquoted_or_first(word, index):
            continue

        if word.text == "eval":
            scripts.append(" ".join(w.text for w in command[index + 1 :] if not w.redirect))
        elif base(word) in SHELLS:
            script = shell_c_argument(command[index + 1 :])
            if script is not None:
                scripts.append(script)

    return scripts


def shell_c_argument(args: list[Word]) -> str | None:
    position = 0

    while position < len(args) and args[position].text.startswith("-"):
        flag = args[position].text

        if not flag.startswith("--"):
            if "c" in flag:
                return args[position + 1].text if position + 1 < len(args) else None
            if flag.endswith("o"):
                position += 1

        position += 1

    return None


class Scanner:
    def __init__(self, source: str, commands: list[list[Word]], depth: int = 0) -> None:
        self.source = source
        self.commands = commands
        self.depth = depth
        self.pos = 0

    def scan_text(self, text: str) -> None:
        if self.depth < MAX_DEPTH:
            Scanner(text, self.commands, self.depth + 1).parse()

    def parse(self, closer: str | None = None) -> None:
        source = self.source
        command: list[Word] = []
        chars: list[str] | None = None
        quoted = False
        redirect = False
        heredocs: list[Heredoc] = []

        def end_word() -> None:
            nonlocal chars, quoted, redirect
            if chars is not None:
                command.append(Word("".join(chars), quoted, redirect))
                redirect = False
            chars = None
            quoted = False

        def end_command() -> None:
            nonlocal command
            end_word()
            if command:
                self.commands.append(command)
                for script in embedded_scripts(command):
                    self.scan_text(script)
            command = []

        while self.pos < len(source):
            char = source[self.pos]

            if char == closer:
                self.pos += 1
                break

            if char == "\n":
                end_command()
                self.pos += 1
                self.read_heredocs(heredocs)
                heredocs = []
            elif char in " \t":
                end_word()
                self.pos += 1
            elif char in ";&|)":
                end_command()
                self.pos += 1
            elif char == "(":
                end_command()
                self.pos += 1
                self.parse(")")
            elif char in "<>":
                if source.startswith("<<<", self.pos):
                    end_word()
                    self.pos += 3
                    redirect = True
                    self.read_here_string(command)
                    redirect = False
                elif source.startswith("<<", self.pos):
                    end_word()
                    self.pos += 2
                    heredocs.append(self.read_heredoc_delimiter(command))
                elif source.startswith(("<(", ">("), self.pos):
                    end_word()
                    self.pos += 1
                else:
                    if chars is not None and "".join(chars).isdigit():
                        chars = None
                    end_word()
                    while self.pos < len(source) and source[self.pos] in "<>":
                        self.pos += 1
                    redirect = True
            elif char == "#" and chars is None:
                end = source.find("\n", self.pos)
                self.pos = len(source) if end == -1 else end
            else:
                if chars is None:
                    chars = []

                text, was_quoted = self.read_word_part(char)
                chars.append(text)
                quoted = quoted or was_quoted

        end_command()

        if heredocs:
            self.read_heredocs(heredocs)

    def read_word_part(self, char: str) -> tuple[str, bool]:
        source = self.source

        if char == "\\":
            if source.startswith("\\\n", self.pos):
                self.pos += 2
                return "", False
            text = source[self.pos + 1 : self.pos + 2]
            self.pos += 2
            return text, False

        if char == "'":
            end = source.find("'", self.pos + 1)
            if end == -1:
                self.pos += 1
                return "'", False
            text = source[self.pos + 1 : end]
            self.pos = end + 1
            return text, True

        if char == '"':
            return self.read_double_quoted(), True

        if char == "`":
            return self.read_backticks(), False

        if source.startswith("$(", self.pos):
            return self.read_substitution(), False

        self.pos += 1
        return char, False

    def read_double_quoted(self) -> str:
        source = self.source
        parts: list[str] = []
        self.pos += 1

        while self.pos < len(source):
            char = source[self.pos]

            if char == '"':
                self.pos += 1
                break

            if char == "\\" and self.pos + 1 < len(source):
                next_char = source[self.pos + 1]
                parts.append(next_char if next_char in '$`"\\\n' else char + next_char)
                self.pos += 2
            elif char == "`":
                parts.append(self.read_backticks())
            elif source.startswith("$(", self.pos):
                parts.append(self.read_substitution())
            else:
                parts.append(char)
                self.pos += 1

        return "".join(parts)

    def read_substitution(self) -> str:
        start = self.pos
        self.pos += 2
        self.parse(")")
        return self.source[start : self.pos]

    def read_backticks(self) -> str:
        source = self.source
        end = self.pos + 1

        while end < len(source) and source[end] != "`":
            end += 2 if source[end] == "\\" else 1

        if end >= len(source):
            self.pos += 1
            return "`"

        inner = source[self.pos + 1 : end]
        text = source[self.pos : end + 1]
        self.pos = end + 1
        self.scan_text(inner.replace("\\`", "`"))
        return text

    def skip_blanks(self) -> None:
        while self.pos < len(self.source) and self.source[self.pos] in " \t":
            self.pos += 1

    def read_bare_word(self) -> str:
        """Read one word after a heredoc or here-string operator, removing its quotes."""
        parts: list[str] = []

        while self.pos < len(self.source) and self.source[self.pos] not in " \t\n;&|()<>":
            parts.append(self.read_word_part(self.source[self.pos])[0])

        return "".join(parts)

    def read_here_string(self, command: list[Word]) -> None:
        self.skip_blanks()
        text = self.read_bare_word()

        if runs_shell(command):
            self.scan_text(text)

    def read_heredoc_delimiter(self, command: list[Word]) -> Heredoc:
        strip_tabs = self.source.startswith("-", self.pos)
        if strip_tabs:
            self.pos += 1

        self.skip_blanks()
        return Heredoc(self.read_bare_word(), strip_tabs, command)

    def read_heredocs(self, heredocs: list[Heredoc]) -> None:
        for heredoc in heredocs:
            body: list[str] = []

            while self.pos < len(self.source):
                end = self.source.find("\n", self.pos)
                line = self.source[self.pos :] if end == -1 else self.source[self.pos : end]
                self.pos = len(self.source) if end == -1 else end + 1

                if (line.lstrip("\t") if heredoc.strip_tabs else line) == heredoc.delimiter:
                    break

                body.append(line)

            if runs_shell(heredoc.command):
                self.scan_text("\n".join(body))


def recursive_force_operands(command: list[Word]) -> list[str] | None:
    """Return the operands of an `rm` with both flags in this command, or None when there is none."""
    in_rm = end_options = recursive = force = False
    operands: list[str] = []

    for index, word in enumerate(command):
        if not in_rm:
            in_rm = base(word) == "rm" and is_unquoted_or_first(word, index)
            continue

        if word.redirect:
            continue

        text = word.text

        if not end_options:
            if text == "--":
                end_options = True
                continue
            if text.startswith("-") and len(text) > 1:
                if text.startswith("--"):
                    recursive = recursive or text == "--recursive"
                    force = force or text == "--force"
                else:
                    recursive = recursive or "r" in text or "R" in text
                    force = force or "f" in text
                continue

        if text:
            operands.append(text)

    return operands if recursive and force else None


def advise(operand: str, cwd: str) -> str:
    if any(char in operand for char in "*?[$`"):
        return f" {operand} is a pattern or variable. Expand it yourself and handle each match."

    path = operand
    if path == "~" or path.startswith("~/"):
        path = os.environ.get("HOME", "~") + path[1:]
    elif not path.startswith("/") and cwd:
        path = os.path.join(cwd, path)

    if os.path.islink(path):
        return f" {operand} is a symlink. Use unlink {operand}."
    if os.path.isfile(path):
        return f" {operand} is a file. Use unlink {operand}."
    if not os.path.isdir(path):
        return f" {operand} does not exist."

    try:
        entries = len(os.listdir(path))
    except OSError:
        return f" {operand} is a directory that cannot be read. Ask the user to delete it."

    if entries == 0:
        return f" {operand} is an empty directory. Use rmdir {operand}."
    return f" {operand} is a directory with {entries} entries. Empty it with unlink and rmdir first, or ask the user to delete it."


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    commands: list[list[Word]] = []
    Scanner(payload.get("tool_input", {}).get("command") or "", commands).parse()

    for command in commands:
        operands = recursive_force_operands(command)

        if operands is not None:
            reason = "Blocked: rm with both recursive and force flags is disabled by your safety hook."
            reason += " Delete only what you mean to. Use unlink for one file and rmdir for one empty directory."
            reason += "".join(advise(op, payload.get("cwd") or "") for op in operands)

            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }))
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
