#!/usr/bin/env python3
"""Report on Claude Code memory directories, and on churn in rule files.

    python3 memory.py sweep [--root DIR] [--today DATE] [--since DATE] [--record]
    python3 memory.py retier FILE TIER
    python3 memory.py trash FILE [--today DATE]
    python3 memory.py churn [--repo DIR] [--days N] [--today DATE] [--min-commits N] [PATH ...]

`rules/memory.md` defines the format these commands read: the `Tier`, `Home`, `Scope`, and
`Promotion` lines at the top of a memory's body, and the instance lines under `## Instances`.

`sweep` reads every `<root>/*/memory/` directory and prints one JSON report. Each memory gets a
`status` list drawn from `expired`, `ready_pattern`, `ready_promote`, `held`, `contradicted`, and
`legacy`. A legacy memory has no `Tier` line, and `untiered_new` marks one written since the rule
took effect. Each directory also lists format `problems` and its index's size against the load cap.
`--since` is the last sweep's date, which bounds `contradicted`. It defaults to the date `--record`
saved in `~/.local/state/coding_agent_standards/memory-sweep.json`. `--record` also appends the
summary to `memory-sweep-log.jsonl` there, which the trial review reads.

`retier` rewrites a memory's `Tier` line and the tier in its `MEMORY.md` line. `trash` moves a
memory into a dated trash directory, and removes its `MEMORY.md` line after copying the index
there too. Memory directories are not under version control, so the trash is the only way back.

`churn` lists, for each section of each markdown file under the paths, the commits that touched it
in the window. Added lines map to the section of the new text, and removed lines to the section of
the old text. File renames and heading renames are followed, so a section keeps one key under its
latest name. Only sections with at least `--min-commits` commits are printed.

Errors go to stderr with exit status 1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TIERS = ("observation", "pattern", "fact")
KINDS = ("correction", "confirmation", "case", "contradiction")
COUNTING = ("correction", "confirmation")

PATTERN_DAYS = 3
EXPIRY_DAYS = 60

# Claude Code loads the first 200 lines or 25KB of MEMORY.md, whichever comes first.
INDEX_LINE_CAP = 200
INDEX_BYTE_CAP = 25 * 1024
NEAR_CAP = 0.9

RULE_DATE = dt.date(2026, 11, 25)
LEGACY_TIER = {"reference": "fact", "user": "fact", "project": "fact", "feedback": "observation"}

STATE_DIR = Path.home() / ".local" / "state" / "coding_agent_standards"
TRASH_DIR = STATE_DIR / "memory-trash"
SWEEP_STATE = STATE_DIR / "memory-sweep.json"
SWEEP_LOG = STATE_DIR / "memory-sweep-log.jsonl"

DEFAULT_CHURN_PATHS = ("claude/rules", "claude/practices", "claude/project-management")

INSTANCE_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) ([a-z]+) \(([^)]+)\): (.+)$")
INDEX_RE = re.compile(r"^- \[([^\]]*)\]\(([^)]+)\)\s*(?:—|--|-)?\s*(.*)$")
INDEX_TIER_RE = re.compile(r"^\((observation|pattern|fact)\b[^)]*\)")
HELD_RE = re.compile(r"^held (\d{4}-\d{2}-\d{2})\b")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


class MemoryError_(Exception):
    pass


def parse_date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError as exc:
        raise MemoryError_(f"not a date: {text!r}") from exc


# --- memory files -------------------------------------------------------------------------------


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return the frontmatter's scalar keys, flattened, and the body.

    Claude Code writes `type` either at the top level or under `metadata:`. Both land on `type`.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        return {}, text

    keys: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.match(r"^\s*([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match and match.group(2):
            keys.setdefault(match.group(1), match.group(2).strip().strip("\"'"))

    return keys, "\n".join(lines[end + 1 :])


def parse_memory(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    body_lines = body.splitlines()

    header: dict[str, str] = {}
    index = 0
    while index < len(body_lines) and not body_lines[index].strip():
        index += 1
    while index < len(body_lines) and body_lines[index].strip():
        match = re.match(r"^(Tier|Home|Scope|Promotion):\s*(.*)$", body_lines[index])
        if not match:
            break
        header[match.group(1).lower()] = match.group(2).strip()
        index += 1

    instances: list[dict[str, str]] = []
    bad_instances: list[str] = []
    in_instances = False
    for line in body_lines:
        if line.startswith("## "):
            in_instances = line.strip() == "## Instances"
            continue
        if not in_instances or not line.strip():
            continue

        match = INSTANCE_RE.match(line.strip())
        if not match or match.group(2) not in KINDS:
            bad_instances.append(line.strip())
            continue
        try:
            parse_date(match.group(1))
        except MemoryError_:
            bad_instances.append(line.strip())
            continue
        instances.append(
            {"date": match.group(1), "kind": match.group(2), "context": match.group(3), "case": match.group(4)}
        )

    return {
        "front": front,
        "header": header,
        "instances": instances,
        "bad_instances": bad_instances,
        "hard_rule": "HARD RULE" in text,
    }


def modified_date(path: Path, front: dict[str, str]) -> dt.date:
    if front.get("modified"):
        try:
            return parse_date(front["modified"])
        except MemoryError_:
            pass
    return dt.date.fromtimestamp(path.stat().st_mtime)


def assess(path: Path, parsed: dict[str, Any], today: dt.date, since: dt.date | None) -> dict[str, Any]:
    header = parsed["header"]
    instances = parsed["instances"]
    tier = header.get("tier")
    home = header.get("home")
    problems: list[str] = []
    status: list[str] = []

    dates_by_kind: dict[str, list[dt.date]] = {kind: [] for kind in KINDS}
    for instance in instances:
        dates_by_kind[instance["kind"]].append(parse_date(instance["date"]))

    last_contradiction = max(dates_by_kind["contradiction"], default=None)
    counting_days = sorted(
        {
            day
            for kind in COUNTING
            for day in dates_by_kind[kind]
            if last_contradiction is None or day > last_contradiction
        }
    )
    all_dates = [day for days in dates_by_kind.values() for day in days]
    modified = modified_date(path, parsed["front"])
    last_evidence = max(all_dates, default=modified)

    for line in parsed["bad_instances"]:
        problems.append(f"malformed instance line: {line}")

    if tier is None:
        status.append("legacy")
        memory_type = parsed["front"].get("type")
        result_extra: dict[str, Any] = {
            "type": memory_type,
            "suggested_tier": LEGACY_TIER.get(memory_type or ""),
            "hard_rule": parsed["hard_rule"],
            "untiered_new": modified >= RULE_DATE,
        }
    else:
        result_extra = {}
        if tier not in TIERS:
            problems.append(f"unknown tier: {tier}")
        if tier in ("observation", "pattern"):
            if not home:
                problems.append("missing Home line")
            if not header.get("scope"):
                problems.append("missing Scope line")
            if not instances:
                problems.append("no instances")

    held_since: dt.date | None = None
    promotion = header.get("promotion")
    if promotion:
        match = HELD_RE.match(promotion)
        if match:
            held_since = parse_date(match.group(1))
        else:
            problems.append(f"malformed Promotion line: {promotion}")

    if tier == "observation":
        if (today - last_evidence).days >= EXPIRY_DAYS:
            status.append("expired")
        if len(counting_days) >= PATTERN_DAYS:
            status.append("ready_pattern")

    if tier == "pattern" and home and home != "memory":
        new_since_hold = held_since is not None and any(day > held_since for day in all_dates)
        if held_since is None or new_since_hold:
            status.append("ready_promote")
        else:
            status.append("held")

    if last_contradiction is not None and (since is None or last_contradiction > since):
        status.append("contradicted")

    return {
        "file": path.name,
        "name": parsed["front"].get("name", path.stem),
        "tier": tier,
        "home": home,
        "scope": header.get("scope"),
        "status": status,
        "instances": len(instances),
        "counting_days": [day.isoformat() for day in counting_days],
        "last_evidence": last_evidence.isoformat(),
        "problems": problems,
        **result_extra,
    }


# --- MEMORY.md ----------------------------------------------------------------------------------


def parse_index(path: Path) -> list[dict[str, Any]]:
    entries = []
    if not path.exists():
        return entries

    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = INDEX_RE.match(line.strip())
        if not match:
            continue
        hook = match.group(3)
        tier_match = INDEX_TIER_RE.match(hook)
        entries.append(
            {
                "line": number,
                "title": match.group(1),
                "file": match.group(2),
                "tier": tier_match.group(1) if tier_match else None,
            }
        )
    return entries


def project_path(directory: Path) -> str | None:
    """Read the project's working directory from one of its session transcripts.

    A directory's name replaces every character but letters and digits with `-`, so it cannot be
    mapped back to a path. Transcripts record `cwd`.
    """
    for transcript in sorted(directory.glob("*.jsonl")):
        try:
            with transcript.open(encoding="utf-8") as handle:
                for _, line in zip(range(50), handle):
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict) and isinstance(record.get("cwd"), str):
                        return record["cwd"]
        except OSError:
            continue
    return None


def sweep_directory(directory: Path, today: dt.date, since: dt.date | None) -> dict[str, Any]:
    memory_dir = directory / "memory"
    index_path = memory_dir / "MEMORY.md"
    index_entries = parse_index(index_path)
    index_text = index_path.read_bytes() if index_path.exists() else b""
    index_lines = len(index_text.decode("utf-8", errors="replace").splitlines())

    problems: list[str] = []
    memories = []
    files = sorted(p for p in memory_dir.glob("*.md") if p.name != "MEMORY.md")
    by_name = {p.name: p for p in files}
    indexed = {entry["file"] for entry in index_entries}

    for path in files:
        memory = assess(path, parse_memory(path), today, since)
        memories.append(memory)
        if path.name not in indexed:
            problems.append(f"{path.name}: no MEMORY.md line")

    tiers = {memory["file"]: memory["tier"] for memory in memories}
    for entry in index_entries:
        if entry["file"] not in by_name:
            problems.append(f"MEMORY.md line {entry['line']}: no file {entry['file']}")
            continue
        file_tier = tiers.get(entry["file"])
        if file_tier and entry["tier"] != file_tier:
            problems.append(
                f"MEMORY.md line {entry['line']}: tier {entry['tier'] or 'missing'} but {entry['file']} says {file_tier}"
            )

    cwd = project_path(directory)
    return {
        "directory": str(directory),
        "project_path": cwd,
        "project_exists": None if cwd is None else Path(cwd).exists(),
        "index": {
            "lines": index_lines,
            "bytes": len(index_text),
            "near_cap": index_lines >= INDEX_LINE_CAP * NEAR_CAP or len(index_text) >= INDEX_BYTE_CAP * NEAR_CAP,
        },
        "memories": memories,
        "problems": problems,
    }


def read_last_sweep() -> dt.date | None:
    try:
        return parse_date(json.loads(SWEEP_STATE.read_text())["last_sweep"])
    except (OSError, ValueError, KeyError, TypeError, MemoryError_):
        return None


def sweep(root: Path, today: dt.date, since: dt.date | None, record: bool) -> dict[str, Any]:
    if since is None:
        since = read_last_sweep()

    directories = [
        sweep_directory(directory, today, since)
        for directory in sorted(root.iterdir())
        if (directory / "memory").is_dir()
    ]

    summary: dict[str, int] = {}
    for directory in directories:
        for memory in directory["memories"]:
            for status in memory["status"]:
                summary[status] = summary.get(status, 0) + 1
            if memory.get("untiered_new"):
                summary["untiered_new"] = summary.get("untiered_new", 0) + 1
            summary["instances"] = summary.get("instances", 0) + memory["instances"]
        summary["problems"] = summary.get("problems", 0) + len(directory["problems"]) + sum(
            len(memory["problems"]) for memory in directory["memories"]
        )

    if record:
        SWEEP_STATE.parent.mkdir(parents=True, exist_ok=True)
        SWEEP_STATE.write_text(json.dumps({"last_sweep": today.isoformat()}) + "\n")
        with SWEEP_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"date": today.isoformat(), "summary": summary}, sort_keys=True) + "\n")

    return {
        "today": today.isoformat(),
        "since": since.isoformat() if since else None,
        "thresholds": {"pattern_days": PATTERN_DAYS, "expiry_days": EXPIRY_DAYS},
        "summary": summary,
        "directories": directories,
    }


def retier(path: Path, tier: str) -> dict[str, Any]:
    if tier not in TIERS:
        raise MemoryError_(f"tier must be one of {', '.join(TIERS)}")

    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(r"(?m)^Tier:.*$", f"Tier: {tier}", text, count=1)
    if count == 0:
        raise MemoryError_(f"{path} has no Tier line")
    path.write_text(new_text, encoding="utf-8")

    index_path = path.parent / "MEMORY.md"
    changed_index = False
    if index_path.exists():
        lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
        for number, line in enumerate(lines):
            match = INDEX_RE.match(line.strip())
            if match and match.group(2) == path.name:
                lines[number] = re.sub(r"\((observation|pattern|fact)\b", f"({tier}", line, count=1)
                changed_index = lines[number] != line
        index_path.write_text("".join(lines), encoding="utf-8")

    return {"file": str(path), "tier": tier, "index_updated": changed_index}


def trash(path: Path, today: dt.date) -> dict[str, Any]:
    if not path.is_file():
        raise MemoryError_(f"{path} is not a file")
    if path.name == "MEMORY.md":
        raise MemoryError_("trash a memory, not the index")

    slug = path.parent.parent.name
    target_dir = TRASH_DIR / today.isoformat() / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / path.name
    suffix = 1
    while target.exists():
        target = target_dir / f"{path.stem}.{suffix}{path.suffix}"
        suffix += 1

    index_path = path.parent / "MEMORY.md"
    removed_lines = 0
    if index_path.exists():
        stamp = dt.datetime.now().strftime("%H%M%S")
        shutil.copy2(index_path, target_dir / f"MEMORY.md.{stamp}")
        kept = []
        for line in index_path.read_text(encoding="utf-8").splitlines(keepends=True):
            match = INDEX_RE.match(line.strip())
            if match and match.group(2) == path.name:
                removed_lines += 1
                continue
            kept.append(line)
        index_path.write_text("".join(kept), encoding="utf-8")

    shutil.move(str(path), str(target))
    return {"file": str(path), "trashed_to": str(target), "index_lines_removed": removed_lines}


# --- churn --------------------------------------------------------------------------------------


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise MemoryError_(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def headings(text: str) -> list[str]:
    """Return, for each line, the nearest heading at or above it. Fenced code is not a heading."""
    current = "(top)"
    in_fence = False
    result = []
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence:
            match = HEADING_RE.match(line)
            if match:
                current = f"{match.group(1)} {match.group(2)}"
        result.append(current)
    return result


def file_at(repo: Path, rev: str, path: str) -> str:
    return git(repo, "show", f"{rev}:{path}", check=False)


def resolve_alias(aliases: dict[Any, Any], key: Any) -> Any:
    seen = set()
    while key in aliases and key not in seen:
        seen.add(key)
        key = aliases[key]
    return key


def commit_changes(repo: Path, sha: str, paths: list[str]) -> list[tuple[str, str]]:
    """Return (old path, new path) for each markdown file the commit touched under the paths."""
    output = git(repo, "show", "-M", "--name-status", "--format=", sha, "--", *paths)
    changes = []
    for line in output.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0][0]
        if status == "R" and len(parts) == 3:
            old, new = parts[1], parts[2]
        elif len(parts) >= 2:
            old = new = parts[1]
        else:
            continue
        if status == "A":
            old = ""
        if status == "D":
            new = ""
        if (old or new).endswith(".md"):
            changes.append((old, new))
    return changes


def note_renames(
    aliases: dict[tuple[str, str], tuple[str, str]],
    old_path: str,
    new_path: str,
    removed: list[str],
    added: list[str],
) -> None:
    """Record a hunk that swaps headings one for one, at the same level, as a section rename."""
    if not removed or len(removed) != len(added):
        return
    for before, after in zip(removed, added):
        if before != after and before.split(" ", 1)[0] == after.split(" ", 1)[0]:
            aliases[(old_path, before)] = (new_path, after)


def churn(repo: Path, paths: list[str], since: dt.date, min_commits: int) -> dict[str, Any]:
    repo = Path(git(repo, "rev-parse", "--show-toplevel").strip())
    log = git(repo, "log", "--reverse", f"--since={since.isoformat()}", "--format=%H%x09%ad%x09%s", "--date=short",
              "--", *paths)

    file_alias: dict[str, str] = {}
    section_alias: dict[tuple[str, str], tuple[str, str]] = {}
    records: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}

    for entry in log.splitlines():
        sha, date, subject = entry.split("\t", 2)
        for old_path, new_path in commit_changes(repo, sha, paths):
            if old_path and new_path and old_path != new_path:
                file_alias[old_path] = new_path

            old_text = file_at(repo, f"{sha}^", old_path) if old_path else ""
            new_text = file_at(repo, sha, new_path) if new_path else ""
            old_headings = headings(old_text)
            new_headings = headings(new_text)
            diff_paths = [p for p in {old_path, new_path} if p]
            diff = git(repo, "show", "-M", "--unified=0", "--format=", sha, "--", *diff_paths)

            touched: dict[tuple[str, str], list[int]] = {}
            removed_headings: list[str] = []
            added_headings: list[str] = []
            old_line = new_line = 0
            for line in diff.splitlines():
                hunk = HUNK_RE.match(line)
                if hunk:
                    note_renames(section_alias, old_path or new_path, new_path or old_path, removed_headings,
                                 added_headings)
                    removed_headings, added_headings = [], []
                    old_line, new_line = int(hunk.group(1)), int(hunk.group(3))
                    continue
                if line.startswith(("---", "+++")):
                    continue
                if line.startswith("-"):
                    section = old_headings[old_line - 1] if 0 < old_line <= len(old_headings) else "(top)"
                    heading = HEADING_RE.match(line[1:])
                    if heading:
                        removed_headings.append(f"{heading.group(1)} {heading.group(2)}")
                    touched.setdefault((old_path, section), [0, 0])[1] += 1
                    old_line += 1
                elif line.startswith("+"):
                    section = new_headings[new_line - 1] if 0 < new_line <= len(new_headings) else "(top)"
                    heading = HEADING_RE.match(line[1:])
                    if heading:
                        added_headings.append(f"{heading.group(1)} {heading.group(2)}")
                    touched.setdefault((new_path, section), [0, 0])[0] += 1
                    new_line += 1

            note_renames(section_alias, old_path or new_path, new_path or old_path, removed_headings, added_headings)

            for (path, section), (added, removed) in touched.items():
                per_commit = records.setdefault((path, section), {})
                record = per_commit.setdefault(
                    sha, {"sha": sha, "date": date, "subject": subject, "added": 0, "removed": 0}
                )
                record["added"] += added
                record["removed"] += removed

    def by_latest_path(key: tuple[str, str]) -> tuple[str, str]:
        return (resolve_alias(file_alias, key[0]), key[1])

    latest_sections = {by_latest_path(before): by_latest_path(after) for before, after in section_alias.items()}

    merged: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for key, per_commit in records.items():
        key = resolve_alias(latest_sections, by_latest_path(key))
        target = merged.setdefault(key, {})
        for sha, record in per_commit.items():
            existing = target.get(sha)
            if existing:
                existing["added"] += record["added"]
                existing["removed"] += record["removed"]
            else:
                target[sha] = dict(record)

    sections = [
        {"file": path, "section": section, "commits": sorted(per_commit.values(), key=lambda r: r["date"])}
        for (path, section), per_commit in merged.items()
        if len(per_commit) >= min_commits
    ]
    sections.sort(key=lambda s: (-len(s["commits"]), s["file"], s["section"]))
    return {"repo": str(repo), "since": since.isoformat(), "min_commits": min_commits, "sections": sections}


# --- entry point --------------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="memory.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_sweep = sub.add_parser("sweep", help="report on every memory directory")
    p_sweep.add_argument("--root", default=str(Path.home() / ".claude" / "projects"))
    p_sweep.add_argument("--today")
    p_sweep.add_argument("--since", help="the last sweep's date")
    p_sweep.add_argument("--record", action="store_true", help="save today as the last sweep's date")

    p_retier = sub.add_parser("retier", help="change a memory's tier and its index line")
    p_retier.add_argument("file")
    p_retier.add_argument("tier", choices=TIERS)

    p_trash = sub.add_parser("trash", help="move a memory to the trash and drop its index line")
    p_trash.add_argument("file")
    p_trash.add_argument("--today")

    p_churn = sub.add_parser("churn", help="list commits per rule-file section")
    p_churn.add_argument("--repo", default=".")
    p_churn.add_argument("--days", type=int, default=30)
    p_churn.add_argument("--today")
    p_churn.add_argument("--min-commits", type=int, default=3)
    p_churn.add_argument("paths", nargs="*")

    args = parser.parse_args(argv)
    try:
        today = parse_date(args.today) if getattr(args, "today", None) else dt.date.today()
        if args.command == "sweep":
            since = parse_date(args.since) if args.since else None
            result = sweep(Path(os.path.expanduser(args.root)), today, since, args.record)
        elif args.command == "retier":
            result = retier(Path(args.file), args.tier)
        elif args.command == "trash":
            result = trash(Path(args.file), today)
        else:
            paths = args.paths or list(DEFAULT_CHURN_PATHS)
            result = churn(Path(args.repo), paths, today - dt.timedelta(days=args.days), args.min_commits)
    except (MemoryError_, OSError) as exc:
        print(f"memory.py: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
