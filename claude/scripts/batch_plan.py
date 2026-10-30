#!/usr/bin/env python3
"""Check that a plan of commit batches reproduces the branch it was cut from.

    python3 batch_plan.py verify --plan FILE

The plan is JSON:

    {"base": "<sha>", "tip": "<sha>",
     "batches": [{"name": "docs", "commits": ["<sha>", ...], "after": []},
                 {"name": "parser", "commits": ["<sha>", ...], "after": ["docs"]}]}

`base` is where the batches start, usually the merge base with the mainline. `tip` is the snapshot
of the branch being landed. `after` names the batches a batch must land behind. A batch with an
empty `after` is meant to land concurrently with the others, straight onto the mainline.

Two checks run, each in a throwaway detached worktree that is removed afterwards:

1. Each batch is cherry-picked onto `base` plus only the batches it is `after`, transitively. A
   conflict means the batch depends on work the plan does not give it.
2. Every batch is cherry-picked onto `base` in dependency order. The resulting tree must equal the
   tree of `tip`. A difference means the plan dropped, duplicated, or reordered work.

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
    result["missing"] = [c for c in on_branch if c not in listed]
    result["extra"] = sorted(listed - set(on_branch))
    result["ok"] = (all(b["applies"] for b in result["batches"]) and result["tree_matches"]
                    and not result["missing"] and not result["extra"])
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="batch_plan.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("verify", help="check that the batches apply on their own and rebuild the tip's tree")
    p.add_argument("--plan", type=Path, required=True, help="JSON plan file")
    args = parser.parse_args(argv[1:])

    try:
        result = verify(json.loads(args.plan.read_text()))
    except (PlanError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"batch_plan: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
