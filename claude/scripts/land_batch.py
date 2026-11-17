#!/usr/bin/env python3
"""Run the deterministic steps of landing one land-branch batch, and keep the run file.

    python3 land_batch.py init --plan FILE --preflight FILE --snapshot SHA --onto SHA --batch-tip SHA
                               --mainline BRANCH --merge-method METHOD --topic NAME --worktrees DIR
                               --staging-branch BRANCH --staging-worktree DIR --check-command CMD
                               --review-policy POLICY --deadline ISO [--state-dir DIR]
    python3 land_batch.py status --run FILE
    python3 land_batch.py open --run FILE --batch NAME [--title-file FILE --body-file FILE] [--picked]
    python3 land_batch.py merge --run FILE --batch NAME
    python3 land_batch.py finish --run FILE --batch NAME

The coordinator in the land-branch skill owns every judgement and the run's one watcher. This
script owns the steps between them, and it never waits on CI or reviews:

- `open` creates the batch branch in its own worktree from the mainline, cherry-picks the batch,
  runs the local checks, pushes to the push remote, and opens the PR. Re-run it after any commit
  or rebase in the worktree: it reruns the checks on the new head and pushes it, with a lease
  pinned to the head it last pushed when a rebase rewrote the branch
- `merge` turns on merging once every check on the pushed head finished and no required check
  failed. It names the failed checks that are not required, for the coordinator to look at
- `finish` cleans up a merged batch and names the batches it made ready

Each command prints one JSON object. Exit 0 means the step is done. Exit 3 means the script
stopped for the coordinator, with `stop` naming why: a conflict, a failed check, a PR that is not
ready to merge. The worktree, branch, and PR stay in place, and re-running the same command after
the coordinator acts picks up from the live state. Exit 1 is a usage or run-file error. Exit 2 is
a git or gh command that failed.

The run file is JSON, and this script is its only writer:

    {"version": 1, "repo": "OWNER/NAME", "snapshot": "<sha>", "onto": "<sha>", "batch_tip": "<sha>",
     "staging": {"branch": "agent/stage/<topic>", "worktree": "<dir>"},
     "plan": <the plan batch_plan.py verified>,
     "mainline": "main",
     "remotes": {"mainline": "upstream", "push": "origin", "head_prefix": "someone:", "fork": true},
     "merge_method": "MERGE", "required_checks": ["ci"], "auto_merge": true, "delete_branch_on_merge": true,
     "check_command": "make ci", "review_policy": "...", "deadline": "<ISO 8601>",
     "topic": "<topic>", "worktrees": "<dir>", "branch_prefix": "agent/",
     "batches": {"<name>": {"status": "not-started", "branch": null, "worktree": null, "start": null,
                            "picked": false, "checked_head": null, "pushed_head": null, "pr": null}}}

`required_checks` is null when preflight could not read the base's protection, and every check
then counts as required. `status` is one of not-started, open, merged, and stopped. A batch whose
PR closed without merging is stopped. `init` writes the file at
`<state-dir>/land-branch/v3/<owner>-<repo>-<snapshot>.json`, with the snapshot's short hash.
Hand-kept run files from older plugins live in `land-branch/` and `land-branch/v2/`, and this
script never reads them. The run's watch state file sits beside the run file with a `.watch.json`
suffix.

`branch_prefix` comes from preflight's `branches.prefix`. A batch branch is named
`<prefix><topic><sep><batch>`, where `<sep>` is the prefix's last character, as pr_watch.py's
`branch_name` defines. A run file that has no `branch_prefix` uses `agent/`.

Batches land serially: a batch is ready once every batch in its `after` list merged, and its PR
targets the mainline. Stacked batches are landed by hand, as the skill describes.

Every write takes a lock on `<run file>.lock`, re-reads the file, and replaces it atomically. No
command holds the run file in memory across a long step, so `open` on two independent batches can
run at once. `gh` calls go through pr_watch.py's helpers, which need gh's credentials. Run this
script through cg, or with the sandbox disabled.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator

sys.path.insert(0, str(Path(__file__).parent))

import pr_watch  # noqa: E402

VERSION = 1
STATUSES = ("not-started", "open", "merged", "stopped")


class RunError(Exception):
    pass


class CommandFailed(Exception):
    pass


class Stop(Exception):
    def __init__(self, reason: str, **detail: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


# -- run file ----------------------------------------------------------------------------------


def load(path: Path) -> dict[str, Any]:
    try:
        run = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise RunError(f"cannot read run file {path}: {e}") from e
    if run.get("version") != VERSION:
        raise RunError(f"{path} has version {run.get('version')!r}, not {VERSION}. It was not written by this "
                       "script, so land its batches by hand")
    return run


def write(path: Path, run: dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(run, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(path: Path) -> Iterator[None]:
    with open(str(path) + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def update(path: Path, name: str, **fields: Any) -> dict[str, Any]:
    with locked(path):
        run = load(path)
        run["batches"][name].update(fields)
        write(path, run)
    return run


def watch_file(path: Path) -> Path:
    return path.with_name(path.name[:-len(".json")] + ".watch.json")


def loop_file(state_dir: Path, repo: str, pr: int) -> Path:
    return state_dir / "merge-fix-loop" / f"{repo.replace('/', '-')}-{pr}.loop.json"


def state_dir_of(path: Path) -> Path:
    return path.parent.parent.parent


def plan_batch(run: dict[str, Any], name: str) -> dict[str, Any]:
    for batch in run["plan"]["batches"]:
        if batch["name"] == name:
            return batch
    raise RunError(f"the plan has no batch {name}")


def ready(run: dict[str, Any]) -> list[str]:
    merged = {n for n, b in run["batches"].items() if b["status"] == "merged"}
    return [b["name"] for b in run["plan"]["batches"]
            if run["batches"][b["name"]]["status"] == "not-started" and set(b.get("after", [])) <= merged]


# -- commands ----------------------------------------------------------------------------------


def git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise CommandFailed(f"git {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result


def out(args: list[str], cwd: Path) -> str:
    return git(args, cwd).stdout.strip()


def gh(args: list[str]) -> str:
    try:
        return pr_watch.gh(args)
    except pr_watch.GhError as e:
        raise CommandFailed(f"gh {' '.join(args)}: {e}") from e


def snapshot(repo: str, pr: int) -> dict[str, Any]:
    owner, name = repo.split("/")
    try:
        return pr_watch.summarize(pr_watch.fetch_pr(owner, name, pr))
    except pr_watch.GhError as e:
        raise CommandFailed(f"snapshot of PR #{pr}: {e}") from e


def checkout_root(run: dict[str, Any]) -> Path:
    return Path(run["staging"]["worktree"])


# -- init --------------------------------------------------------------------------------------


def init(args: argparse.Namespace) -> dict[str, Any]:
    plan = json.loads(Path(args.plan).read_text())
    preflight = json.loads(Path(args.preflight).read_text())
    remotes = preflight.get("remotes")
    if not remotes or not remotes.get("mainline") or not remotes.get("push"):
        raise RunError("preflight names no mainline or push remote. Settle its needs first")
    if args.merge_method not in (preflight.get("merge_methods") or {}).get("allowed", []):
        raise RunError(f"{args.merge_method} is not an allowed merge method on the base")

    prefix = (preflight.get("branches") or {}).get("prefix") or pr_watch.DEFAULT_BRANCH_PREFIX
    try:
        for b in plan["batches"]:
            pr_watch.branch_name(prefix, args.topic, b["name"])
    except ValueError as e:
        raise RunError(str(e)) from e

    repo = preflight["repo"]
    slug = repo["nameWithOwner"]
    path = Path(args.state_dir).expanduser() / "land-branch" / "v3" / f"{slug.replace('/', '-')}-{args.snapshot[:7]}.json"
    if path.exists():
        raise RunError(f"{path} already exists. Resume that run instead")

    run = {
        "version": VERSION,
        "repo": slug,
        "snapshot": args.snapshot,
        "onto": args.onto,
        "batch_tip": args.batch_tip,
        "staging": {"branch": args.staging_branch, "worktree": str(Path(args.staging_worktree).resolve())},
        "plan": plan,
        "mainline": args.mainline,
        "remotes": {k: remotes[k] for k in ("mainline", "push", "head_prefix", "fork")},
        "merge_method": args.merge_method,
        "required_checks": (None if preflight.get("protection_unreadable")
                            else sorted((preflight.get("protection") or {}).get("required_checks") or [])),
        "auto_merge": bool(repo.get("autoMergeAllowed")),
        "delete_branch_on_merge": bool(repo.get("deleteBranchOnMerge")),
        "check_command": args.check_command,
        "review_policy": args.review_policy,
        "deadline": args.deadline,
        "topic": args.topic,
        "worktrees": str(Path(args.worktrees).expanduser().resolve()),
        "branch_prefix": prefix,
        "batches": {b["name"]: {"status": "not-started", "branch": None, "worktree": None, "start": None,
                                "picked": False, "checked_head": None, "pushed_head": None, "pr": None}
                    for b in plan["batches"]},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        write(path, run)
    return {"run": str(path), "watch_state": str(watch_file(path)), "ready": ready(run)}


def status(args: argparse.Namespace) -> dict[str, Any]:
    run = load(Path(args.run))
    return {"batches": {n: {k: b[k] for k in ("status", "branch", "pr")} for n, b in run["batches"].items()},
            "ready": ready(run),
            "all_merged": all(b["status"] == "merged" for b in run["batches"].values())}


# -- open --------------------------------------------------------------------------------------


def in_progress(worktree: Path) -> bool:
    return git(["rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD"], worktree, check=False).returncode == 0


def conflicted(worktree: Path) -> list[str]:
    return sorted(out(["diff", "--name-only", "--diff-filter=U"], worktree).splitlines())


def find_pr(run: dict[str, Any], branch: str) -> dict[str, Any] | None:
    owner = run["remotes"]["head_prefix"].rstrip(":") or run["repo"].split("/")[0]
    prs = json.loads(gh(["pr", "list", "--repo", run["repo"], "--head", branch, "--state", "open",
                         "--json", "number,url,headRepositoryOwner"]) or "[]")
    mine = [p for p in prs if ((p.get("headRepositoryOwner") or {}).get("login") or "").lower() == owner.lower()]
    return mine[0] if mine else None


def open_batch(args: argparse.Namespace, run_checks: Callable[[str, Path, Path], int]) -> dict[str, Any]:
    path = Path(args.run)
    run = load(path)
    name = args.batch
    batch = plan_batch(run, name)
    state = run["batches"][name]
    remotes = run["remotes"]
    root = checkout_root(run)

    if state["status"] in ("merged", "stopped"):
        raise Stop("batch-done", status=state["status"])
    if state["status"] == "not-started" and name not in ready(run):
        waiting = [a for a in batch.get("after", []) if run["batches"][a]["status"] != "merged"]
        raise Stop("not-ready", waiting_for=waiting)

    mainline_ref = f"{remotes['mainline']}/{run['mainline']}"
    prefix = run.get("branch_prefix") or pr_watch.DEFAULT_BRANCH_PREFIX
    branch = state["branch"] or pr_watch.branch_name(prefix, run["topic"], name)
    worktree = Path(state["worktree"] or Path(run["worktrees"]) / f"{run['topic']}-{name}")

    git(["fetch", remotes["mainline"]], root)
    if remotes["push"] != remotes["mainline"]:
        git(["fetch", remotes["push"]], root)

    if not worktree.exists():
        if git(["rev-parse", "-q", "--verify", f"refs/heads/{branch}"], root, check=False).returncode == 0:
            raise Stop("branch-without-worktree", branch=branch, worktree=str(worktree))
        start = out(["rev-parse", mainline_ref], root)
        git(["worktree", "add", "--no-track", "-b", branch, str(worktree), start], root)
        run = update(path, name, status="open", branch=branch, worktree=str(worktree), start=start)
        state = run["batches"][name]

    if not state["picked"]:
        if in_progress(worktree):
            raise Stop("cherry-pick-in-progress", worktree=str(worktree), conflicts=conflicted(worktree))
        head = out(["rev-parse", "HEAD"], worktree)
        if head == state["start"]:
            pick = git(["cherry-pick", *batch["commits"]], worktree, check=False)
            if pick.returncode != 0:
                raise Stop("cherry-pick-conflict", worktree=str(worktree), conflicts=conflicted(worktree),
                           message=(pick.stderr or pick.stdout).strip())
        count = int(out(["rev-list", "--count", f"{state['start']}..HEAD"], worktree))
        if count != len(batch["commits"]) and not args.picked:
            raise Stop("pick-count-mismatch", expected=len(batch["commits"]), found=count, worktree=str(worktree),
                       hint="pass --picked when the coordinator finished the picks by hand")
        run = update(path, name, picked=True)
        state = run["batches"][name]

    head = out(["rev-parse", "HEAD"], worktree)
    if state["checked_head"] != head:
        log = path.with_name(f"{path.name[:-len('.json')]}.{name}.check.log")
        code = run_checks(run["check_command"], worktree, log)
        if code != 0:
            raise Stop("local-checks-failed", code=code, log=str(log), worktree=str(worktree))
        run = update(path, name, checked_head=head)
        state = run["batches"][name]

    if state["pushed_head"] != head:
        pushed = state["pushed_head"]
        refspec = f"refs/heads/{branch}:refs/heads/{branch}"
        if pushed and git(["merge-base", "--is-ancestor", pushed, head], worktree, check=False).returncode != 0:
            # A rebase rewrote the branch. Pin the lease to the head this script pushed, so a push it never
            # saw is refused rather than overwritten.
            git(["push", f"--force-with-lease={branch}:{pushed}", remotes["push"], refspec], worktree)
        else:
            git(["push", "-u", remotes["push"], refspec], worktree)
        run = update(path, name, pushed_head=head)
        state = run["batches"][name]

    if state["pr"] is None:
        existing = find_pr(run, branch)
        if existing:
            number, url = existing["number"], existing["url"]
        else:
            if not args.title_file or not args.body_file:
                raise RunError("opening the PR needs --title-file and --body-file")
            title = Path(args.title_file).read_text().strip()
            url = gh(["pr", "create", "--repo", run["repo"], "--base", run["mainline"],
                      "--head", remotes["head_prefix"] + branch, "--title", title,
                      "--body-file", args.body_file]).strip().splitlines()[-1]
            number = int(url.rstrip("/").rsplit("/", 1)[1])
        run = update(path, name, pr=number)
        loop = loop_file(state_dir_of(path), run["repo"], number)
        loop.parent.mkdir(parents=True, exist_ok=True)
        loop.write_text(json.dumps({"pr": number, "repo": run["repo"], "branch": branch, "worktree": str(worktree),
                                    "base": run["mainline"], "merge_into": run["mainline"],
                                    "review_policy": run["review_policy"], "deadline": run["deadline"]},
                                   indent=1) + "\n")
        return {"event": "opened", "batch": name, "pr": number, "url": url, "head": head}

    return {"event": "open", "batch": name, "pr": state["pr"], "head": head}


def run_checks(command: str, worktree: Path, log: Path) -> int:
    result = subprocess.run(shlex.split(command), cwd=worktree, capture_output=True, text=True)
    log.write_text(result.stdout + "\n--- stderr ---\n" + result.stderr)
    return result.returncode


# -- merge and finish --------------------------------------------------------------------------


def opened(run: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in run["batches"]:
        raise RunError(f"the run has no batch {name}")
    state = run["batches"][name]
    if state["status"] != "open" or state["pr"] is None:
        raise Stop("not-open", status=state["status"])
    return state


def merge(args: argparse.Namespace) -> dict[str, Any]:
    run = load(Path(args.run))
    state = opened(run, args.batch)
    pr = state["pr"]
    snap = snapshot(run["repo"], pr)

    if snap["merged"]:
        return {"event": "merged", "batch": args.batch, "pr": pr}
    if snap["state"] != "OPEN":
        update(Path(args.run), args.batch, status="stopped")
        raise Stop("pr-closed", state=snap["state"])

    # `gh pr merge --auto` merges at once on a CLEAN PR, so every gate holds before any merge command.
    if snap["base"] != run["mainline"]:
        raise Stop("base-not-mainline", base=snap["base"])
    if snap["sha"] != state["pushed_head"]:
        raise Stop("head-moved", head=snap["sha"], pushed=state["pushed_head"])
    if not snap["checks"]:
        raise Stop("no-checks")
    if snap["pending"]:
        raise Stop("checks-pending", pending=snap["pending"])
    required = run["required_checks"]
    blocking = [c for c in snap["failed"] if required is None or c in required]
    if blocking:
        raise Stop("checks-failed", failed=blocking)

    done = {"batch": args.batch, "pr": pr, "failed_not_required": [c for c in snap["failed"] if c not in blocking]}
    method = "--" + run["merge_method"].lower()
    if snap["auto_merge"]:
        return {"event": "auto-merge-on", **done}
    if run["auto_merge"]:
        gh(["pr", "merge", str(pr), "--repo", run["repo"], "--auto", method])
        return {"event": "auto-merge-on", **done}
    if snap["merge_state"] != "CLEAN":
        raise Stop("not-clean", merge_state=snap["merge_state"])
    gh(["pr", "merge", str(pr), "--repo", run["repo"], method])
    return {"event": "merge-requested", **done}


def finish(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.run)
    run = load(path)
    state = opened(run, args.batch)
    pr = state["pr"]
    remotes = run["remotes"]
    root = checkout_root(run)

    snap = snapshot(run["repo"], pr)
    if not snap["merged"]:
        if snap["state"] != "OPEN":
            update(path, args.batch, status="stopped")
            raise Stop("pr-closed", state=snap["state"])
        raise Stop("not-merged", pr=pr)
    children = json.loads(gh(["pr", "list", "--repo", run["repo"], "--base", state["branch"], "--state", "open",
                              "--json", "number"]) or "[]")
    if children:
        raise Stop("open-prs-on-branch", prs=[c["number"] for c in children])

    if Path(state["worktree"]).exists():
        git(["worktree", "remove", state["worktree"]], root)
    if git(["rev-parse", "-q", "--verify", f"refs/heads/{state['branch']}"], root, check=False).returncode == 0:
        git(["branch", "-D", state["branch"]], root)
    if out(["ls-remote", "--heads", remotes["push"], f"refs/heads/{state['branch']}"], root):
        git(["push", remotes["push"], "--delete", state["branch"]], root)

    for stale in (loop_file(state_dir_of(path), run["repo"], pr),
                  state_dir_of(path) / "merge-fix-loop" / f"{run['repo'].replace('/', '-')}-{pr}.json"):
        with contextlib.suppress(FileNotFoundError):
            stale.unlink()

    run = update(path, args.batch, status="merged")
    return {"event": "finished", "batch": args.batch, "pr": pr, "ready": ready(run),
            "all_merged": all(b["status"] == "merged" for b in run["batches"].values())}


# -- main --------------------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="land_batch.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="write the run file for an approved, verified plan")
    p.add_argument("--plan", required=True)
    p.add_argument("--preflight", required=True, help="a file holding pr_watch.py preflight's output")
    for flag in ("--snapshot", "--onto", "--batch-tip", "--mainline", "--merge-method", "--topic", "--worktrees",
                 "--staging-branch", "--staging-worktree", "--check-command", "--review-policy", "--deadline"):
        p.add_argument(flag, required=True)
    p.add_argument("--state-dir", default="~/.local/state/coding_agent_standards")

    p = sub.add_parser("status", help="report each batch and which are ready")
    p.add_argument("--run", required=True)

    p = sub.add_parser("open", help="branch, pick, check, push, and open the PR for a ready batch")
    p.add_argument("--run", required=True)
    p.add_argument("--batch", required=True)
    p.add_argument("--title-file")
    p.add_argument("--body-file")
    p.add_argument("--picked", action="store_true", help="the coordinator finished the picks by hand")

    for command, text in (("merge", "turn on merging once the checks finished and none failed"),
                          ("finish", "clean up a merged batch and name the batches it made ready")):
        p = sub.add_parser(command, help=text)
        p.add_argument("--run", required=True)
        p.add_argument("--batch", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = init(args)
        elif args.command == "status":
            result = status(args)
        elif args.command == "open":
            result = open_batch(args, run_checks)
        elif args.command == "merge":
            result = merge(args)
        else:
            result = finish(args)
    except Stop as e:
        print(json.dumps({"stop": e.reason, "batch": getattr(args, "batch", None), **e.detail}))
        return 3
    except CommandFailed as e:
        print(json.dumps({"error": str(e), "batch": getattr(args, "batch", None)}))
        return 2
    except (RunError, KeyError, ValueError, OSError) as e:
        print(f"land_batch: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
