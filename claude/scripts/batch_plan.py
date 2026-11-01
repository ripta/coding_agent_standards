#!/usr/bin/env python3
"""Check that a plan of commit batches reproduces the branch it was cut from.

    python3 batch_plan.py verify --plan FILE
    python3 batch_plan.py reduce --plan FILE

The plan is JSON:

    {"base": "<sha>", "tip": "<sha>",
     "batches": [{"name": "docs", "commits": ["<sha>", ...], "after": []},
                 {"name": "parser", "commits": ["<sha>", ...], "after": ["docs"]}]}

`base` is where the batches start, usually the merge base with the mainline. `tip` is the snapshot
of the branch being landed. `after` names the batches a batch must land behind. A batch with an
empty `after` is meant to land concurrently with the others, straight onto the mainline.

The optional `"exclude": ["<sha>", ...]` lists commits that are left out on purpose, such as empty
marker commits. verify accepts an entry only when it is on the branch range and its tree equals its
parent's tree. Accepted entries appear under `excluded`. Any other entry appears under
`exclude_errors` as `{"commit", "reason"}` and fails the plan. An entry that is also in a batch is a
plan error.

Two checks run, each in a throwaway detached worktree that is removed afterwards:

1. Each batch is cherry-picked onto `base` plus only the batches it is `after`, transitively. A
   conflict means the batch depends on work the plan does not give it.
2. Every batch is cherry-picked onto `base` in dependency order. The resulting tree must equal the
   tree of `tip`. A difference means the plan dropped, duplicated, or reordered work.

`reduce` prints each batch's `after` list after transitive reduction, as a JSON object keyed by
batch name. A batch that is after B, and after A which B is also after, reduces to B alone. A batch
whose reduced list holds one name can stack on that batch's branch.

The result is JSON on stdout, with `ok` true only when both checks pass. Errors in the plan itself
go to stderr with exit status 1. A plan that fails a check exits 3.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class PlanError(Exception):
    pass


def git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise PlanError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result


def resolve(rev: str) -> str:
    return git(["rev-parse", "--verify", f"{rev}^{{commit}}"]).stdout.strip()


def validate(plan: dict[str, Any]) -> list[dict[str, Any]]:
    batches = plan.get("batches")
    if not isinstance(batches, list) or not batches:
        raise PlanError("plan has no batches")

    names = [b.get("name") for b in batches]
    if len(set(names)) != len(names) or not all(isinstance(n, str) and n for n in names):
        raise PlanError("every batch needs a unique, non-empty name")

    seen: set[str] = set()
    for batch in batches:
        if not batch.get("commits"):
            raise PlanError(f"batch {batch['name']} has no commits")
        for after in batch.setdefault("after", []):
            if after not in names:
                raise PlanError(f"batch {batch['name']} is after unknown batch {after}")
        full = [resolve(c) for c in batch["commits"]]
        dupes = seen.intersection(full)
        if dupes:
            raise PlanError(f"batch {batch['name']} repeats commits already in another batch: {sorted(dupes)}")
        seen.update(full)
        batch["commits"] = full
    return batches


def validate_exclude(plan: dict[str, Any], batches: list[dict[str, Any]]) -> list[str]:
    raw = plan.get("exclude", [])
    if not isinstance(raw, list):
        raise PlanError("exclude must be a list of commits")

    full = [resolve(c) for c in raw]
    batched = {c for b in batches for c in b["commits"]}
    both = batched.intersection(full)
    if both:
        raise PlanError(f"exclude lists commits that are also in a batch: {sorted(both)}")
    return full


def check_excluded(exclude: list[str], on_branch: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Split `exclude` into accepted commits and errors. Only an empty commit on the range is accepted."""
    accepted: list[str] = []
    errors: list[dict[str, str]] = []
    for commit in exclude:
        if commit not in on_branch:
            errors.append({"commit": commit, "reason": "not on the branch range"})
            continue
        tree = git(["rev-parse", f"{commit}^{{tree}}"]).stdout.strip()
        parent_tree = git(["rev-parse", f"{commit}^^{{tree}}"]).stdout.strip()
        if tree != parent_tree:
            errors.append({"commit": commit, "reason": "not empty"})
            continue
        accepted.append(commit)
    return accepted, errors


def order(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Topological order by `after`, keeping plan order where the dependencies allow it."""
    by_name = {b["name"]: b for b in batches}
    done: list[str] = []
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in done:
            return
        if name in visiting:
            raise PlanError(f"batch {name} is part of an `after` cycle")
        visiting.add(name)
        for after in by_name[name]["after"]:
            visit(after)
        visiting.discard(name)
        done.append(name)

    for batch in batches:
        visit(batch["name"])
    return [by_name[n] for n in done]


def ancestors(batches: list[dict[str, Any]], name: str) -> set[str]:
    by_name = {b["name"]: b for b in batches}
    found: set[str] = set()
    stack = list(by_name[name]["after"])
    while stack:
        current = stack.pop()
        if current not in found:
            found.add(current)
            stack.extend(by_name[current]["after"])
    return found


def reduced_after(batches: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Drop each `after` entry that another entry already reaches."""
    by_name = {b["name"]: b for b in batches}
    reduced: dict[str, list[str]] = {}
    for batch in batches:
        direct = batch["after"]
        covered: set[str] = set()
        for other in direct:
            covered |= ancestors(batches, other)
        reduced[batch["name"]] = [n for n in direct if n not in covered and n in by_name]
    return reduced


def apply(worktree: Path, start: str, commits: list[str]) -> str | None:
    """Reset the worktree to `start` and cherry-pick `commits`. Return the conflicting commit, if any."""
    git(["reset", "--hard", "--quiet", start], cwd=worktree)
    for commit in commits:
        picked = git(["cherry-pick", "--allow-empty", "--keep-redundant-commits", commit], cwd=worktree, check=False)
        if picked.returncode != 0:
            git(["cherry-pick", "--abort"], cwd=worktree, check=False)
            return commit
    return None


def verify(plan: dict[str, Any]) -> dict[str, Any]:
    base = resolve(plan["base"])
    tip = resolve(plan["tip"])
    batches = validate(plan)
    exclude = validate_exclude(plan, batches)
    ordered = order(batches)

    result: dict[str, Any] = {"base": base, "tip": tip, "order": [b["name"] for b in ordered], "batches": []}
    with tempfile.TemporaryDirectory(prefix="batch-plan-") as tmp:
        worktree = Path(tmp) / "wt"
        git(["worktree", "add", "--detach", "--quiet", str(worktree), base])
        try:
            for batch in ordered:
                needed = ancestors(batches, batch["name"])
                prior = [c for b in ordered if b["name"] in needed for c in b["commits"]]
                conflict = apply(worktree, base, prior + batch["commits"])
                result["batches"].append({"name": batch["name"], "applies": conflict is None, "conflict": conflict})

            all_commits = [c for b in ordered for c in b["commits"]]
            conflict = apply(worktree, base, all_commits)
            if conflict:
                result["tree_matches"] = False
                result["combined_conflict"] = conflict
            else:
                built = git(["rev-parse", "HEAD^{tree}"], cwd=worktree).stdout.strip()
                wanted = git(["rev-parse", f"{tip}^{{tree}}"]).stdout.strip()
                result["tree_matches"] = built == wanted
                if built != wanted:
                    result["tree_diff"] = git(["diff", "--stat", built, wanted]).stdout
        finally:
            # Every apply ends clean, so a plain remove succeeds. If it does not, the temporary
            # directory is deleted anyway and the prune below drops the stale registration.
            git(["worktree", "remove", str(worktree)], check=False)
    git(["worktree", "prune"], check=False)

    listed = {c for b in batches for c in b["commits"]}
    on_branch = git(["rev-list", "--no-merges", f"{base}..{tip}"]).stdout.split()
    excluded, exclude_errors = check_excluded(exclude, on_branch)
    result["excluded"] = excluded
    result["exclude_errors"] = exclude_errors
    result["missing"] = [c for c in on_branch if c not in listed and c not in exclude]
    result["extra"] = sorted(listed - set(on_branch))
    result["ok"] = (all(b["applies"] for b in result["batches"]) and result["tree_matches"]
                    and not result["missing"] and not result["extra"] and not exclude_errors)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="batch_plan.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify", help="check that the batches apply on their own and rebuild the tip's tree")
    p.add_argument("--plan", type=Path, required=True, help="JSON plan file")
    p = sub.add_parser("reduce", help="print each batch's after list with redundant entries removed")
    p.add_argument("--plan", type=Path, required=True, help="JSON plan file")
    args = parser.parse_args(argv[1:])

    if args.command == "reduce":
        try:
            plan = json.loads(args.plan.read_text())
            batches = validate(plan)
            order(batches)
            print(json.dumps(reduced_after(batches), indent=2))
        except (PlanError, OSError, json.JSONDecodeError, KeyError) as e:
            print(f"batch_plan: {e}", file=sys.stderr)
            return 1
        return 0

    try:
        result = verify(json.loads(args.plan.read_text()))
    except (PlanError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"batch_plan: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
