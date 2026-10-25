#!/usr/bin/env python3
"""Read era 3 proposals and the queue, and run the checks the standard defines.

    python3 proposals.py check --proposals-dir DIR [--proposals-for PREFIX=PATH ...]
    python3 proposals.py row --proposals-dir DIR [--proposals-for PREFIX=PATH ...] PROJ-NNN [MN]
    python3 proposals.py freeze --proposals-dir DIR [--row-commit SHA ...]
    python3 proposals.py hooks --proposals-dir DIR [--passed] [--today YYYY-MM-DD]
    python3 proposals.py progress --proposals-dir DIR [--proposals-for PREFIX=PATH ...] [--json]
        [--today YYYY-MM-DD]
    python3 proposals.py notice --proposals-dir DIR [--today YYYY-MM-DD]
    python3 proposals.py next --proposals-dir DIR [--proposals-for PREFIX=PATH ...] [--count N]
        [--hold PROJ-NNN ...]
    python3 proposals.py candidates --proposals-dir DIR [--proposals-for PREFIX=PATH ...]

The rules live in project-management/proposals.md and plans.md. `check` reports
milestone status and hook structure the standard rejects. `row` finds the queue
row that names a milestone, or a proposal's next unfinished one, and says
whether it is ready. `freeze` reports edits to implemented proposals that the
freeze does not allow. `hooks` lists every revisit hook, passed dates first.
`progress` reports the queue as done, ready, held, awaiting-deploy, and blocked
rows, with the hooks.
`notice` prints one line when any hook has passed, and nothing otherwise.
`next` picks the next N rows a `/work-queue` run can take, in queue order.
`candidates` recommends accepted proposals to schedule, in tiers.

The queue is DIR/queue.md, which holds unfinished rows, and DIR/history.md, which holds
finished rows in the order they were built. Every command reads both as one queue.

DIR is the proposals directory, which may sit in a symlinked specs repo. Results
are JSON on stdout. Errors go to stderr with exit status 1.

A dependency on another project's proposal resolves through the `## Other proposals`
entries in DIR/queue.md. `--proposals-for PREFIX=PATH` adds or overrides one entry for a
single run, with PATH relative to the current directory. A dependency whose prefix has no
entry, or whose entry does not lead to that project's proposals, is `unresolved`. It holds
the row and never blocks it.
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
# A `(merge after deployed)` marker gates the whole row on another deploy unit's deployment.
# `(deployed)` is its legacy spelling. It still gates the row, and the check asks for it to be
# reclassified.
DEPENDENCY = re.compile(
    r"^([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)(?:\s+M(\d+))?(?:\s+\((deployed|merge after deployed)\))?$"
)
# A milestone whose checks read production state that another deploy unit's deployment
# produces. Only that milestone waits for the deployment, not its row.
LIVE_AFTER = re.compile(r"^\*\*Live after:\*\*\s*(.*?)\s*$")
LIVE_AFTER_TARGET = re.compile(r"^([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)(?:\s+M(\d+))?\s+deployed$")
META_LINE = re.compile(r"^\*\*(Status|Updated|Revisit):\*\*", re.IGNORECASE)
PARTIAL_SUPERSESSION = re.compile(r"Superseded in part by [A-Z0-9]*[A-Z][A-Z0-9]*-\d+; see Decision Log\.")
FROZEN_STATUSES = {"implemented", "superseded"}
LINK_TARGET = re.compile(r"\]\([^)]*\)")
AUDIT_ENTRY = re.compile(r"\brevisit\b", re.IGNORECASE)
CORRECTION_ENTRY = re.compile(r"\bcorrection of fact\b", re.IGNORECASE)
SUPERSESSION_ENTRY = re.compile(r"\bsuperseded (?:in part )?by [A-Z0-9]*[A-Z][A-Z0-9]*-\d+", re.IGNORECASE)
UNCOMMITTED = "0" * 40
QUEUE_FILE = "queue.md"
HISTORY_FILE = "history.md"


class ProposalError(Exception):
    """A failure the user must act on; the message says what and where."""


# -- revisit hooks --------------------------------------------------------


REVISIT_LINE = re.compile(r"^\s*(?:-\s*)?\*\*Revisit:\*\*\s*(.*?)\s*$")
# A line that starts something new, and so ends a hook that wraps: a heading, a bold field such
# as the header's next metadata line, or a list item.
HOOK_STOP = re.compile(r"^\s*(?:#|\*\*[^*]+:\*\*|(?:[-*+]|\d+\.)\s)")
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


def _hook_end(lines: list[str], start: int) -> int:
    """Return the index past a hook's last line. A hook wraps until a blank line, heading, field, or list item."""
    end = start + 1
    while end < len(lines) and lines[end].strip() and not HOOK_STOP.match(lines[end]):
        end += 1
    return end


def hook_spans(lines: list[str]) -> dict[int, tuple[int, str]]:
    """Map each revisit hook's first line index to its end and where it sits: the header or a settled decision.

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
            found[i] = (_hook_end(lines, i), "header")
        elif settled[0] < i < settled[1]:
            found[i] = (_hook_end(lines, i), "settled")
    return found


def parse_hooks(lines: list[str]) -> list[Hook]:
    hooks = []
    for i, (end, location) in hook_spans(lines).items():
        text = " ".join([REVISIT_LINE.match(lines[i]).group(1), *(line.strip() for line in lines[i + 1 : end])]).strip()
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
class Dependency:
    proposal: str
    milestone: int | None
    deployed: bool
    legacy: bool = False
    live: bool = False

    @property
    def ref(self) -> str:
        return self.proposal + (f" M{self.milestone}" if self.milestone else "")

    def __str__(self) -> str:
        if self.live:
            return self.ref + " deployed"
        if self.deployed:
            return self.ref + (" (deployed)" if self.legacy else " (merge after deployed)")
        return self.ref


@dataclass
class Milestone:
    number: int
    status: str | None
    as_built: list[str] = field(default_factory=list)
    live_after: Dependency | None = None
    live_after_text: str | None = None

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
        live = LIVE_AFTER.match(line) if not in_as_built else None
        if live:
            current.live_after_text = live.group(1)
            target = LIVE_AFTER_TARGET.match(live.group(1))
            if target:
                number = int(target.group(2)) if target.group(2) else None
                current.live_after = Dependency(target.group(1), number, True, live=True)
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
class Row:
    index: int
    proposal: str
    first: int
    last: int
    depends_on: list[Dependency]
    note: str
    source: str = QUEUE_FILE

    @property
    def label(self) -> str:
        if self.first == self.last:
            return f"{self.proposal} M{self.first}"
        return f"{self.proposal} M{self.first}-M{self.last}"

    def names(self, proposal: str, milestone: int) -> bool:
        return self.proposal == proposal and self.first <= milestone <= self.last


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def has_queue(proposals_dir: Path) -> bool:
    return (proposals_dir / QUEUE_FILE).is_file() or (proposals_dir / HISTORY_FILE).is_file()


def load_queue(proposals_dir: Path) -> list[Row]:
    """Read history.md's finished rows, then queue.md's unfinished ones, as one queue.

    History comes first, so the merged list is in build order, and a row's index still
    compares it with every row of the same proposal.
    """
    path = proposals_dir / QUEUE_FILE
    if not path.is_file():
        raise ProposalError(f"{path} does not exist. Scheduling a proposal creates it.")
    history = proposals_dir / HISTORY_FILE
    rows = _load_rows(history, 0) if history.is_file() else []
    return rows + _load_rows(path, len(rows))


def _load_rows(path: Path, start: int) -> list[Row]:
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
            number = int(d.group(2)) if d.group(2) else None
            deps.append(Dependency(d.group(1), number, bool(d.group(3)), legacy=d.group(3) == "deployed"))
        rows.append(Row(start + len(rows), m.group(1), first, last, deps, cells[2], path.name))
    return rows


# -- other projects -------------------------------------------------------


OTHER_PROPOSALS = "Other proposals"
OTHER_BULLET = re.compile(r"^\s*[-*]\s")
OTHER_ENTRY = re.compile(r"^\s*[-*]\s+([A-Z0-9]*[A-Z][A-Z0-9]*):\s+`?([^`]+?)`?\s*$")
PREFIX = re.compile(r"^[A-Z0-9]*[A-Z][A-Z0-9]*$")


def _prefix(proposal_id: str) -> str:
    return proposal_id.rsplit("-", 1)[0]


@dataclass
class Location:
    """Where another project's proposals live, and the queue.md line or flag that says so."""

    prefix: str
    path: Path
    source: str
    file: Path | None = None


def load_locations(proposals_dir: Path) -> dict[str, Location]:
    """Read the `## Other proposals` entries in queue.md, keyed by prefix.

    A relative path resolves against the directory queue.md really sits in. When the specs
    directory is a symlink, `..` climbs from the link's target, so every checkout that links
    the same specs repo resolves an entry to the same place.
    """
    path = proposals_dir / "queue.md"
    if not path.is_file():
        return {}
    lines = path.read_text().splitlines()
    start, end = _sections(lines).get(OTHER_PROPOSALS, (0, 0))
    base = proposals_dir.resolve()
    found: dict[str, Location] = {}
    for i in range(start + 1, end):
        if not OTHER_BULLET.match(lines[i]):
            continue
        m = OTHER_ENTRY.match(lines[i])
        if not m:
            raise ProposalError(
                f"{path}:{i + 1}: cannot read {lines[i].strip()!r}; write - PREFIX: path/to/proposals"
            )
        prefix, written = m.groups()
        if prefix in found:
            raise ProposalError(f"{path}:{i + 1}: {prefix} is listed twice under ## {OTHER_PROPOSALS}")
        found[prefix] = Location(prefix, (base / written).resolve(), f"queue.md line {i + 1}", path)
    return found


def parse_overrides(values: list[str]) -> dict[str, Location]:
    """Read `--proposals-for PREFIX=PATH` flags. A relative PATH resolves against the current directory."""
    found: dict[str, Location] = {}
    for raw in values:
        prefix, sep, written = raw.partition("=")
        if not sep or not PREFIX.match(prefix) or not written:
            raise ProposalError(
                f"--proposals-for {raw!r}: write PREFIX=PATH, as in OTHER=../other/docs/proposals"
            )
        if prefix in found:
            raise ProposalError(f"--proposals-for names {prefix} twice")
        found[prefix] = Location(prefix, Path(written).resolve(), "--proposals-for")
    return found


@dataclass
class Project:
    """One proposals directory: its proposals and its queue rows."""

    proposals_dir: Path
    proposals: dict[str, Proposal]
    rows: list[Row]


def _load_other(location: Location) -> Project | str:
    """Load the project an entry names, or say why it cannot be loaded.

    A sibling's queue is read only for its rows, so its own entries are never followed.
    """
    where = f"the {location.prefix} entry ({location.source}) points at {location.path}"
    if not location.path.is_dir():
        return f"{where}, which is not a directory"
    try:
        proposals = load_proposals(location.path)
        rows = load_queue(location.path) if has_queue(location.path) else []
    except ProposalError as err:
        return f"{where}, which cannot be read: {err}"
    if not any(_prefix(pid) == location.prefix for pid in proposals):
        return f"{where}, which holds no {location.prefix} proposals"
    return Project(location.path, proposals, rows)


class Workspace:
    """This project's proposals and queue, plus the other projects its entries name.

    An ID found in this project is local, whatever its prefix. Any other ID resolves through
    the entry for its prefix. An ID missing from a prefix this project uses, with no entry,
    does not exist. Every other ID is unresolved.
    """

    def __init__(self, local: Project, locations: dict[str, Location]) -> None:
        self.local = local
        self.locations = locations
        self.prefixes = {_prefix(pid) for pid in local.proposals}
        self.prefixes |= {_prefix(row.proposal) for row in local.rows}
        self._others: dict[str, Project | str] = {}

    def other(self, prefix: str) -> Project | str:
        if prefix not in self._others:
            self._others[prefix] = _load_other(self.locations[prefix])
        return self._others[prefix]

    def find(self, proposal_id: str) -> tuple[Project | None, str]:
        """Return the project that should hold an ID, or None with the reason it is unresolved."""
        if proposal_id in self.local.proposals:
            return self.local, ""
        prefix = _prefix(proposal_id)
        if prefix in self.locations:
            other = self.other(prefix)
            return (other, "") if isinstance(other, Project) else (None, other)
        if prefix in self.prefixes:
            return self.local, ""
        return None, (
            f"no proposals directory is listed for {prefix}. Add `- {prefix}: <path>` under "
            f"`## {OTHER_PROPOSALS}` in queue.md, or pass --proposals-for {prefix}=<path>"
        )

    def where(self, project: Project) -> str:
        """A suffix naming another project's directory in a reason. Local reasons need none."""
        return "" if project is self.local else f" in {project.proposals_dir}"


def workspace(
    proposals_dir: Path, overrides: dict[str, Location] | None = None, queue: bool = True
) -> Workspace:
    """Load this project and its entries. With `queue` false, a missing queue reads as no rows."""
    proposals = load_proposals(proposals_dir)
    rows = load_queue(proposals_dir) if queue or has_queue(proposals_dir) else []
    locations = {**load_locations(proposals_dir), **(overrides or {})}
    return Workspace(Project(proposals_dir, proposals, rows), locations)


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


def check(proposals_dir: Path, overrides: dict[str, Location] | None = None) -> list[dict[str, Any]]:
    # Without a queue nothing is scheduled yet, so the checks that need one are skipped. A
    # queue that exists but cannot be read is an error, not an empty queue.
    ws = workspace(proposals_dir, overrides, queue=False)
    proposals = ws.local.proposals
    rows = ws.local.rows if has_queue(proposals_dir) else None
    findings: list[dict[str, Any]] = []

    def report(proposal: Proposal, problem: str, milestone: int | None = None) -> None:
        findings.append(
            {"proposal": proposal.id, "milestone": milestone, "file": str(proposal.path), "problem": problem}
        )

    def queued(project: Project, pid: str, number: int) -> bool:
        if project is ws.local and rows is None:
            return True
        return any(row.names(pid, number) for row in project.rows)

    for location in ws.locations.values():
        other = ws.other(location.prefix)
        if isinstance(other, str):
            findings.append({
                "proposal": None, "milestone": None, "file": str(location.file) if location.file else None,
                "problem": f"## {OTHER_PROPOSALS}: {other}",
            })

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
            # A DROPPED milestone may never have been scheduled, but DONE work always was. A DONE
            # milestone in no row most likely lost its row on the way to history.md.
            if m.status == "DONE" and not queued(ws.local, p.id, m.number):
                report(p, f"DONE milestone is in no queue row. Its finished row belongs in {HISTORY_FILE}", m.number)
            if m.status == "DROPPED" and not any("Decision Log" in line for line in m.as_built):
                report(p, "DROPPED milestone does not link its Decision Log entry", m.number)
            target = m.replaced_by
            project, unresolved = ws.find(target[0]) if target is not None else (None, "")
            if target is not None and project is None:
                ref = target[0] + (f" M{target[1]}" if target[1] is not None else "")
                report(p, f"Replaced by names {ref}, which is unresolved: {unresolved}", m.number)
            elif target is not None and target[1] is not None:
                other = project.proposals.get(target[0])
                replacement = other.milestones.get(target[1]) if other else None
                ref = f"{target[0]} M{target[1]}"
                if replacement is None:
                    report(p, f"Replaced by names {ref}, which does not exist{ws.where(project)}", m.number)
                elif replacement.status == "DROPPED":
                    report(p, f"Replaced by names {ref}, which is itself DROPPED", m.number)
                elif not queued(project, *target):
                    report(p, f"Replaced by names {ref}, which no queue row names{ws.where(project)}", m.number)
            elif target is not None and target[0] not in project.proposals:
                report(p, f"Replaced by names {target[0]}, which does not exist{ws.where(project)}", m.number)

            live = m.live_after
            project, unresolved = ws.find(live.proposal) if live is not None else (None, "")
            if m.live_after_text is not None and live is None:
                report(p, f"cannot read **Live after:** {m.live_after_text!r}; write PROJ-NNN MN deployed", m.number)
            elif live is not None and m.status not in FINISHED and project is None:
                report(p, f"Live after names {live.ref}, which is unresolved: {unresolved}", m.number)
            elif live is not None and m.status not in FINISHED:
                other = project.proposals.get(live.proposal)
                awaited = other.milestones.get(live.milestone) if other and live.milestone else None
                if other is None:
                    missing = f"{live.proposal}, which does not exist{ws.where(project)}"
                    report(p, f"Live after names {missing}", m.number)
                elif live.milestone is not None and awaited is None and not other.history:
                    report(p, f"Live after names {live.ref}, which does not exist{ws.where(project)}", m.number)
                elif awaited is not None and awaited.status == "DROPPED":
                    report(p, f"Live after names {live.ref}, which is DROPPED", m.number)
        statuses = [m.status for m in p.milestones.values()]
        done = "DONE" in statuses
        all_finished = bool(statuses) and all(s in FINISHED for s in statuses)
        if p.status == "accepted" and all_finished and done:
            report(p, "every milestone is finished, so the proposal should be implemented")
        if p.status == "accepted" and statuses and all(s == "DROPPED" for s in statuses):
            report(p, "every milestone is DROPPED, so it can never be implemented. Retract or supersede it")
        if p.status == "implemented" and not (all_finished and done):
            report(p, "implemented, but not every milestone is finished with at least one DONE")
    if rows is not None:
        findings += _queue_findings(ws)
    return findings


def _queue_findings(ws: Workspace) -> list[dict[str, Any]]:
    """Report the queue rules in plans.md "The Queue File" that hold mechanically."""
    rows, proposals = ws.local.rows, ws.local.proposals
    findings: list[dict[str, Any]] = []

    def where(row: Row) -> str:
        return "" if row.source == QUEUE_FILE else f" in {row.source}"

    def report(row: Row, problem: str) -> None:
        p = proposals.get(row.proposal)
        findings.append({
            "proposal": row.proposal, "milestone": None, "file": str(p.path) if p else None,
            "problem": f"queue row {row.label}{where(row)}: {problem}",
        })

    def finished(row: Row) -> bool:
        p = proposals.get(row.proposal)
        return p is not None and all(
            p.milestones.get(n) is not None and p.milestones[n].status in FINISHED
            for n in range(row.first, row.last + 1)
        )

    # Keyed on the row itself, not its label. A row copied into history.md and left in queue.md
    # has the same label in both files.
    seen: dict[tuple[str, int], Row] = {}
    for row in rows:
        for n in range(row.first, row.last + 1):
            other = seen.setdefault((row.proposal, n), row)
            if other is not row:
                report(row, f"{row.proposal} M{n} is also in row {other.label}{where(other)}")
        p = proposals.get(row.proposal)
        is_finished = finished(row)
        if is_finished and row.source == QUEUE_FILE:
            report(row, f"finished, so it moves to the end of {HISTORY_FILE}")
        if not is_finished and row.source == HISTORY_FILE and p is not None:
            report(row, f"unfinished, so it belongs in {QUEUE_FILE}")
        if not is_finished:
            if p is not None and p.status != "accepted":
                report(row, f"unfinished, but {row.proposal} is {p.status}. See plans.md \"Stopping a Proposal\"")
        if not row.note and sum(1 for r in rows if r.proposal == row.proposal) > 1:
            report(row, f"{row.proposal} has more than one row, so each needs a note saying why")
        for dep in row.depends_on:
            project, unresolved = ws.find(dep.proposal)
            if project is None and not is_finished:
                report(row, f"{dep} is unresolved: {unresolved}")
            if dep.legacy and not is_finished:
                report(row, (
                    f"{dep} is the legacy row gate. Reclassify it as a **Live after:** {dep.ref} deployed line "
                    f"on the milestone whose checks need the deployment, as {dep.ref} (merge after deployed) "
                    "when the proposal's skew analysis names a failing direction, or as a plain dependency. "
                    "See plans.md \"Deployment Dependencies\""
                ))
    return findings


# -- row ------------------------------------------------------------------


AWAITING_DEPLOY = ("awaiting deploy", "ask the user whether it is live")


def _dependency_state(dep: Dependency, ws: Workspace) -> tuple[str, str]:
    """Classify one dependency as met, unmet, awaiting deploy, blocked, or unresolved, with the reason.

    A deployment never confirms itself. A deploy dependency whose code is finished stays
    `awaiting deploy` until the user says it is live.

    A dependency on another project follows the same rules against that project's proposals
    and queue. One that cannot be found there is `unresolved`: the fix is an entry or a flag,
    so it holds the row rather than blocking it.
    """
    project, unresolved = ws.find(dep.proposal)
    if project is None:
        return "unresolved", unresolved
    proposals, rows, where = project.proposals, project.rows, ws.where(project)
    target = proposals.get(dep.proposal)
    if target is None:
        return "blocked", f"{dep.proposal} does not exist{where}"
    if dep.milestone is None:
        if target.status == "implemented":
            return AWAITING_DEPLOY if dep.deployed else ("met", "implemented")
        if target.status != "accepted":
            return "blocked", f"{dep.proposal} is {target.status or 'missing a status'}"
        unfinished = [n for n, m in target.milestones.items() if m.status not in FINISHED]
        if not any(row.names(dep.proposal, n) for row in rows for n in unfinished):
            return "blocked", f"{dep.proposal} has no queue row for its unfinished milestones{where}"
        return "unmet", f"{dep.proposal} is not implemented yet"

    if target.history and target.status == "implemented":
        return AWAITING_DEPLOY if dep.deployed else ("met", "implemented history")
    milestone = target.milestones.get(dep.milestone)
    if milestone is None:
        return "blocked", f"{dep.proposal} has no M{dep.milestone}"
    if milestone.status == "DONE":
        return AWAITING_DEPLOY if dep.deployed else ("met", "DONE")
    if milestone.status == "DROPPED":
        replacement = milestone.replaced_by
        hint = f"; wait on {replacement[0]}" + (f" M{replacement[1]}" if replacement[1] else "") if replacement else ""
        return "blocked", f"{dep} is DROPPED{hint}"
    if target.status not in ("accepted", "implemented"):
        return "blocked", f"{dep.proposal} is {target.status}"
    if not any(row.names(dep.proposal, dep.milestone) for row in rows):
        return "blocked", f"{dep.proposal} M{dep.milestone} is in no queue row{where}"
    return "unmet", f"{dep.proposal} M{dep.milestone} is {milestone.status}"


def row_info(
    proposals_dir: Path, proposal_id: str, milestone: int | None, overrides: dict[str, Location] | None = None
) -> dict[str, Any]:
    ws = workspace(proposals_dir, overrides)
    proposals, rows = ws.local.proposals, ws.local.rows
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
        state, reason = _dependency_state(dep, ws)
        deps.append({"dependency": str(dep), "state": state, "reason": reason})

    live_after = None
    if entry.live_after is not None:
        state, reason = _dependency_state(entry.live_after, ws)
        live_after = {"dependency": str(entry.live_after), "state": state, "reason": reason}

    earlier = [row.label for row in own if row.index < target.index and not finished(row)]
    pending_before = [
        f"{proposal_id} M{n}" for n in range(target.first, milestone)
        if proposal.milestones.get(n) is None or proposal.milestones[n].status not in FINISHED
    ]
    waits = deps + ([live_after] if live_after else [])
    runnable = proposal.status == "accepted" and entry.status not in FINISHED and not earlier and not pending_before
    ready = runnable and all(d["state"] == "met" for d in waits)
    # Only the user can say a deployment is live, so a milestone that waits on nothing else is
    # ready once the user says yes.
    ready_once_deployed = runnable and not ready and all(d["state"] in ("met", "awaiting deploy") for d in waits)
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
        "live_after": live_after,
        "earlier_rows_unfinished": earlier,
        "earlier_milestones_in_row_unfinished": pending_before,
        "ready": ready,
        "ready_once_deployed": ready_once_deployed,
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
    hooks = {i for start, (end, _) in hook_spans(lines).items() for i in range(start, end)}
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
                log_inserts[n] = all(
                    AUDIT_ENTRY.search(e) or CORRECTION_ENTRY.search(e) or SUPERSESSION_ENTRY.search(e)
                    for e in entries
                )

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
                kind = (
                    "decision-log entry that records neither a revisit audit, a correction of fact, "
                    "nor a supersession"
                )
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


def progress(proposals_dir: Path, today: str, overrides: dict[str, Location] | None = None) -> dict[str, Any]:
    """Join each queue row with its milestones' status: what is done, ready, held, or awaits a deploy."""
    ws = workspace(proposals_dir, overrides)
    report: dict[str, Any] = {
        "done": [], "ready": [], "held": [], "awaiting_deploy": [], "blocked": [],
        "hooks": hooks(proposals_dir, today, False),
    }
    for row in ws.local.rows:
        entry, finished, blocked, held, awaiting = _classify(row, ws)
        if finished:
            report["done"].append(entry)
        elif blocked:
            entry["blocked"] = blocked + held + awaiting
            report["blocked"].append(entry)
        elif held:
            entry["held"] = held + awaiting
            report["held"].append(entry)
        elif awaiting:
            entry["awaiting_deploy"] = awaiting
            report["awaiting_deploy"].append(entry)
        else:
            report["ready"].append(entry)
    return report


def _unfinished(row: Row, p: Proposal | None) -> bool:
    return any(
        p is None or p.milestones.get(n) is None or p.milestones[n].status not in FINISHED
        for n in range(row.first, row.last + 1)
    )


def _classify(row: Row, ws: Workspace) -> tuple[dict[str, Any], bool, list[str], list[str], list[str]]:
    """Summarize one row. Say whether it is finished, and what blocks, holds, or awaits a deploy.

    A `Live after` line on the row's next milestone decides for the row. One on a later
    milestone waits only for that milestone, so it is listed on the entry and leaves the row
    as it is.
    """
    rows, proposals = ws.local.rows, ws.local.proposals
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
        return entry, True, [], [], []
    next_number = next(n for n, s in statuses.items() if s not in FINISHED)
    entry["next"] = f"{row.proposal} M{next_number}"

    # Blocked reasons need the user. Held reasons clear once other work finishes, or once an
    # unresolved dependency gets an entry. Awaiting reasons clear once the user says a deployment
    # is live.
    blocked, held, awaiting = [], [], []
    if p is None:
        blocked.append(f"{row.proposal} does not exist")
    else:
        if p.status != "accepted":
            blocked.append(f"{row.proposal} is {p.status}")
        blocked += [f"{row.proposal} has no M{n}" for n, s in statuses.items() if s is None]
    for earlier in rows[: row.index]:
        if earlier.proposal == row.proposal and _unfinished(earlier, p):
            held.append(f"waits on its earlier row {earlier.label}")

    waits = [(None, dep) for dep in row.depends_on]
    live_after = []
    for n in numbers:
        m = p.milestones.get(n) if p else None
        if m is not None and m.live_after is not None and m.status not in FINISHED:
            waits.append((n, m.live_after))

    for n, dep in waits:
        state, reason = _dependency_state(dep, ws)
        if n is not None:
            live_after.append({
                "milestone": f"{row.proposal} M{n}", "dependency": str(dep), "state": state, "reason": reason,
            })
            if n != next_number:
                continue
        label = f"{row.proposal} M{n} live after {dep}" if n is not None else str(dep)
        if state == "blocked":
            blocked.append(f"{label}: {reason}")
        elif state == "awaiting deploy":
            awaiting.append(f"{label}: {reason}")
        elif state != "met":
            held.append(f"{label}: {reason}")

    if live_after:
        entry["live_after"] = live_after
    return entry, False, blocked, held, awaiting


def render_progress(report: dict[str, Any]) -> str:
    def tally(entry: dict[str, Any]) -> str:
        text = f"{entry['done']}/{entry['total'] - entry['dropped']} done"
        return text + (f", {entry['dropped']} dropped" if entry["dropped"] else "")

    lines = ["Done"]
    lines += [f"  {e['row']}  {tally(e)}" for e in report["done"]] or ["  (none)"]
    lines.append("Ready, in queue order")
    for e in report["ready"]:
        lines.append(f"  {e['row']}  {tally(e)}, next {e['next']}")
        lines += [f"    - {w['milestone']} live after {w['dependency']}: {w['state']}" for w in e.get("live_after", [])]
    if not report["ready"]:
        lines.append("  (none)")
    sections = (
        ("Held, until other work finishes", "held"),
        ("Awaiting deploy, the user says when it is live", "awaiting_deploy"),
        ("Blocked, needs the user", "blocked"),
    )
    for title, key in sections:
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


# -- next -----------------------------------------------------------------


def next_rows(
    proposals_dir: Path, count: int, holds: list[str], overrides: dict[str, Location] | None = None
) -> dict[str, Any]:
    """Pick the first `count` unfinished rows, in queue order, that a run can take.

    A row qualifies when nothing blocks it. Every row or milestone it waits on
    must be finished or already picked. A row the run cannot take is skipped and
    listed with its reasons, so the plan can say what it passed over.

    A row that awaits only a deployment qualifies. Its entry lists what awaits one, so the
    plan can ask the user whether each is live. A run cannot deploy, so a deployment whose
    code is not finished yet skips the row. So does an unresolved dependency, and an unmet one in
    another project, since a run builds only this project's rows.
    """
    if count < 1:
        raise ProposalError(f"--count {count} is not a positive number")
    ws = workspace(proposals_dir, overrides)
    proposals, rows = ws.local.proposals, ws.local.rows
    picked: list[Row] = []
    report: dict[str, Any] = {"run": [], "skipped": []}

    def in_run(proposal: str, milestone: int) -> bool:
        return any(row.names(proposal, milestone) for row in picked)

    for row in rows:
        if len(picked) == count:
            break
        entry, finished, blocked, _, awaiting = _classify(row, ws)
        if finished:
            continue
        if awaiting:
            entry["awaiting_deploy"] = awaiting
        reasons = list(blocked)
        if row.proposal in holds:
            reasons.append("held by the run's notes")
        p = proposals.get(row.proposal)
        for earlier in rows[: row.index]:
            if earlier.proposal == row.proposal and _unfinished(earlier, p) and earlier not in picked:
                reasons.append(f"waits on its earlier row {earlier.label}, which is not in the run")
        upcoming = next(
            (p.milestones.get(n) for n in range(row.first, row.last + 1)
             if p and (p.milestones.get(n) is None or p.milestones[n].status not in FINISHED)),
            None,
        )
        live = upcoming.live_after if upcoming else None
        for dep in row.depends_on + ([live] if live else []):
            state, reason = _dependency_state(dep, ws)
            if state == "unresolved":
                reasons.append(f"{dep}: {reason}")
                continue
            if state != "unmet":
                continue
            if dep.deployed:
                reasons.append(f"{dep}: {reason}, and a run cannot deploy it")
                continue
            project, _ = ws.find(dep.proposal)
            if project is not ws.local:
                reasons.append(f"{dep}: {reason}, and another project builds it")
                continue
            target = proposals[dep.proposal]
            needed = [dep.milestone] if dep.milestone else [
                n for n, m in target.milestones.items() if m.status not in FINISHED
            ]
            if not all(in_run(dep.proposal, n) for n in needed):
                reasons.append(f"{dep}: {reason}, and it is not in the run")
        if reasons:
            report["skipped"].append({"row": row.label, "reasons": reasons})
            continue
        picked.append(row)
        report["run"].append(entry)
    return report


# -- candidates -----------------------------------------------------------


DEPENDENCY_BULLET = re.compile(r"^[-*]\s+\[?([A-Z0-9]*[A-Z][A-Z0-9]*-\d+)\b")
OPEN_ITEM = re.compile(r"^(?:[-*]|\d+\.|###)\s+(.*)$")
CREATED = re.compile(r"^\*\*Created:\*\*\s*(\d{4}-\d{2}-\d{2})")
BUG_FILE = re.compile(r"bugs/(\d{8}-[^\s`)\]]+?\.md)")
TITLE = re.compile(r"^#\s+[A-Z0-9]*[A-Z][A-Z0-9]*-\d+:\s*(.+?)\s*$")


@dataclass
class Facts:
    """What a proposal's text says that bears on when to schedule it."""

    title: str
    created: str | None
    dependencies: list[str]
    open_questions: int
    bugs: list[str]
    motivation: str


def _facts(path: Path) -> Facts:
    lines = path.read_text().splitlines()
    spans = _sections(lines)

    def body(name: str) -> list[str]:
        start, end = spans.get(name, (0, 0))
        return lines[start + 1 : end]

    title = next((m.group(1) for line in lines if (m := TITLE.match(line))), "")
    created = next((m.group(1) for line in lines if (m := CREATED.match(line))), None)
    dependencies = [m.group(1) for line in body("Dependencies") if (m := DEPENDENCY_BULLET.match(line))]
    open_questions = sum(
        1 for line in body("Design Decisions (Open)")
        if (m := OPEN_ITEM.match(line)) and not re.match(r"none\b", m.group(1), re.IGNORECASE)
    )
    # A Decision Log entry that names a bug is history, not a reason to build.
    log = spans.get("Decision Log", (0, 0))
    cited = (line for i, line in enumerate(lines) if not log[0] <= i < log[1])
    bugs = sorted({m.group(1) for line in cited for m in BUG_FILE.finditer(line)})
    paragraph: list[str] = []
    why = next((name for name in ("Motivation", "Summary", "Overview") if name in spans), "Motivation")
    for line in body(why):
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    first = " ".join(paragraph)
    motivation = re.split(r"(?<=\.)\s", first, maxsplit=1)[0]
    return Facts(title, created, dependencies, open_questions, bugs, motivation)


def _bug_open(bugs_dir: Path, name: str) -> bool:
    """A bug file whose status is fixed or closed no longer argues for the work. An unreadable one still does."""
    path = bugs_dir / name
    if not path.is_file():
        return True
    for line in path.read_text().splitlines():
        m = PROPOSAL_STATUS.match(line)
        if m:
            return _base_status(m.group(1)) not in ("fixed", "closed")
    return True


def _base_status(status: str) -> str:
    """Drop the trailing note some statuses carry, as in `implemented (phase 459)`."""
    return status.split(maxsplit=1)[0].lower() if status.strip() else ""


def candidates(
    proposals_dir: Path, overrides: dict[str, Location] | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Sort the accepted proposals that have unscheduled milestones into tiers, per plans.md.

    The tiers are ready, waiting, and not_schedulable. Within a tier the order is the
    recommendation: most unblocked first, then bug fixes, then the oldest.

    A Dependencies section is prose, and may cite ADRs or tickets, so an ID whose prefix has no
    entry is passed over as before. One whose entry does not resolve, or that another project
    has yet to schedule, makes the candidate not schedulable from here.
    """
    ws = workspace(proposals_dir, overrides, queue=False)
    proposals, rows = ws.local.proposals, ws.local.rows
    status = {pid: _base_status(p.status) for pid, p in proposals.items()}
    facts = {pid: _facts(p.path) for pid, p in proposals.items() if status[pid] not in NOT_LIVE}
    bugs_dir = proposals_dir.parent / "bugs"

    dependents: dict[str, set[str]] = {}
    for pid, f in facts.items():
        if status[pid] in STOPPED:
            continue
        for dep in f.dependencies:
            if dep != pid:
                dependents.setdefault(dep, set()).add(pid)

    def unblocks(pid: str) -> list[str]:
        seen: set[str] = set()
        todo = [pid]
        while todo:
            for other in dependents.get(todo.pop(), ()):
                if other not in seen and other != pid:
                    seen.add(other)
                    todo.append(other)
        return sorted(seen)

    tiers: dict[str, list[dict[str, Any]]] = {"ready": [], "waiting": [], "not_schedulable": []}
    for pid, p in proposals.items():
        if status[pid] != "accepted":
            continue
        scheduled = {n for n in p.milestones for row in rows if row.names(pid, n)}
        unscheduled = sorted(n for n, m in p.milestones.items() if m.status not in FINISHED and n not in scheduled)
        if not unscheduled:
            continue
        f = facts[pid]
        waits_on: list[str] = []
        reasons: list[str] = []
        if f.open_questions:
            reasons.append(f"{f.open_questions} open design question(s); route it to proposal-reviewer")
        if not p.era3:
            reasons.append("its milestones are not subsections with a **Status:** line")
        if scheduled and min(unscheduled) < max(scheduled):
            reasons.append("an unscheduled milestone sits between scheduled ones")
        for dep in f.dependencies:
            if dep == pid:
                continue
            project, unresolved = ws.find(dep)
            if project is None:
                if _prefix(dep) in ws.locations:
                    reasons.append(f"depends on {dep}, which is unresolved: {unresolved}")
                continue
            target = project.proposals.get(dep)
            if target is None or _base_status(target.status) == "implemented":
                continue
            if _base_status(target.status) != "accepted":
                reasons.append(f"depends on {dep}, which is {target.status or 'missing a status'}")
            elif not any(row.proposal == dep for row in project.rows):
                if project is ws.local:
                    waits_on.append(dep)
                else:
                    where = ws.where(project)
                    reasons.append(f"depends on {dep}, which has no queue row{where}. Schedule it there")
        entry = {
            "proposal": pid,
            "title": f.title,
            "file": str(p.path),
            "created": f.created,
            "unscheduled": [f"{pid} M{n}" for n in unscheduled],
            "unblocks": unblocks(pid),
            "bugs": [name for name in f.bugs if _bug_open(bugs_dir, name)],
            "motivation": f.motivation,
        }
        if reasons:
            tiers["not_schedulable"].append({**entry, "reasons": reasons, "waits_on": waits_on})
        elif waits_on:
            tiers["waiting"].append({**entry, "waits_on": waits_on})
        else:
            tiers["ready"].append(entry)

    for tier in tiers.values():
        tier.sort(key=lambda e: (-len(e["unblocks"]), not e["bugs"], e["created"] or "9999-99-99", e["proposal"]))
    return tiers


# -- cli ------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "row", "freeze", "hooks", "progress", "notice", "next", "candidates"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--proposals-dir", type=Path, required=True)
        if name in ("check", "row", "progress", "next", "candidates"):
            cmd.add_argument(
                "--proposals-for", action="append", default=[], metavar="PREFIX=PATH",
                help="where another project's proposals live, overriding queue.md; PATH is relative to the "
                "current directory",
            )
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
        if name == "next":
            cmd.add_argument("--count", type=int, default=1, help="how many rows to pick; defaults to 1")
            cmd.add_argument("--hold", action="append", default=[], help="a proposal whose rows the run holds")
    args = parser.parse_args(argv)
    try:
        if getattr(args, "today", None) is not None and not ISO_DATE.match(args.today):
            raise ProposalError(f"--today {args.today!r} is not YYYY-MM-DD")
        overrides = parse_overrides(getattr(args, "proposals_for", []))
        if args.command == "check":
            result: Any = check(args.proposals_dir, overrides)
        elif args.command == "next":
            result = next_rows(args.proposals_dir, args.count, args.hold, overrides)
        elif args.command == "candidates":
            result = candidates(args.proposals_dir, overrides)
        elif args.command == "hooks":
            result = hooks(args.proposals_dir, args.today, args.passed)
        elif args.command in ("progress", "notice"):
            # These two print text for a person to read, so they skip the JSON below.
            if args.command == "notice":
                text = notice(args.proposals_dir, args.today)
            else:
                report = progress(args.proposals_dir, args.today, overrides)
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
            result = row_info(args.proposals_dir, args.proposal, milestone, overrides)
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
