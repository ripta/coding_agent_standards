#!/usr/bin/env python3
"""Read era 3 proposals and the queue, and run the checks the standard defines.

    python3 proposals.py check --proposals-dir DIR
    python3 proposals.py row --proposals-dir DIR PROJ-NNN [MN]
    python3 proposals.py freeze --proposals-dir DIR [--row-commit SHA ...]
    python3 proposals.py hooks --proposals-dir DIR [--passed] [--today YYYY-MM-DD]
    python3 proposals.py progress --proposals-dir DIR [--json] [--today YYYY-MM-DD]
    python3 proposals.py notice --proposals-dir DIR [--today YYYY-MM-DD]

The rules live in project-management/proposals.md and plans.md. `check` reports
milestone status and hook structure the standard rejects. `row` finds the queue
row that names a milestone, or a proposal's next unfinished one, and says
whether it is ready. `freeze` reports edits to implemented proposals that the
freeze does not allow. `hooks` lists every revisit hook, passed dates first.
`progress` reports the queue as done, ready, and held rows, with the hooks.
`notice` prints one line when any hook has passed, and nothing otherwise.

DIR is the proposals directory, which may sit in a symlinked specs repo. Results
are JSON on stdout. Errors go to stderr with exit status 1.
"""

import argparse
import difflib
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

MILESTONE_STATUSES = {"NOT STARTED", "IN PROGRESS", "DONE", "DROPPED"}
FINISHED = {"DONE", "DROPPED"}
NOT_LIVE = {"implemented", "rejected", "superseded", "retracted"}
STOPPED = {"deferred", "rejected", "superseded", "retracted"}

PROPOSAL_FILE = re.compile(r"^([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)-.*\.md$")
PROPOSAL_STATUS = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.IGNORECASE)
MILESTONE_HEADING = re.compile(r"^###\s+M(\d+):")
REPLACED_BY = re.compile(r"^\s*(?:-\s*)?Replaced by:\s*([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)(?:\s+M(\d+))?\s*$")
AS_BUILT = "**As built:**"
ROW_RANGE = re.compile(r"^([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)\s+M(\d+)(?:-M(\d+))?$")
DEPENDENCY = re.compile(r"^([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)(?:\s+M(\d+))?(\s+\(deployed\))?$")
META_LINE = re.compile(r"^\*\*(Status|Updated|Revisit):\*\*", re.IGNORECASE)
PARTIAL_SUPERSESSION = re.compile(r"Superseded in part by [A-Z0-9]*[A-Z][A-Z0-9]*-\d+; see Decision Log\.")
FROZEN_STATUSES = {"implemented", "superseded"}
LINK_TARGET = re.compile(r"\]\([^)]*\)")
AUDIT_ENTRY = re.compile(r"\brevisit\b", re.IGNORECASE)
CORRECTION_ENTRY = re.compile(r"\bcorrection of fact\b", re.IGNORECASE)
UNCOMMITTED = "0" * 40


class ProposalError(Exception):
    """A failure the user must act on; the message says what and where."""


# -- revisit hooks --------------------------------------------------------


REVISIT_LINE = re.compile(r"^\s*(?:-\s*)?\*\*Revisit:\*\*\s*(.*?)\s*$")
# The anchor runs to the last ")", so it may hold parentheses of its own. Trailing punctuation
# after it ends the sentence, not the date.
HOOK_DATE = re.compile(r"\bon or after\s+(.+?)(?:\s*\((.*)\))?[\s.;,]*$", re.IGNORECASE)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Hook:
    line: int
    location: str
    text: str
    condition: str
    date: str | None
    anchor: str | None


def hook_lines(lines: list[str]) -> dict[int, str]:
    """Map each revisit hook's line index to where it sits: the header or a settled decision.

    Only those two places hold live hooks. A Decision Log copy is history, and its date is
    never replaced, so it is not a hook.
    """
    spans = _sections(lines)
    header_end = min((start for start, _ in spans.values()), default=len(lines))
    settled = spans.get("Design Decisions (Settled)", (0, 0))
    found = {}
    for i, line in enumerate(lines):
        if not REVISIT_LINE.match(line):
            continue
        if i < header_end:
            found[i] = "header"
        elif settled[0] < i < settled[1]:
            found[i] = "settled"
    return found


def parse_hooks(lines: list[str]) -> list[Hook]:
    hooks = []
    for i, location in hook_lines(lines).items():
        text = REVISIT_LINE.match(lines[i]).group(1)
        when = anchor = None
        condition = text
        m = HOOK_DATE.search(text)
        if m:
            when, anchor = m.group(1).rstrip(".;,"), m.group(2)
            condition = text[: m.start()].rstrip(" ;,")
        hooks.append(Hook(i + 1, location, text, condition, when, anchor))
    return hooks


def hook_faults(hook: Hook) -> list[str]:
    """Return what is structurally wrong with a hook. A passed date is not a fault."""
    if hook.date is None:
        return [] if hook.condition else ["revisit hook has neither a condition nor a date"]
    faults = []
    if not ISO_DATE.match(hook.date):
        faults.append(f"revisit date {hook.date!r} is not YYYY-MM-DD")
    if not hook.anchor:
        faults.append("revisit date has no anchor in parentheses saying why that date")
    return faults


# -- parsing --------------------------------------------------------------


@dataclass
class Milestone:
    number: int
    status: str | None
    as_built: list[str] = field(default_factory=list)

    @property
    def replaced_by(self) -> tuple[str, int | None] | None:
        for line in self.as_built:
            m = REPLACED_BY.match(line)
            if m:
                return m.group(1), int(m.group(2)) if m.group(2) else None
        return None


@dataclass
class Proposal:
    id: str
    path: Path
    status: str
    milestones: dict[int, Milestone]
    era3: bool

    @property
    def history(self) -> bool:
        return self.status in NOT_LIVE and not self.era3


def _sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Map each `## ` heading to its [start, end) line span."""
    spans: dict[str, tuple[int, int]] = {}
    starts = [(i, line[3:].strip()) for i, line in enumerate(lines) if line.startswith("## ")]
    for n, (i, name) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        spans[name] = (i, end)
    return spans


def parse_proposal(path: Path, text: str | None = None) -> Proposal:
    lines = (path.read_text() if text is None else text).splitlines()
    status = ""
    for line in lines:
        m = PROPOSAL_STATUS.match(line)
        if m:
            status = m.group(1).strip().lower()
            break

    milestones: dict[int, Milestone] = {}
    start, end = _sections(lines).get("Milestones", (0, 0))
    current: Milestone | None = None
    in_as_built = False
    for line in lines[start:end]:
        heading = MILESTONE_HEADING.match(line)
        if heading:
            current = Milestone(int(heading.group(1)), None)
            milestones[current.number] = current
            in_as_built = False
            continue
        if current is None:
            continue
        if current.status is None:
            m = PROPOSAL_STATUS.match(line)
            if m:
                current.status = m.group(1).strip()
                continue
        if line.strip() == AS_BUILT:
            in_as_built = True
            continue
        if in_as_built:
            current.as_built.append(line)

    era3 = bool(milestones) and all(m.status is not None for m in milestones.values())
    match = PROPOSAL_FILE.match(path.name)
    return Proposal(match.group(1) if match else path.stem, path, status, milestones, era3)


def load_proposals(proposals_dir: Path) -> dict[str, Proposal]:
    if not proposals_dir.is_dir():
        raise ProposalError(f"{proposals_dir} is not a directory")
    proposals = {}
    for path in sorted(proposals_dir.iterdir()):
        if PROPOSAL_FILE.match(path.name):
            proposal = parse_proposal(path)
            proposals[proposal.id] = proposal
    return proposals


@dataclass
class Dependency:
    proposal: str
    milestone: int | None
    deployed: bool

    def __str__(self) -> str:
        ref = self.proposal + (f" M{self.milestone}" if self.milestone else "")
        return ref + (" (deployed)" if self.deployed else "")


@dataclass
class Row:
    index: int
    proposal: str
    first: int
    last: int
    depends_on: list[Dependency]
    note: str

    @property
    def label(self) -> str:
        if self.first == self.last:
            return f"{self.proposal} M{self.first}"
        return f"{self.proposal} M{self.first}-M{self.last}"

    def names(self, proposal: str, milestone: int) -> bool:
        return self.proposal == proposal and self.first <= milestone <= self.last


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def load_queue(proposals_dir: Path) -> list[Row]:
    path = proposals_dir / "queue.md"
    if not path.is_file():
        raise ProposalError(f"{path} does not exist. Scheduling a proposal creates it.")
    rows: list[Row] = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if cells[0] == "Milestones" or set(cells[0]) <= {"-", ":"}:
            continue
        if len(cells) != 3:
            raise ProposalError(f"{path}:{number}: a queue row has 3 cells, not {len(cells)}")
        m = ROW_RANGE.match(cells[0])
        if not m:
            raise ProposalError(f"{path}:{number}: cannot read milestone range {cells[0]!r}")
        first = int(m.group(2))
        last = int(m.group(3)) if m.group(3) else first
        deps = []
        for raw in re.split(r"\s*,\s*", cells[1]):
            if raw in ("", "None", "none"):
                continue
            d = DEPENDENCY.match(raw)
            if not d:
                raise ProposalError(f"{path}:{number}: cannot read dependency {raw!r}")
            deps.append(Dependency(d.group(1), int(d.group(2)) if d.group(2) else None, bool(d.group(3))))
        rows.append(Row(len(rows), m.group(1), first, last, deps, cells[2]))
    return rows


# -- check ----------------------------------------------------------------


INDEX_ROW = re.compile(r"^\[?([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)\]?(?:\(.*\))?$")


def _index_statuses(proposals_dir: Path) -> dict[str, tuple[Path, str]]:
    """Read each proposal's status from the index table, keyed by proposal ID."""
    found = [proposals_dir / name for name in ("index.md", "README.md") if (proposals_dir / name).is_file()]
    if len(found) > 1:
        raise ProposalError(f"{proposals_dir} has both index.md and README.md. Merge them into one index first.")
    statuses: dict[str, tuple[Path, str]] = {}
    for index in found:
        for line in index.read_text().splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = _cells(line)
            m = INDEX_ROW.match(cells[0])
            if m and len(cells) >= 2:
                statuses[m.group(1)] = (index, cells[-1].lower())
    return statuses


def check(proposals_dir: Path) -> list[dict[str, Any]]:
    proposals = load_proposals(proposals_dir)
    # Without a queue nothing is scheduled yet, so the checks that need one are skipped. A
    # queue that exists but cannot be read is an error, not an empty queue.
    rows = load_queue(proposals_dir) if (proposals_dir / "queue.md").is_file() else None
    findings: list[dict[str, Any]] = []

    def report(proposal: Proposal, problem: str, milestone: int | None = None) -> None:
        findings.append(
            {"proposal": proposal.id, "milestone": milestone, "file": str(proposal.path), "problem": problem}
        )

    def queued(pid: str, number: int) -> bool:
        return rows is None or any(row.names(pid, number) for row in rows)

    for pid, (index, listed) in _index_statuses(proposals_dir).items():
        p = proposals.get(pid)
        if p is not None and listed != p.status:
            report(p, f"{index.name} lists {listed!r}, but the proposal says {p.status!r}")

    for p in proposals.values():
        hooks = parse_hooks(p.path.read_text().splitlines())
        for hook in hooks:
            for fault in hook_faults(hook):
                report(p, f"line {hook.line}: {fault}")
        if p.status == "deferred" and not any(h.location == "header" for h in hooks):
            report(p, "deferred proposal has no **Revisit:** line in its header")

    for p in proposals.values():
        if p.history or p.status in STOPPED:
            continue
        if p.status == "accepted" and not p.era3:
            report(p, "accepted proposal whose milestones are not subsections with a **Status:** line")
            continue
        for m in p.milestones.values():
            if m.status not in MILESTONE_STATUSES:
                report(p, f"milestone status {m.status!r} is not one of {sorted(MILESTONE_STATUSES)}", m.number)
            if m.status in FINISHED and not m.as_built:
                report(p, f"{m.status} milestone has no As built block", m.number)
            if m.status == "DROPPED" and not any("Decision Log" in line for line in m.as_built):
                report(p, "DROPPED milestone does not link its Decision Log entry", m.number)
            target = m.replaced_by
            if target is not None and target[1] is not None:
                other = proposals.get(target[0])
                replacement = other.milestones.get(target[1]) if other else None
                ref = f"{target[0]} M{target[1]}"
                if replacement is None:
                    report(p, f"Replaced by names {ref}, which does not exist", m.number)
                elif replacement.status == "DROPPED":
                    report(p, f"Replaced by names {ref}, which is itself DROPPED", m.number)
                elif not queued(*target):
                    report(p, f"Replaced by names {ref}, which no queue row names", m.number)
            elif target is not None and target[0] not in proposals:
                report(p, f"Replaced by names {target[0]}, which does not exist", m.number)
        statuses = [m.status for m in p.milestones.values()]
        done = "DONE" in statuses
        all_finished = bool(statuses) and all(s in FINISHED for s in statuses)
        if p.status == "accepted" and all_finished and done:
            report(p, "every milestone is finished, so the proposal should be implemented")
        if p.status == "accepted" and statuses and all(s == "DROPPED" for s in statuses):
            report(p, "every milestone is DROPPED, so it can never be implemented. Retract or supersede it")
        if p.status == "implemented" and not (all_finished and done):
            report(p, "implemented, but not every milestone is finished with at least one DONE")
    return findings


# -- row ------------------------------------------------------------------


def _dependency_state(dep: Dependency, proposals: dict[str, Proposal], rows: list[Row]) -> tuple[str, str]:
    """Classify one dependency as met, unmet, confirm, or blocked, with the reason."""
    target = proposals.get(dep.proposal)
    if target is None:
        return "blocked", f"{dep.proposal} does not exist"
    if dep.milestone is None:
        if target.status == "implemented":
            return ("confirm", "confirm it runs in production") if dep.deployed else ("met", "implemented")
        if target.status != "accepted":
            return "blocked", f"{dep.proposal} is {target.status or 'missing a status'}"
        unfinished = [n for n, m in target.milestones.items() if m.status not in FINISHED]
        if not any(row.names(dep.proposal, n) for row in rows for n in unfinished):
            return "blocked", f"{dep.proposal} has no queue row for its unfinished milestones"
        return "unmet", f"{dep.proposal} is not implemented yet"

    if target.history and target.status == "implemented":
        return ("confirm", "confirm it runs in production") if dep.deployed else ("met", "implemented history")
    milestone = target.milestones.get(dep.milestone)
    if milestone is None:
        return "blocked", f"{dep.proposal} has no M{dep.milestone}"
    if milestone.status == "DONE":
        return ("confirm", "confirm it runs in production") if dep.deployed else ("met", "DONE")
    if milestone.status == "DROPPED":
        replacement = milestone.replaced_by
        hint = f"; wait on {replacement[0]}" + (f" M{replacement[1]}" if replacement[1] else "") if replacement else ""
        return "blocked", f"{dep} is DROPPED{hint}"
    if target.status not in ("accepted", "implemented"):
        return "blocked", f"{dep.proposal} is {target.status}"
    if not any(row.names(dep.proposal, dep.milestone) for row in rows):
        return "blocked", f"{dep.proposal} M{dep.milestone} is in no queue row"
    return "unmet", f"{dep.proposal} M{dep.milestone} is {milestone.status}"


def row_info(proposals_dir: Path, proposal_id: str, milestone: int | None) -> dict[str, Any]:
    proposals = load_proposals(proposals_dir)
    rows = load_queue(proposals_dir)
    proposal = proposals.get(proposal_id)
    if proposal is None:
        raise ProposalError(f"no proposal {proposal_id} in {proposals_dir}")

    def finished(row: Row) -> bool:
        return all(
            proposal.milestones.get(n) is not None and proposal.milestones[n].status in FINISHED
            for n in range(row.first, row.last + 1)
        )

    own = [row for row in rows if row.proposal == proposal_id]
    if milestone is None:
        target = next((row for row in own if not finished(row)), None)
        if target is None:
            raise ProposalError(f"{proposal_id} has no unfinished queue row")
        milestone = next(
            n for n in range(target.first, target.last + 1)
            if proposal.milestones.get(n) is None or proposal.milestones[n].status not in FINISHED
        )
    else:
        target = next((row for row in own if row.names(proposal_id, milestone)), None)
        if target is None:
            raise ProposalError(f"{proposal_id} M{milestone} is in no queue row, so it is not scheduled")

    entry = proposal.milestones.get(milestone)
    if entry is None:
        raise ProposalError(f"{proposal_id} has no M{milestone}")
    deps = []
    for dep in target.depends_on:
        state, reason = _dependency_state(dep, proposals, rows)
        deps.append({"dependency": str(dep), "state": state, "reason": reason})
    earlier = [row.label for row in own if row.index < target.index and not finished(row)]
    pending_before = [
        f"{proposal_id} M{n}" for n in range(target.first, milestone)
        if proposal.milestones.get(n) is None or proposal.milestones[n].status not in FINISHED
    ]
    ready = (
        proposal.status == "accepted"
        and entry.status not in FINISHED
        and not earlier
        and not pending_before
        and all(d["state"] == "met" for d in deps)
    )
    return {
        "proposal": proposal_id,
        "proposal_status": proposal.status,
        "proposal_file": str(proposal.path),
        "milestone": milestone,
        "milestone_status": entry.status,
        "row": target.label,
        "row_note": target.note,
        "last_in_row": milestone == target.last,
        "last_unfinished_in_proposal": all(
            m.status in FINISHED for n, m in proposal.milestones.items() if n != milestone
        ),
        "dependencies": deps,
        "earlier_rows_unfinished": earlier,
        "earlier_milestones_in_row_unfinished": pending_before,
        "ready": ready,
    }


# -- freeze ---------------------------------------------------------------


def _git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise ProposalError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout if proc.returncode == 0 else ""


def _status_at(repo: Path, commit: str, rel: str) -> str:
    text = _git(repo, "show", f"{commit}:{rel}", check=False)
    for line in text.splitlines():
        m = PROPOSAL_STATUS.match(line)
        if m:
            return m.group(1).strip().lower()
    return ""


def freeze_point(repo: Path, rel: str) -> tuple[str, str, str] | None:
    """Return the freeze base: a commit, the file's path there, and how it was found.

    The base is the commit that wrote `implemented` ("flip"). A proposal imported already
    implemented uses its first commit ("first-commit"). None means no commit ever froze it.
    A proposal marked implemented only in the working tree is not frozen yet, since its
    uncommitted edits are the work that finishes it.
    """
    log = _git(repo, "log", "--follow", "--first-parent", "--format=%x00%H", "--name-only", "--", rel)
    history: list[tuple[str, str]] = []
    for chunk in log.split("\x00")[1:]:
        parts = [p for p in chunk.split("\n") if p]
        if len(parts) >= 2:
            history.append((parts[0], parts[-1]))
    if not history:
        return None
    for n, (commit, path) in enumerate(history[:-1]):
        if _status_at(repo, commit, path) != "implemented":
            continue
        if _status_at(repo, f"{commit}^", history[n + 1][1]) != "implemented":
            return commit, path, "flip"
    first_commit, first_path = history[-1]
    if _status_at(repo, first_commit, first_path) == "implemented":
        return first_commit, first_path, "first-commit"
    return None


def _regions(lines: list[str]) -> list[str]:
    """Label each line status, revisit, meta, as-built, decision-log, or text.

    Only the header's metadata counts. A milestone's status line is text, since the freeze
    allows no milestone status change.
    """
    labels = ["text"] * len(lines)
    spans = _sections(lines)
    header_end = min((start for start, _ in spans.values()), default=len(lines))
    log_start, log_end = spans.get("Decision Log", (0, 0))
    for i in range(log_start + 1, log_end):
        labels[i] = "decision-log"
    hooks = hook_lines(lines)
    in_as_built = False
    for i, line in enumerate(lines):
        if line.startswith("#"):
            in_as_built = False
        meta = META_LINE.match(line) if i < header_end else None
        if i in hooks:
            labels[i] = "revisit"
        elif meta:
            labels[i] = "status" if meta.group(1).lower() == "status" else "meta"
        elif line.strip() == AS_BUILT:
            in_as_built = True
            labels[i] = "as-built"
        elif in_as_built:
            labels[i] = "as-built"
    return labels


def _link_only(old: list[str], new: list[str]) -> bool:
    if len(old) != len(new):
        return False
    return all(LINK_TARGET.sub("]()", a) == LINK_TARGET.sub("]()", b) for a, b in zip(old, new))


def _marker_only(tag: str, old: list[str], new: list[str]) -> bool:
    """Whether the change only adds the exact partial supersession marker.

    The marker is inserted as its own line, or appended to an existing line with nothing
    after it. Any other text beside it is a frozen edit.
    """
    if tag == "insert":
        return all(not line.strip() or PARTIAL_SUPERSESSION.fullmatch(line.strip()) for line in new)
    if tag != "replace" or len(old) != len(new):
        return False
    for a, b in zip(old, new):
        if a == b:
            continue
        m = PARTIAL_SUPERSESSION.search(b)
        if not m or m.end() != len(b.rstrip()) or b[: m.start()].rstrip() != a.rstrip():
            return False
    return True


def _status_allowed(old: list[str], new: list[str]) -> bool:
    """Whether a header status change is one the lifecycle allows from `implemented`."""
    values = [m.group(1).strip().lower() for m in map(PROPOSAL_STATUS.match, new) if m]
    return len(values) == 1 and values[0] in FROZEN_STATUSES and any(PROPOSAL_STATUS.match(a) for a in old)


def _entries(lines: list[str]) -> list[str]:
    """Join a Decision Log hunk's lines into its list entries."""
    entries: list[str] = []
    for line in lines:
        if line.startswith("- ") or not entries:
            entries.append(line)
        else:
            entries[-1] += " " + line.strip()
    return [e for e in entries if e.strip()]


def _blame(repo: Path, rel: str) -> list[str]:
    """Return the commit behind each working-tree line, with zeros for uncommitted lines."""
    out = _git(repo, "blame", "--porcelain", "--", rel, check=False)
    commits: list[str] = []
    for line in out.splitlines():
        m = re.match(r"^([0-9a-f]{40}) \d+ \d+", line)
        if m:
            commits.append(m.group(1))
    return commits


def _removers(repo: Path, rel: str, base: str, head_text: str, removed: list[str]) -> set[str]:
    """Return the commits that removed these lines since the base, or zeros when uncommitted.

    Blame sees only lines that exist, so a removal is traced through history instead.
    """
    if "\n".join(removed) in head_text:
        return {UNCOMMITTED}
    probe = next((line for line in removed if line.strip()), "")
    if not probe:
        return set()
    out = _git(repo, "log", "--follow", "--format=%H", "-S", probe, f"{base}..HEAD", "--", rel, check=False)
    return set(out.split())


def _hunk_labels(lines: list[str], labels: list[str], start: int, end: int) -> set[str]:
    """Return the regions a hunk's lines fall in. Blank lines carry no meaning, so they never count."""
    return {labels[i] for i in range(start, end) if lines[i].strip()}


def _origin(authors: set[str], row: set[str]) -> str:
    """Name who made a hunk. Uncommitted edits count as the run's own."""
    if not authors:
        return "unknown"
    return "row" if authors <= row | {UNCOMMITTED} else "other"


def freeze(proposals_dir: Path, row_commits: list[str]) -> list[dict[str, Any]]:
    proposals_dir = proposals_dir.resolve()
    repo = Path(_git(proposals_dir, "rev-parse", "--show-toplevel").strip())
    row = {_git(repo, "rev-parse", c).strip() for c in row_commits}
    results: list[dict[str, Any]] = []
    for p in load_proposals(proposals_dir).values():
        # History was edited under its own era's rules, so the freeze starts with era 3. Any
        # proposal a commit ever froze stays frozen, whatever its status says now.
        if p.history or not p.era3:
            continue
        rel = str(p.path.resolve().relative_to(repo))
        point = freeze_point(repo, rel)
        if point is None:
            continue
        commit, old_rel, found = point
        old = _git(repo, "show", f"{commit}:{old_rel}").splitlines()
        new = p.path.read_text().splitlines()
        head_text = _git(repo, "show", f"HEAD:{rel}", check=False)
        old_labels, new_labels = _regions(old), _regions(new)
        blame = _blame(repo, rel)
        opcodes = [op for op in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes() if op[0] != "equal"]

        audits = corrections = 0
        log_inserts: dict[int, bool] = {}
        hunk_labels = [
            _hunk_labels(old, old_labels, i1, i2) | _hunk_labels(new, new_labels, j1, j2)
            for _, i1, i2, j1, j2 in opcodes
        ]
        for n, (tag, i1, i2, j1, j2) in enumerate(opcodes):
            labels = hunk_labels[n]
            if tag == "insert" and labels == {"decision-log"}:
                entries = _entries(new[j1:j2])
                audits += sum(1 for e in entries if AUDIT_ENTRY.search(e))
                corrections += sum(1 for e in entries if CORRECTION_ENTRY.search(e))
                log_inserts[n] = all(AUDIT_ENTRY.search(e) or CORRECTION_ENTRY.search(e) for e in entries)

        hunks = []
        for n, (tag, i1, i2, j1, j2) in enumerate(opcodes):
            old_part, new_part = old[i1:i2], new[j1:j2]
            labels = hunk_labels[n]
            kind = None
            if not labels:
                continue
            if n in log_inserts:
                if log_inserts[n]:
                    continue
                kind = "decision-log entry that records neither a revisit audit nor a correction of fact"
            elif "status" in labels:
                if labels <= {"status", "meta"} and _status_allowed(old_part, new_part):
                    continue
                kind = "status change the lifecycle does not allow from implemented"
            elif "revisit" in labels:
                if labels <= {"revisit", "meta"} and audits:
                    continue
                kind = "revisit hook changed without a revisit audit in the Decision Log"
            elif (
                labels <= {"meta", "as-built"}
                or _link_only(old_part, new_part)
                or _marker_only(tag, old_part, new_part)
            ):
                continue
            authors = {blame[j] for j in range(j1, j2) if j < len(blame)}
            if old_part:
                authors |= _removers(repo, rel, commit, head_text, old_part)
            hunks.append({
                "kind": kind or "changed text outside the allowed edits",
                "old_lines": [i1 + 1, i2],
                "new_lines": [j1 + 1, j2],
                "removed": old_part,
                "added": new_part,
                "origin": _origin(authors, row),
            })
        if hunks:
            results.append({
                "proposal": p.id,
                "file": str(p.path),
                "freeze_commit": commit,
                "freeze_base": found,
                "corrections_logged": corrections,
                "hunks": hunks,
            })
    return results


# -- hooks ----------------------------------------------------------------


def hooks(proposals_dir: Path, today: str, passed_only: bool) -> list[dict[str, Any]]:
    """List every revisit hook, passed dates first. A hook is passed on or after its date."""
    listed = []
    for p in load_proposals(proposals_dir).values():
        for hook in parse_hooks(p.path.read_text().splitlines()):
            readable = hook.date is not None and ISO_DATE.match(hook.date) is not None
            passed = readable and hook.date <= today
            if passed_only and not passed:
                continue
            listed.append({
                "proposal": p.id,
                "status": p.status,
                "file": str(p.path),
                "line": hook.line,
                "location": hook.location,
                "condition": hook.condition or None,
                "date": hook.date,
                "anchor": hook.anchor,
                "passed": passed,
            })
    listed.sort(key=lambda h: (not h["passed"], h["date"] or "9999", h["proposal"], h["line"]))
    return listed


# -- progress -------------------------------------------------------------


def progress(proposals_dir: Path, today: str) -> dict[str, Any]:
    """Join each queue row with its milestones' status: what is done, what is ready, what is held."""
    proposals = load_proposals(proposals_dir)
    rows = load_queue(proposals_dir)
    report: dict[str, Any] = {
        "done": [], "ready": [], "held": [], "blocked": [], "hooks": hooks(proposals_dir, today, False),
    }
    for row in rows:
        p = proposals.get(row.proposal)
        numbers = range(row.first, row.last + 1)
        statuses = {n: p.milestones[n].status if p and n in p.milestones else None for n in numbers}
        entry: dict[str, Any] = {
            "row": row.label,
            "note": row.note,
            "done": sum(1 for s in statuses.values() if s == "DONE"),
            "dropped": sum(1 for s in statuses.values() if s == "DROPPED"),
            "total": len(statuses),
        }
        if all(s in FINISHED for s in statuses.values()):
            report["done"].append(entry)
            continue
        entry["next"] = next(f"{row.proposal} M{n}" for n, s in statuses.items() if s not in FINISHED)
        # Blocked reasons need the user. Held reasons clear once other work finishes.
        blocked, held = [], []
        if p is None:
            blocked.append(f"{row.proposal} does not exist")
        else:
            if p.status != "accepted":
                blocked.append(f"{row.proposal} is {p.status}")
            blocked += [f"{row.proposal} has no M{n}" for n, s in statuses.items() if s is None]
        for earlier in rows[: row.index]:
            if earlier.proposal == row.proposal and any(
                p is None or p.milestones.get(n) is None or p.milestones[n].status not in FINISHED
                for n in range(earlier.first, earlier.last + 1)
            ):
                held.append(f"waits on its earlier row {earlier.label}")
        for dep in row.depends_on:
            state, reason = _dependency_state(dep, proposals, rows)
            if state == "blocked":
                blocked.append(f"{dep}: {reason}")
            elif state != "met":
                held.append(f"{dep}: {reason}")
        if blocked:
            entry["blocked"] = blocked + held
            report["blocked"].append(entry)
        elif held:
            entry["held"] = held
            report["held"].append(entry)
        else:
            report["ready"].append(entry)
    return report


def render_progress(report: dict[str, Any]) -> str:
    def tally(entry: dict[str, Any]) -> str:
        text = f"{entry['done']}/{entry['total'] - entry['dropped']} done"
        return text + (f", {entry['dropped']} dropped" if entry["dropped"] else "")

    lines = ["Done"]
    lines += [f"  {e['row']}  {tally(e)}" for e in report["done"]] or ["  (none)"]
    lines.append("Ready, in queue order")
    lines += [f"  {e['row']}  {tally(e)}, next {e['next']}" for e in report["ready"]] or ["  (none)"]
    for title, key in (("Held, until other work finishes", "held"), ("Blocked, needs the user", "blocked")):
        lines.append(title)
        for e in report[key]:
            lines.append(f"  {e['row']}  {tally(e)}, next {e['next']}")
            lines += [f"    - {reason}" for reason in e[key]]
        if not report[key]:
            lines.append("  (none)")
    lines.append("Revisit hooks")
    for h in report["hooks"]:
        when = f"on or after {h['date']}" if h["date"] else "no date"
        mark = "PASSED " if h["passed"] else ""
        lines.append(f"  {mark}{h['proposal']} ({h['status']}, {h['location']}): {h['condition'] or ''}; {when}")
    if not report["hooks"]:
        lines.append("  (none)")
    return "\n".join(lines)


def notice(proposals_dir: Path, today: str) -> str:
    """One line naming how many hooks have passed, or nothing when none has."""
    passed = hooks(proposals_dir, today, True)
    if not passed:
        return ""
    names = ", ".join(sorted({h["proposal"] for h in passed}))
    noun = "hook has" if len(passed) == 1 else "hooks have"
    return (
        f"{len(passed)} revisit {noun} passed in {proposals_dir} ({names}). Each needs an audit the user decides: "
        f"act, extend with a reason, or abandon. List them with: python3 {shlex.quote(str(Path(__file__).resolve()))} "
        f"hooks --passed --proposals-dir {shlex.quote(str(proposals_dir))}"
    )


# -- cli ------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "row", "freeze", "hooks", "progress", "notice"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--proposals-dir", type=Path, required=True)
        if name == "row":
            cmd.add_argument("proposal")
            cmd.add_argument("milestone", nargs="?")
        if name == "freeze":
            cmd.add_argument("--row-commit", action="append", default=[])
        if name in ("hooks", "progress", "notice"):
            cmd.add_argument("--today", default=date.today().isoformat(), help="YYYY-MM-DD; defaults to today")
        if name == "hooks":
            cmd.add_argument("--passed", action="store_true", help="list only hooks whose date has passed")
        if name == "progress":
            cmd.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    try:
        if getattr(args, "today", None) is not None and not ISO_DATE.match(args.today):
            raise ProposalError(f"--today {args.today!r} is not YYYY-MM-DD")
        if args.command == "check":
            result: Any = check(args.proposals_dir)
        elif args.command == "hooks":
            result = hooks(args.proposals_dir, args.today, args.passed)
        elif args.command in ("progress", "notice"):
            # These two print text for a person to read, so they skip the JSON below.
            if args.command == "notice":
                text = notice(args.proposals_dir, args.today)
            else:
                report = progress(args.proposals_dir, args.today)
                text = json.dumps(report, indent=2) if args.json else render_progress(report)
            if text:
                print(text)
            return 0
        elif args.command == "row":
            milestone = None
            if args.milestone is not None:
                m = re.fullmatch(r"M?(\d+)", args.milestone)
                if not m:
                    raise ProposalError(f"cannot read milestone {args.milestone!r}; write it as M3")
                milestone = int(m.group(1))
            result = row_info(args.proposals_dir, args.proposal, milestone)
        else:
            result = freeze(args.proposals_dir, args.row_commit)
    except ProposalError as err:
        print(f"proposals.py: {err}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
