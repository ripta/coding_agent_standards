"""Cross-file checks on the standards' own prose.

Each test pins a fact one file states about another: a path that must exist, a script
subcommand that must be defined, a vocabulary two files must agree on. Judgment about whether a
rule is still right stays with audits and the reviewer agent.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = ROOT / "claude"
SCRIPTS = CLAUDE / "scripts"

INSTRUCTION_DIRS = ("agents", "commands", "skills", "rules", "project-management", "knowledge", "hooks")
INSTRUCTION_FILES = sorted(p for d in INSTRUCTION_DIRS for p in (CLAUDE / d).rglob("*.md"))

FENCE = re.compile(r"^\s*(```|~~~)")
SPAN = re.compile(r"`([^`\n]+)`")

# Claude Code's model aliases. A dated model ID goes stale at the next release.
MODEL_ALIASES = {"opus", "sonnet", "haiku", "opusplan", "inherit"}


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def prose_lines(path: Path):
    """Yield (line number, text) for lines outside fenced code blocks."""
    fenced = False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, line


def spans(path: Path):
    """Yield (line number, content) for each inline code span outside fences."""
    for number, line in prose_lines(path):
        for match in SPAN.finditer(line):
            yield number, match.group(1)


def frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.index("\n---\n", 4)
    return yaml.safe_load(text[4:end]) or {}


# -- paths ----------------------------------------------------------------------------------

PATH_PREFIXES = (
    "claude/", "rules/", "project-management/", "skills/", "agents/", "commands/", "hooks/",
    "scripts/", "knowledge/", "practices/", "languages/", "profiles/", "settings/", "types/",
    "bugs/", "vale/", "rumdl/",
)
PLUGIN_ROOT = re.compile(r"^\$\{CLAUDE_PLUGIN_ROOT\}/|^\$\{CLAUDE_SKILL_DIR\}/\.\./\.\./")
SKILL_DIR = re.compile(r"^\$\{CLAUDE_SKILL_DIR\}/")


def unresolved_paths(path: Path):
    for number, content in spans(path):
        candidate = PLUGIN_ROOT.sub("claude/", content)
        candidate = SKILL_DIR.sub(f"{rel(path.parent)}/", candidate).rstrip(".,:;)")
        if not candidate.startswith(PATH_PREFIXES) or re.search(r"[<>*{}$\s]", candidate):
            continue
        roots = (ROOT, CLAUDE, path.parent, CLAUDE / "knowledge" / "templates" / "wiki")
        if not any((root / candidate).exists() for root in roots):
            yield f"{rel(path)}:{number}: {content}"


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=rel)
def test_quoted_paths_resolve(path: Path) -> None:
    assert list(unresolved_paths(path)) == []


# -- script commands ------------------------------------------------------------------------

SCRIPT_CALL = re.compile(
    r"\b(proposals|detect_era|pr_watch|batch_plan)\.py(?: ([a-z][a-z-]*))?((?: --[a-z][a-z-]*)*)"
)


def script_help(script: str, subcommand: str | None) -> str:
    args = [sys.executable, str(SCRIPTS / f"{script}.py")]
    if subcommand:
        args.append(subcommand)
    result = subprocess.run([*args, "--help"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def script_calls():
    seen = set()
    for path in INSTRUCTION_FILES:
        for number, line in prose_lines(path):
            for match in SCRIPT_CALL.finditer(line):
                script, subcommand, flags = match.groups()
                if script == "detect_era":
                    flags = f" {subcommand}{flags}" if subcommand and subcommand.startswith("--") else flags
                    subcommand = None
                key = (script, subcommand, flags)
                if key not in seen:
                    seen.add(key)
                    yield pytest.param(script, subcommand, flags.split(), id=f"{rel(path)}:{number}")


@pytest.mark.parametrize(("script", "subcommand", "flags"), list(script_calls()))
def test_named_script_commands_exist(script: str, subcommand: str | None, flags: list[str]) -> None:
    help_text = script_help(script, subcommand)
    assert help_text, f"{script}.py {subcommand or ''} is not a command"
    for flag in flags:
        assert flag in help_text, f"{script}.py {subcommand or ''} has no {flag}"


# -- frontmatter ----------------------------------------------------------------------------

SKILLS = sorted(CLAUDE.glob("skills/*/SKILL.md"))
AGENTS = sorted(CLAUDE.glob("agents/*.md"))
COMMANDS = sorted(CLAUDE.glob("commands/*.md"))


@pytest.mark.parametrize("path", SKILLS + AGENTS + COMMANDS, ids=rel)
def test_frontmatter_parses_and_describes(path: Path) -> None:
    meta = frontmatter(path)
    assert isinstance(meta.get("description"), str) and meta["description"].strip()
    if "model" in meta:
        assert meta["model"] in MODEL_ALIASES


@pytest.mark.parametrize("path", SKILLS + AGENTS, ids=rel)
def test_name_matches_its_file(path: Path) -> None:
    expected = path.parent.name if path.name == "SKILL.md" else path.stem
    assert frontmatter(path).get("name") == expected


@pytest.mark.parametrize("path", COMMANDS + SKILLS, ids=rel)
def test_arguments_come_with_a_hint(path: Path) -> None:
    if "$ARGUMENTS" not in path.read_text():
        return
    meta = frontmatter(path)
    assert "argument-hint" in meta or path.name == "SKILL.md"


# -- shell discipline -----------------------------------------------------------------------

COMMAND_WORDS = (
    "awk", "cat", "cd", "echo", "find", "gcloud", "gh", "git", "grep", "ls", "make", "node",
    "python3", "rm", "rumdl", "sed", "uv", "uvx", "vale",
)
CHAIN = re.compile(r" (&&|\|\||\||;) ")


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=rel)
def test_inline_commands_are_not_chained(path: Path) -> None:
    chained = [
        f"{rel(path)}:{number}: {content}"
        for number, content in spans(path)
        if content.split(" ", 1)[0] in COMMAND_WORDS and CHAIN.search(content)
    ]
    assert chained == [], "rules/shell-discipline.md forbids chaining in one invocation"


# -- Makefile vocabulary --------------------------------------------------------------------

VERBS = ("build", "check", "clean", "fix", "fmt", "lint", "test")
SYNONYMS = {"format", "tests", "typecheck"}
MAKE_TARGET = re.compile(r"^make ([a-z0-9][a-z0-9-]*)")


@pytest.mark.parametrize("path", INSTRUCTION_FILES, ids=rel)
def test_make_targets_follow_the_vocabulary(path: Path) -> None:
    wrong = []
    for number, content in spans(path):
        match = MAKE_TARGET.match(content)
        if not match:
            continue
        target = match.group(1)
        first, last = target.split("-")[0], target.split("-")[-1]
        reversed_form = last in VERBS and first not in VERBS + ("update", "install")
        if target in SYNONYMS or ("-" in target and reversed_form):
            wrong.append(f"{rel(path)}:{number}: {content}")
    assert wrong == [], "practices/makefile.md names variants <verb>-<component>"


# -- vocabularies ---------------------------------------------------------------------------


def tracking_vocabulary(artifact: str) -> set[str]:
    text = (CLAUDE / "project-management" / "tracking.md").read_text()
    section = text.split("## Status Vocabularies", 1)[1].split("\n## ", 1)[0]
    bullet = re.search(rf"^- {artifact} use .*?(?=^- |^\s*$)", section, re.M | re.S)
    assert bullet, f"tracking.md has no {artifact} vocabulary"
    return set(re.findall(r"`([^`]+)`", bullet.group(0)))


def test_milestone_vocabulary_matches_the_checker() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import proposals

    assert tracking_vocabulary("Proposal milestones") == proposals.MILESTONE_STATUSES


def test_proposal_vocabulary_covers_the_checker() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import proposals

    used = proposals.NOT_LIVE | proposals.STOPPED | proposals.FROZEN_STATUSES
    assert used <= tracking_vocabulary("Proposals")


def test_adr_impact_names_only_adr_statuses() -> None:
    text = (CLAUDE / "agents" / "adr-impact.md").read_text()
    statuses = text.split("Statuses:", 1)[1].split("\n\n", 2)[1]
    named = {
        word.lower()
        for line in statuses.splitlines()
        if line.startswith("- ")
        for word in re.findall(r"[A-Za-z]+", line.split(":", 1)[0])
        if word.lower() not in {"or", "in", "full", "part"}
    }
    assert named <= tracking_vocabulary("ADRs")


# -- workaround markers ---------------------------------------------------------------------

MARKER = re.compile(r"<!-- Workaround for (bugs/[^ ]+\.md)")


def workaround_markers():
    for path in INSTRUCTION_FILES:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for match in MARKER.finditer(line):
                yield pytest.param(match.group(1), id=f"{rel(path)}:{number}")


@pytest.mark.parametrize("bug", list(workaround_markers()))
def test_workarounds_point_at_open_bugs(bug: str) -> None:
    path = ROOT / bug
    assert path.is_file(), f"{bug} does not exist"
    status = re.search(r"^\*\*Status:\*\* *(\S+)", path.read_text(), re.M)
    assert status and status.group(1) == "open", f"{bug} is closed; remove its workaround"


# -- the checks catch what they claim to ----------------------------------------------------


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "doc.md"
    path.write_text(text)
    return path


def test_a_missing_path_is_reported(tmp_path: Path) -> None:
    path = write(tmp_path, "See `claude/rules/no-such-rule.md` and `claude/rules/precedence.md`.\n")
    assert [line.split(": ", 1)[1] for line in unresolved_paths(path)] == ["claude/rules/no-such-rule.md"]


def test_a_path_inside_a_fence_is_not_checked(tmp_path: Path) -> None:
    path = write(tmp_path, "```text\n`claude/rules/no-such-rule.md`\n```\n")
    assert list(unresolved_paths(path)) == []


def test_chained_inline_commands_are_found(tmp_path: Path) -> None:
    path = write(tmp_path, "Run `cd <dir> && pwd -P`, or `git ls-files | wc -l`, but not `a; b` prose.\n")
    found = [
        content
        for _, content in spans(path)
        if content.split(" ", 1)[0] in COMMAND_WORDS and CHAIN.search(content)
    ]
    assert found == ["cd <dir> && pwd -P", "git ls-files | wc -l"]


def test_component_first_make_targets_are_found(tmp_path: Path) -> None:
    path = write(tmp_path, "Run `make ui-lint`, `make lint-ui`, `make update-golden`, or `make format`.\n")
    with pytest.raises(AssertionError) as failure:
        test_make_targets_follow_the_vocabulary(path)
    assert "make ui-lint" in str(failure.value)
    assert "make format" in str(failure.value)
    assert "lint-ui" not in str(failure.value).replace("ui-lint", "")


def test_unquoted_bracket_hints_fail_to_parse(tmp_path: Path) -> None:
    path = write(tmp_path, "---\ndescription: d\nargument-hint: [a] [b]\n---\n")
    with pytest.raises(yaml.YAMLError):
        frontmatter(path)
