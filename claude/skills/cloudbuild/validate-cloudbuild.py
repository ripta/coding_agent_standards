#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Validate and lint a Google Cloud Build config.

Three layers, worst first:

  1. Well-formedness. The file parses, and every key and value has a shape
     Cloud Build accepts.
  2. Correctness. Substitution escaping, step wiring, secrets, timeouts. These
     are the things that submit cleanly and then fail, or worse, silently do
     the wrong thing.
  3. House rules from SKILL.md. Private pools, machine types, the timeout
     ceiling, inline scripts, template scaffolding left in place.

Run it through uv, which installs PyYAML itself, or through any python3 that
already has PyYAML:

    ./validate-cloudbuild.py cloudbuild.yaml
    uv run --script validate-cloudbuild.py cloudbuild.yaml
    python3 validate-cloudbuild.py cloudbuild.yaml

With no path it checks every cloudbuild*.yaml in the current directory.

Exit status: 0 when nothing failing is found, 1 when a finding fails the run,
2 for a usage or I/O problem.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - depends on the host env
    sys.exit(
        "validate-cloudbuild.py needs PyYAML.\n"
        "Run it as: uv run --script validate-cloudbuild.py <file>"
    )

# --- Check registry ---------------------------------------------------------
#
# Every finding carries a code, and the code decides its level. Keeping the
# levels in one table is what makes --list-checks and --ignore cheap.

ERROR, WARN, NOTE = "error", "warn", "note"

CHECKS: dict[str, tuple[str, str]] = {
    # Parse and schema
    "CB001": (ERROR, "file does not parse as YAML"),
    "CB002": (ERROR, "config is not a YAML mapping"),
    "CB003": (ERROR, "unknown top-level field"),
    "CB004": (ERROR, "steps is missing or empty"),
    "CB005": (ERROR, "malformed build step"),
    "CB006": (ERROR, "unknown build step field"),
    "CB007": (ERROR, "duplicate mapping key"),
    "CB008": (ERROR, "duplicate step id"),
    "CB009": (ERROR, "waitFor names a step that is not defined above it"),
    "CB010": (ERROR, "timeout is not a duration like 600s"),
    "CB011": (ERROR, "step timeout exceeds the build timeout"),
    "CB012": (ERROR, "user substitution key must match _[A-Z0-9_]+"),
    "CB013": (ERROR, "script cannot be combined with args or entrypoint"),
    "CB014": (WARN, "unknown options field"),
    # Substitutions and secrets
    "CB015": (ERROR, "single $ on something Cloud Build will not substitute"),
    "CB016": (WARN, "$$ on a substitution the shell cannot resolve"),
    "CB017": (WARN, "substitution used inside script, which never expands it"),
    "CB018": (ERROR, "$$ inside script, where the shell reads it as its PID"),
    "CB019": (WARN, "declared substitution is never used"),
    "CB020": (WARN, "substitution references another without dynamicSubstitutions"),
    "CB021": (ERROR, "secretEnv is not declared in availableSecrets"),
    "CB022": (WARN, "declared secret is never used"),
    "CB023": (WARN, "serviceAccount set without options.logging"),
    # House rules
    "CB030": (ERROR, "options.pool opts into a private pool"),
    "CB031": (ERROR, "options.machineType leaves the free-tier default pool"),
    "CB032": (ERROR, "timeout is absent"),
    "CB033": (ERROR, "timeout is above the 2700s ceiling"),
    "CB034": (WARN, "Alpine base image"),
    "CB035": (WARN, "hardcoded project id where $PROJECT_ID belongs"),
    "CB036": (ERROR, "buildx use names a different builder than buildx create"),
    "CB037": (WARN, "multi-line shell step without set -e"),
    "CB038": (WARN, "buildx --push and images both push the image"),
    "CB039": (NOTE, "base image has no tag"),
    "CB040": (NOTE, "long inline script belongs in a Makefile"),
    "CB041": (NOTE, "no header comment naming the triggers"),
    "CB042": (NOTE, "header comment is longer than the config it heads"),
    "CB043": (ERROR, "template scaffolding was shipped verbatim"),
}

LEVEL_RANK = {NOTE: 0, WARN: 1, ERROR: 2}

# --- Cloud Build vocabulary -------------------------------------------------

TOP_LEVEL_FIELDS = {
    "steps",
    "timeout",
    "queueTtl",
    "logsBucket",
    "options",
    "substitutions",
    "tags",
    "serviceAccount",
    "secrets",
    "availableSecrets",
    "artifacts",
    "images",
}

STEP_FIELDS = {
    "name",
    "args",
    "env",
    "allowFailure",
    "allowExitCodes",
    "dir",
    "id",
    "waitFor",
    "entrypoint",
    "secretEnv",
    "volumes",
    "timeout",
    "script",
    "automapSubstitutions",
    "results",
}

OPTIONS_FIELDS = {
    "automapSubstitutions",
    "defaultLogsBucketBehavior",
    "diskSizeGb",
    "dynamicSubstitutions",
    "env",
    "logStreamingOption",
    "logging",
    "machineType",
    "pool",
    "requestedVerifyOption",
    "secretEnv",
    "sourceProvenanceHash",
    "substitutionOption",
    "volumes",
    "workerPool",
}

# Available to every build.
GLOBAL_SUBS = {"PROJECT_ID", "PROJECT_NUMBER", "BUILD_ID", "LOCATION"}

# Set only by triggers. They expand to the empty string elsewhere, which is
# what makes `if [[ -n "$TAG_NAME" ]]` work as a build-type guard.
TRIGGER_SUBS = {
    "TRIGGER_NAME",
    "TRIGGER_BUILD_CONFIG_PATH",
    "COMMIT_SHA",
    "REVISION_ID",
    "SHORT_SHA",
    "REPO_NAME",
    "REPO_FULL_NAME",
    "BRANCH_NAME",
    "TAG_NAME",
    "REF_NAME",
    "SERVICE_ACCOUNT",
    "SERVICE_ACCOUNT_EMAIL",
}

# GitHub pull request triggers only. Underscored, but built in.
PR_SUBS = {"_HEAD_BRANCH", "_BASE_BRANCH", "_HEAD_REPO_URL", "_PR_NUMBER"}

BUILTIN_SUBS = GLOBAL_SUBS | TRIGGER_SUBS | PR_SUBS

SHELLS = {"bash", "sh", "ash", "dash", "zsh"}

# Registry paths that belong to Google or the community, not to a project.
SHARED_REGISTRY_OWNERS = {
    "cloud-builders",
    "cloud-marketplace",
    "distroless",
    "buildpacks",
    "google.com",
    "google-containers",
    "google-appengine",
    "k8s-artifacts-prod",
    "kaniko-project",
    "skaffold",
}

DURATION_RE = re.compile(r"^\d+(\.\d{1,9})?s$")
SUB_KEY_RE = re.compile(r"^_[A-Z0-9_]+$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DOLLAR_RE = re.compile(r"(\$+)(?:\{([^{}]*)\}|([A-Za-z_][A-Za-z0-9_]*))?")
SET_E_RE = re.compile(r"^\s*set\s+[-+]\S*e|^\s*set\s+-o\s+errexit", re.MULTILINE)
BUILDX_CREATE_RE = re.compile(r"buildx\s+create\b[^\n]*?--name[= ]+(\S+)")
BUILDX_USE_RE = re.compile(r"buildx\s+use\s+(\S+)")
BUILDX_PUSH_RE = re.compile(r"buildx\s+build\b[\s\S]*?--push\b")
IMAGE_REF_RE = re.compile(r"\b((?:[a-z0-9-]+\.)?(?:gcr\.io|pkg\.dev))/([^/\s'\"]+)/")
SCAFFOLDING_RE = re.compile(r"cut here|NOTES\. Not part of the config|Replace: ")

MAX_TIMEOUT_SECONDS = 2700
LONG_SCRIPT_LINES = 25

# --- Position-aware YAML loading --------------------------------------------


class Mapping(dict):
    """A dict that remembers where it and each of its keys came from."""

    def __init__(self) -> None:
        super().__init__()
        self.line = 0
        self.key_lines: dict[str, int] = {}

    def line_of(self, key: str) -> int:
        """Return the source line of a key, falling back to the mapping's own."""
        return self.key_lines.get(key, self.line)


class Sequence(list):
    """A list that remembers where it came from."""

    def __init__(self, items=()) -> None:
        super().__init__(items)
        self.line = 0


class Scalar(str):
    """A str that remembers its source line and YAML style."""

    def __new__(cls, value: str, line: int = 0, style: str | None = None):
        scalar = super().__new__(cls, value)
        scalar.line = line
        scalar.style = style
        return scalar

    def line_at(self, offset: int) -> int:
        """Return the source line of a character offset inside this scalar."""
        # A block scalar's start mark sits on the `|`, so its body starts one
        # line later. Every other style starts on the mark itself.
        base = self.line + 1 if self.style in ("|", ">") else self.line
        return base + self[:offset].count("\n")


class PositionLoader(yaml.SafeLoader):
    """SafeLoader that records line numbers and duplicate keys."""

    def __init__(self, stream) -> None:
        super().__init__(stream)
        self.duplicates: list[tuple[str, int]] = []


def _construct_mapping(loader: PositionLoader, node) -> Mapping:
    loader.flatten_mapping(node)
    out = Mapping()
    out.line = node.start_mark.line + 1
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        line = key_node.start_mark.line + 1
        # PyYAML lets a later duplicate win in silence. Two `steps:` keys or two
        # `timeout:` keys are a real and invisible way to lose half a config.
        if key in out:
            loader.duplicates.append((str(key), line))
        out[key] = loader.construct_object(value_node, deep=True)
        out.key_lines[str(key)] = line
    return out


def _construct_sequence(loader: PositionLoader, node) -> Sequence:
    out = Sequence(loader.construct_object(child, deep=True) for child in node.value)
    out.line = node.start_mark.line + 1
    return out


def _construct_str(loader: PositionLoader, node) -> Scalar:
    return Scalar(node.value, node.start_mark.line + 1, node.style)


PositionLoader.add_constructor("tag:yaml.org,2002:map", _construct_mapping)
PositionLoader.add_constructor("tag:yaml.org,2002:seq", _construct_sequence)
PositionLoader.add_constructor("tag:yaml.org,2002:str", _construct_str)


# --- Findings ---------------------------------------------------------------


@dataclass
class Finding:
    """One thing wrong with one config file."""

    path: str
    line: int
    code: str
    level: str
    message: str

    def format_text(self) -> str:
        return f"{self.path}:{self.line}: {self.level} [{self.code}] {self.message}"


def line_of(container, key: str, default: int = 0) -> int:
    """Return the source line of `key` in `container`, or `default`."""
    if isinstance(container, Mapping):
        return container.line_of(key) or default
    return default


def norm(key: str) -> str:
    """Fold a field name for comparison.

    Cloud Build accepts both the proto spelling and the JSON spelling, so
    wait_for and waitFor are the same field.
    """
    return key.replace("_", "").lower()


def field_get(mapping, name: str, default=None):
    """Read a field by its camelCase name, tolerating the snake_case spelling."""
    if not isinstance(mapping, dict):
        return default
    target = norm(name)
    for key, value in mapping.items():
        if norm(str(key)) == target:
            return value
    return default


def field_line(mapping, name: str, default: int = 0) -> int:
    """Return the source line of a field, by either spelling."""
    if not isinstance(mapping, Mapping):
        return default
    target = norm(name)
    for key in mapping:
        if norm(str(key)) == target:
            return mapping.line_of(str(key))
    return default


def parse_duration(value) -> float | None:
    """Return a duration in seconds, or None when the value is not one."""
    if not isinstance(value, str) or not DURATION_RE.match(value):
        return None
    return float(value[:-1])


def type_name(value) -> str:
    """Return a plain-English type name for a parsed YAML value."""
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def basename_image(image: str) -> str:
    """Return the last path segment of an image reference, tag included."""
    return image.rsplit("/", 1)[-1]


# --- The linter -------------------------------------------------------------


class Linter:
    """Collects findings for a single config file."""

    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text
        self.lines = text.splitlines()
        self.findings: list[Finding] = []
        self.doc = None
        self.declared_subs: dict[str, str] = {}
        self.used_subs: set[str] = set()
        self.declared_secrets: dict[str, int] = {}
        self.used_secrets: set[str] = set()
        self.known_subs: set[str] = set(BUILTIN_SUBS)
        self.build_automap = False
        self.build_timeout: float | None = None

    # -- reporting --

    def report(self, code: str, line: int, message: str) -> None:
        level = CHECKS[code][0]
        self.findings.append(Finding(str(self.path), max(line, 1), code, level, message))

    # -- entry point --

    def run(self) -> list[Finding]:
        if not self.load():
            return self.findings
        self.check_top_level()
        self.check_options()
        self.check_substitutions()
        self.check_secrets_block()
        self.check_timeout()
        self.check_steps()
        self.check_unused()
        self.check_comments()
        self.findings.sort(key=lambda f: (f.line, f.code))
        return self.findings

    # -- layer 1: parse --

    def load(self) -> bool:
        loader = PositionLoader(self.text)
        try:
            self.doc = loader.get_single_data()
        except yaml.YAMLError as err:
            mark = getattr(err, "problem_mark", None)
            detail = getattr(err, "problem", None) or str(err)
            self.report("CB001", mark.line + 1 if mark else 1, str(detail).strip())
            return False
        finally:
            loader.dispose()

        for key, line in loader.duplicates:
            self.report("CB007", line, f"`{key}` is set twice; the later one silently wins")

        if self.doc is None:
            self.report("CB002", 1, "file is empty")
            return False
        if not isinstance(self.doc, dict):
            self.report("CB002", 1, f"top level is a {type_name(self.doc)}, not a mapping")
            return False
        return True

    # -- layer 2: schema --

    def check_top_level(self) -> None:
        known = {norm(f) for f in TOP_LEVEL_FIELDS}
        for key in self.doc:
            if norm(str(key)) not in known:
                self.report(
                    "CB003",
                    self.doc.line_of(str(key)),
                    f"`{key}` is not a build config field; Cloud Build rejects the file",
                )

        steps = field_get(self.doc, "steps")
        if not steps:
            line = field_line(self.doc, "steps", 1)
            self.report("CB004", line, "a build needs at least one step")
        elif not isinstance(steps, list):
            self.report(
                "CB004",
                field_line(self.doc, "steps", 1),
                f"steps is a {type_name(steps)}, not a list",
            )

    def check_options(self) -> None:
        options = field_get(self.doc, "options")

        # A custom service account cannot write to the legacy default bucket,
        # so the build fails to start unless logging is redirected. Checked
        # even when the options block is missing, which is the usual way to
        # hit this.
        if field_get(self.doc, "serviceAccount") and field_get(options or {}, "logging") is None:
            self.report(
                "CB023",
                field_line(self.doc, "serviceAccount"),
                "a custom service account needs options.logging, "
                "usually CLOUD_LOGGING_ONLY, or the build fails to start",
            )

        if not isinstance(options, dict):
            return

        known = {norm(f) for f in OPTIONS_FIELDS}
        for key in options:
            if norm(str(key)) not in known:
                self.report(
                    "CB014",
                    options.line_of(str(key)),
                    f"`{key}` is not a known options field",
                )

        if field_get(options, "pool") is not None or field_get(options, "workerPool") is not None:
            self.report(
                "CB030",
                field_line(options, "pool") or field_line(options, "workerPool"),
                "the smallest private pool is ~20x the default pool and is billed for it",
            )
        if field_get(options, "machineType") is not None:
            self.report(
                "CB031",
                field_line(options, "machineType"),
                "the default pool is covered by free-tier quota; this leaves it",
            )

        self.build_automap = bool(field_get(options, "automapSubstitutions"))

    def check_substitutions(self) -> None:
        subs = field_get(self.doc, "substitutions")
        if not isinstance(subs, dict):
            return

        dynamic = bool(field_get(field_get(self.doc, "options") or {}, "dynamicSubstitutions"))
        for key, value in subs.items():
            key = str(key)
            line = subs.line_of(key)
            if not SUB_KEY_RE.match(key):
                self.report(
                    "CB012",
                    line,
                    f"`{key}` must start with an underscore and use A-Z, 0-9, and _ only",
                )
            self.declared_subs[key] = line
            self.known_subs.add(key)
            # A value that names another substitution only resolves when
            # dynamicSubstitutions is on. Triggers turn it on; manual builds do not.
            if isinstance(value, str) and DOLLAR_RE.search(value) and not dynamic:
                for match in DOLLAR_RE.finditer(value):
                    if match.group(2) or match.group(3):
                        self.report(
                            "CB020",
                            line,
                            f"`{key}` references another substitution; "
                            "set options.dynamicSubstitutions: true",
                        )
                        break

    def check_secrets_block(self) -> None:
        available = field_get(self.doc, "availableSecrets")
        if isinstance(available, dict):
            for entry in field_get(available, "secretManager") or []:
                env = field_get(entry, "env")
                if isinstance(env, str):
                    self.declared_secrets[str(env)] = line_of(entry, "env", available.line)
        for entry in field_get(self.doc, "secrets") or []:
            for env in field_get(entry, "secretEnv") or {}:
                self.declared_secrets.setdefault(str(env), line_of(entry, "secretEnv"))

    def check_timeout(self) -> None:
        if "timeout" not in self.doc:
            self.report("CB032", 1, "always set a build timeout; Cloud Build defaults to 60m")
            return

        line = self.doc.line_of("timeout")
        raw = self.doc["timeout"]
        seconds = parse_duration(raw)
        if seconds is None:
            self.report(
                "CB010",
                line,
                f"timeout is `{raw}`; it must be a quoted duration in seconds, such as 600s",
            )
            return

        self.build_timeout = seconds
        if seconds > MAX_TIMEOUT_SECONDS and not self.has_nearby_comment(line):
            self.report(
                "CB033",
                line,
                f"{raw} is above the {MAX_TIMEOUT_SECONDS}s ceiling; "
                "a hung build burns quota instead of failing",
            )

    def has_nearby_comment(self, line: int) -> bool:
        """Report whether a comment sits on the given line or just above it."""
        for index in (line - 1, line - 2, line - 3):
            if 0 <= index < len(self.lines) and "#" in self.lines[index]:
                return True
        return False

    # -- layer 3: steps --

    def check_steps(self) -> None:
        steps = field_get(self.doc, "steps")
        if not isinstance(steps, list):
            return

        known = {norm(f) for f in STEP_FIELDS}
        seen_ids: dict[str, int] = {}

        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                self.report("CB005", getattr(steps, "line", 1), f"step {index} is not a mapping")
                continue

            line = step.line
            label = self.step_label(step, index)

            for key in step:
                if norm(str(key)) not in known:
                    self.report(
                        "CB006",
                        step.line_of(str(key)),
                        f"`{key}` is not a build step field ({label})",
                    )

            name = field_get(step, "name")
            if not name:
                self.report("CB005", line, f"{label} has no `name`; every step needs an image")
            else:
                self.check_image(str(name), field_line(step, "name", line), label)

            self.check_step_ids(step, index, seen_ids, label)
            self.check_step_timeout(step, line, label)
            self.check_step_secrets(step, label)
            self.check_step_scripts(step, label)

    def step_label(self, step, index: int) -> str:
        """Return a human handle for a step: its id when it has one."""
        step_id = field_get(step, "id")
        return f"step {index} `{step_id}`" if step_id else f"step {index}"

    def check_step_ids(self, step, index: int, seen_ids: dict[str, int], label: str) -> None:
        step_id = field_get(step, "id")
        wait_for = field_get(step, "waitFor")

        if isinstance(wait_for, list):
            for dep in wait_for:
                if dep == "-":
                    continue
                if str(dep) not in seen_ids:
                    self.report(
                        "CB009",
                        field_line(step, "waitFor", step.line),
                        f"{label} waits for `{dep}`, which no earlier step defines",
                    )

        if isinstance(step_id, str):
            if str(step_id) in seen_ids:
                self.report(
                    "CB008",
                    field_line(step, "id", step.line),
                    f"id `{step_id}` is already used by an earlier step",
                )
            seen_ids[str(step_id)] = index

    def check_step_timeout(self, step, line: int, label: str) -> None:
        if "timeout" not in step:
            return
        raw = field_get(step, "timeout")
        seconds = parse_duration(raw)
        step_line = field_line(step, "timeout", line)
        if seconds is None:
            self.report("CB010", step_line, f"{label} timeout is `{raw}`; use a duration like 600s")
            return
        if self.build_timeout is not None and seconds > self.build_timeout:
            self.report(
                "CB011",
                step_line,
                f"{label} allows {raw}, more than the build's own timeout",
            )

    def check_step_secrets(self, step, label: str) -> None:
        for env in field_get(step, "secretEnv") or []:
            self.used_secrets.add(str(env))
            if str(env) not in self.declared_secrets:
                self.report(
                    "CB021",
                    field_line(step, "secretEnv", step.line),
                    f"{label} uses secret `{env}`, which availableSecrets does not declare",
                )

    def check_image(self, image: str, line: int, label: str) -> None:
        base = basename_image(image)
        if "alpine" in image.lower():
            self.report("CB034", line, f"{label} runs {image}; prefer a Debian base image")
        if ":" not in base and "@" not in base:
            owner = image.split("/")[1] if image.count("/") >= 2 else ""
            if owner not in SHARED_REGISTRY_OWNERS:
                self.report("CB039", line, f"{label} runs {image} untagged, so it floats on latest")
        self.check_registry_path(image, line, label)

    def check_registry_path(self, value: str, line: int, label: str) -> None:
        for match in IMAGE_REF_RE.finditer(value):
            owner = match.group(2)
            if owner in SHARED_REGISTRY_OWNERS:
                continue
            if "$PROJECT_ID" in owner or "${PROJECT_ID}" in owner:
                continue
            self.report(
                "CB035",
                value.line_at(match.start()) if isinstance(value, Scalar) else line,
                f"{label} names project `{owner}` directly; use $PROJECT_ID ({match.group(0)}…)",
            )

    # -- steps: shell bodies and substitution escaping --

    def check_step_scripts(self, step, label: str) -> None:
        script = field_get(step, "script")
        args = field_get(step, "args")
        entrypoint = field_get(step, "entrypoint")
        name = str(field_get(step, "name") or "")
        automap = bool(field_get(step, "automapSubstitutions")) or self.build_automap
        env_names = self.step_env_names(step)

        if script is not None and (args is not None or entrypoint is not None):
            self.report(
                "CB013",
                field_line(step, "script", step.line),
                f"{label} sets script alongside args or entrypoint; Cloud Build allows only one",
            )

        for value in self.strings_in(field_get(step, "env")):
            self.scan_dollars(value, "plain", label)
        for value in self.strings_in(field_get(step, "dir")):
            self.scan_dollars(value, "plain", label)
        if name:
            self.scan_dollars(name, "plain", label)

        if isinstance(script, str):
            self.scan_dollars(script, "script", label, automap=automap, env_names=env_names)
            self.check_registry_path(script, step.line, label)
            self.check_shell_body(script, label)
            return

        shell = self.is_shell_step(name, entrypoint)
        if not isinstance(args, list):
            for value in self.strings_in(args):
                self.scan_dollars(value, "plain", label)
            return

        expect_body = False
        for arg in args:
            if not isinstance(arg, str):
                expect_body = False
                continue
            is_body = shell and (expect_body or "\n" in arg)
            self.scan_dollars(arg, "shell" if is_body else "plain", label, automap=automap)
            if is_body:
                self.check_shell_body(arg, label)
            self.check_registry_path(arg, getattr(arg, "line", step.line), label)
            expect_body = shell and self.is_command_flag(arg)

    def is_shell_step(self, name: str, entrypoint) -> bool:
        """Report whether the step's args are handed to a shell."""
        runner = str(entrypoint) if entrypoint else basename_image(name).split(":")[0]
        return basename_image(runner) in SHELLS

    def is_command_flag(self, arg: str) -> bool:
        """Report whether this arg is the -c that introduces a shell body."""
        if not arg.startswith("-") or arg.startswith("--") or len(arg) > 5:
            return False
        return arg.endswith("c")

    def step_env_names(self, step) -> set[str]:
        """Return the env var names a step defines, which a script can read."""
        names = set()
        for entry in field_get(step, "env") or []:
            if isinstance(entry, str) and "=" in entry:
                names.add(entry.split("=", 1)[0])
        for entry in field_get(step, "secretEnv") or []:
            names.add(str(entry))
        return names

    def strings_in(self, value):
        """Yield every string in a scalar or a flat list."""
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    yield item

    def scan_dollars(
        self,
        value: str,
        context: str,
        label: str,
        automap: bool = False,
        env_names: set[str] | None = None,
    ) -> None:
        """Check every $ in a string against the rules for its context.

        Cloud Build rewrites `$NAME` and `${NAME}` before the step runs, and
        collapses each `$$` to a literal `$`. So an odd run of dollars
        substitutes and an even run does not. The right spelling flips
        depending on where the string lands:

        - plain fields and shell bodies in `args` are substituted, so a shell
          variable needs `$$VAR` and a substitution needs `$VAR`
        - `script` bodies are never substituted, so a shell variable needs
          `$VAR` and a substitution has to arrive through env or automap
        """
        base_line = getattr(value, "line", 0)
        env_names = env_names or set()

        for match in DOLLAR_RE.finditer(value):
            dollars = match.group(1)
            braced, bare = match.group(2), match.group(3)
            name = braced if braced is not None else bare
            if name is None:
                # $(cmd), $1, $@, a bare $$. None of these are substitutions.
                continue

            line = value.line_at(match.start()) if isinstance(value, Scalar) else base_line
            written = match.group(0)
            substituted = len(dollars) % 2 == 1
            malformed = braced is not None and not IDENT_RE.match(braced)

            if name in self.known_subs:
                self.used_subs.add(name)

            if context == "script":
                if len(dollars) >= 2:
                    self.report(
                        "CB018",
                        line,
                        f"{label}: `{written}` in a script body; the shell reads $$ as its PID, "
                        f"so write `${name}`",
                    )
                elif name in BUILTIN_SUBS and not automap and name not in env_names:
                    self.report(
                        "CB017",
                        line,
                        f"{label}: script bodies are never substituted, so `{written}` is empty; "
                        "map it through env or set automapSubstitutions: true",
                    )
                continue

            if substituted:
                if malformed:
                    self.report(
                        "CB015",
                        line,
                        f"{label}: `{written}` is not a valid substitution; "
                        f"write `$${written[len(dollars) :]}` to reach the shell",
                    )
                elif name not in self.known_subs:
                    hint = "$$" + written[len(dollars) :]
                    self.report(
                        "CB015",
                        line,
                        f"{label}: `{written}` is not a Cloud Build substitution, "
                        f"so it expands to nothing; write `{hint}` for a shell variable",
                    )
            elif context == "shell" and name in self.known_subs and not automap:
                self.report(
                    "CB016",
                    line,
                    f"{label}: `{written}` reaches the shell as a plain variable and is empty; "
                    f"write `${name}` to substitute it",
                )

    def check_shell_body(self, body: str, label: str) -> None:
        base_line = getattr(body, "line", 0)
        line = base_line + 1 if getattr(body, "style", None) in ("|", ">") else base_line
        code_lines = [
            ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")
        ]

        # Without set -e only the last command's status reaches Cloud Build, so
        # a failure in the middle passes the build.
        if len(code_lines) > 1 and not SET_E_RE.search(body):
            self.report(
                "CB037",
                line,
                f"{label}: no `set -e`, so a failing command mid-script passes",
            )

        if len(code_lines) > LONG_SCRIPT_LINES:
            self.report(
                "CB040",
                line,
                f"{label}: {len(code_lines)} lines inline; move this into a Makefile target",
            )

        created = BUILDX_CREATE_RE.search(body)
        used = BUILDX_USE_RE.search(body)
        if created and used and created.group(1) != used.group(1):
            self.report(
                "CB036",
                line + body[: used.start()].count("\n"),
                f"{label}: `buildx use {used.group(1)}` does not match "
                f"`buildx create --name {created.group(1)}`",
            )

        if BUILDX_PUSH_RE.search(body) and field_get(self.doc, "images"):
            self.report(
                "CB038",
                line,
                f"{label}: buildx --push already pushed; the `images` block pushes it again",
            )

    # -- cross-cutting --

    def check_unused(self) -> None:
        for key, line in self.declared_subs.items():
            if key not in self.used_subs:
                self.report(
                    "CB019",
                    line,
                    f"`{key}` is declared and never used; a manual build rejects that",
                )
        for env, line in self.declared_secrets.items():
            if env not in self.used_secrets:
                self.report("CB022", line, f"secret `{env}` is declared and no step reads it")

    def check_comments(self) -> None:
        header: list[str] = []
        for raw in self.lines:
            stripped = raw.strip()
            if not stripped:
                if header:
                    break
                continue
            if not stripped.startswith("#"):
                break
            header.append(stripped)

        for index, raw in enumerate(self.lines):
            if SCAFFOLDING_RE.search(raw) and raw.strip().startswith("#"):
                self.report(
                    "CB043",
                    index + 1,
                    "template scaffolding is still here; everything above the cut line is a "
                    "note to the author and never ships",
                )
                break

        if not header:
            self.report("CB041", 1, "add a header naming the triggers that drive this file")
            return

        body = sum(1 for raw in self.lines if raw.strip() and not raw.strip().startswith("#"))
        if len(header) > body:
            self.report(
                "CB042",
                1,
                f"the header runs {len(header)} lines over {body} lines of config; "
                "keep the triggers and the surprises, cut the rest",
            )


# --- CLI --------------------------------------------------------------------


def default_paths() -> list[Path]:
    """Return every cloudbuild config in the current directory."""
    found = sorted(Path(".").glob("cloudbuild*.yaml")) + sorted(Path(".").glob("cloudbuild*.yml"))
    return found


def list_checks() -> None:
    for code in sorted(CHECKS):
        level, title = CHECKS[code]
        print(f"{code}  {level:<5}  {title}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate-cloudbuild.py",
        description="Parse, schema-check, and lint a Cloud Build config.",
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, help="config files (default: cloudbuild*.yaml)"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    parser.add_argument("--strict", action="store_true", help="fail on warnings and notes too")
    parser.add_argument("--errors-only", action="store_true", help="print errors, drop the rest")
    parser.add_argument(
        "--ignore", default="", metavar="CODES", help="comma-separated codes to skip"
    )
    parser.add_argument("--list-checks", action="store_true", help="print every check and exit")
    args = parser.parse_args(argv)

    if args.list_checks:
        list_checks()
        return 0

    paths = args.paths or default_paths()
    if not paths:
        print("no cloudbuild*.yaml found; pass a path explicitly", file=sys.stderr)
        return 2

    ignored = {code.strip().upper() for code in args.ignore.split(",") if code.strip()}
    unknown = ignored - set(CHECKS)
    if unknown:
        print(f"unknown check code(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as err:
            print(f"cannot read {path}: {err}", file=sys.stderr)
            return 2
        findings.extend(Linter(path, text).run())

    findings = [f for f in findings if f.code not in ignored]
    if args.errors_only:
        findings = [f for f in findings if f.level == ERROR]

    if args.format == "json":
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        for finding in findings:
            print(finding.format_text())
        counts = {level: sum(1 for f in findings if f.level == level) for level in LEVEL_RANK}
        checked = ", ".join(str(p) for p in paths)
        if findings:
            print(
                f"\n{counts[ERROR]} error(s), {counts[WARN]} warning(s), "
                f"{counts[NOTE]} note(s) in {checked}"
            )
        else:
            print(f"{checked}: clean")

    threshold = NOTE if args.strict else ERROR
    failed = any(LEVEL_RANK[f.level] >= LEVEL_RANK[threshold] for f in findings)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
