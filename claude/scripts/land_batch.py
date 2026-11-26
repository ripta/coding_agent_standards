#!/usr/bin/env python3
"""Run the deterministic steps of landing one land-branch batch, and keep the run file.

    python3 land_batch.py init --plan FILE --preflight FILE --snapshot SHA --onto SHA --batch-tip SHA
                               --mainline BRANCH --merge-method METHOD --topic NAME --worktrees DIR
                               --staging-branch BRANCH --staging-worktree DIR --check-command CMD
                               --review-policy POLICY --deadline ISO [--checks-file FILE]
                               [--state-dir DIR]
    python3 land_batch.py status --run FILE
    python3 land_batch.py set-check-command --run FILE --check-command CMD
    python3 land_batch.py set-checks --run FILE --checks-file FILE
    python3 land_batch.py submodules --worktree DIR --base SHA --tip SHA
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
- `set-check-command` changes the run's local check command. The next `open` of each open batch
  that has no checks of its own reruns the checks on its head
- `set-checks` replaces the checks of the batches a checks file names. The next `open` of each such
  open batch reruns them
- `submodules` checks the submodule pointers a range bumps, with no batch yet

A repository with submodules gets them populated. `open` runs `git submodule update --init
--recursive` in the new worktree, and again before the checks, since the head may name new commits.
It stops with `submodule-commit-not-on-remote` when a submodule pointer the batch bumped names a
commit that no branch or tag of the submodule's remote holds. The stop's `submodules` lists each
one with its path, commit, and URL. The commit must land in the submodule's own repository first.
It stops with `submodule-update-failed` when the update itself fails for any other reason.
`submodules` runs the pointer check alone on a worktree and a range, before any batch exists. It
clones only the submodules the range bumps, and a checkout that fails there does not matter. A
clone that fails stops it with `submodule-update-failed`, since nothing is left to check.

`finish` removes a worktree that holds submodules only once nothing in it would be lost. Git
refuses a plain `git worktree remove` there whatever the state, so the removal is forced after
two checks. `git status` must show the worktree and each submodule in it, nested ones too, clean.
It runs with `--untracked-files=normal` and `--ignore-submodules=none`, and once per submodule, so
the user's `status.showUntrackedFiles`, `diff.ignoreSubmodules`, and `submodule.<name>.ignore`
cannot hide a change. `worktree-not-clean` lists what stopped it. Then every submodule clone in the
worktree's git directory, nested ones too, must have an empty `git stash list` and no commit that
`git log --exclude=refs/stash --all --not --remotes` prints. That is every commit that a branch, a
tag, a note, any other local ref, or HEAD reaches and no remote-tracking branch does.
`worktree-holds-local-work` lists each clone with its stashes and commits. A commit that only a
reflog still names is not caught, as with a plain removal.

A checks file is a JSON object that maps a batch name to a list of checks, each
`{"cwd": "<directory inside the worktree>", "command": "<command>"}`. `cwd` defaults to `.`. `open`
runs a batch's checks in order and stops at the first failure. A batch with no checks of its own
runs the run's `--check-command` at the worktree root. A monorepo batch names the directory whose
Makefile covers the paths it touches.

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
     "merge_method": "MERGE", "required_checks": ["ci"], "auto_merge": true,
     "delete_branch_on_merge": true,
     "check_command": "make ci", "review_policy": "...", "deadline": "<ISO 8601>",
     "topic": "<topic>", "worktrees": "<dir>", "branch_prefix": "agent/",
     "batches": {"<name>": {"status": "not-started", "branch": null, "worktree": null, "start": null,
                            "picked": false, "checked_head": null, "pushed_head": null, "pr": null,
                            "checks": null}}}

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
from pathlib import Path, PurePosixPath
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


# -- submodules --------------------------------------------------------------------------------
#
# A new worktree starts with every submodule directory empty. The checks would then run beside
# nothing, and never test the submodule's code. A bumped pointer also reaches the mainline only if
# the commit it names is on the submodule's remote. A clone of the mainline cannot fetch it
# otherwise.


GITLINK = "160000"


def error_of(result: subprocess.CompletedProcess[str]) -> str | None:
    """Return git's error text for a failed command, or None when it succeeded."""
    return None if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip())


def populate_submodules(worktree: Path) -> str | None:
    """Check each submodule out at the commit the worktree's head records.

    Return git's error on failure.
    """
    if not (worktree / ".gitmodules").is_file():
        return None
    return error_of(git(["submodule", "update", "--init", "--recursive"], worktree, check=False))


def changed_gitlinks(worktree: Path, start: str, head: str) -> dict[str, str]:
    """Map each submodule path the batch bumped or added to the commit it now names.

    `diff.ignoreSubmodules` and a submodule's `ignore` setting in `.gitmodules` can hide a gitlink
    from diff. The explicit option overrides both, so a bumped pointer is never skipped.
    """
    fields = git(["diff", "--raw", "--no-renames", "--no-abbrev", "--ignore-submodules=none", "-z", start, head],
                 worktree).stdout.split("\0")
    links = {}
    for meta, path in zip(fields[0::2], fields[1::2]):
        # ":<old mode> <new mode> <old sha> <new sha> <status>"
        _, new_mode, _, new_sha, _ = meta.lstrip(":").split()
        if new_mode == GITLINK:
            links[path] = new_sha
    return links


def missing_on_remote(worktree: Path, links: dict[str, str]) -> list[dict[str, Any]]:
    """List the bumped pointers whose commit no branch or tag of the submodule's remote holds."""
    missing = []
    for path, commit in sorted(links.items()):
        sub = worktree / path
        url = None
        on_remote = False
        if (sub / ".git").exists():
            url = out(["remote", "get-url", "origin"], sub)
            git(["fetch", "--quiet", "origin"], sub)
            if git(["cat-file", "-e", f"{commit}^{{commit}}"], sub, check=False).returncode == 0:
                held = out(["for-each-ref", "--contains", commit, "--format=%(refname)",
                            "refs/remotes/origin", "refs/tags"], sub)
                on_remote = bool(held)
        if not on_remote:
            missing.append({"path": path, "commit": commit, "url": url})
    return missing


def uncloned(worktree: Path, links: dict[str, str]) -> list[str]:
    """List the bumped submodule paths with no clone, which nothing can check against a remote."""
    return sorted(path for path in links if not (worktree / path / ".git").exists())


def not_on_remote(worktree: Path, missing: list[dict[str, Any]]) -> Stop:
    where = "; ".join(f"{m['path']} points at {m['commit'][:12]}, which {m['url'] or 'its remote'} does not hold"
                      for m in missing)
    return Stop("submodule-commit-not-on-remote", worktree=str(worktree), submodules=missing,
                message=f"{where}. Land that commit in the submodule's own repository first, then re-run the command")


def submodules_ready(worktree: Path, start: str, head: str) -> None:
    """Populate the worktree's submodules, or stop for the coordinator, before any check runs."""
    failure = populate_submodules(worktree)
    links = changed_gitlinks(worktree, start, head)

    # A failure that left a bumped submodule with no clone is a network or auth error. The empty
    # directory says nothing about the commit, so the failure is the stop. A failed checkout in a
    # clone that exists can mean the commit is missing, so that case takes the remote check first.
    if failure and uncloned(worktree, links):
        raise Stop("submodule-update-failed", worktree=str(worktree), message=failure)

    missing = missing_on_remote(worktree, links)
    if missing:
        raise not_on_remote(worktree, missing)
    if failure:
        raise Stop("submodule-update-failed", worktree=str(worktree), message=failure)


def submodules(args: argparse.Namespace) -> dict[str, Any]:
    """Check the submodule pointers a range bumps, before any batch exists.

    A pointer's commit can fail to check out at a later segment of the range, so this clones only
    the submodules the range bumps and ignores a failed checkout. Only a commit the remote holds
    counts. A clone that fails is not a failed checkout, and it stops the command.
    """
    worktree = Path(args.worktree)
    links = changed_gitlinks(worktree, args.base, args.tip)
    if links:
        failure = error_of(git(["submodule", "update", "--init", "--", *sorted(links)], worktree, check=False))
        if failure and uncloned(worktree, links):
            raise Stop("submodule-update-failed", worktree=str(worktree), message=failure)
    missing = missing_on_remote(worktree, links)
    if missing:
        raise not_on_remote(worktree, missing)
    return {"event": "submodules-on-remote", "gitlinks": links}


def submodule_clones(modules: Path) -> list[Path]:
    """List the git directory of every submodule clone under `modules`, nested ones included.

    A directory with no HEAD is a namespace for a submodule whose name holds a slash. A clone keeps
    the clones of its own submodules in its own `modules` directory.
    """
    found = []
    for child in sorted(modules.iterdir()):
        if not child.is_dir():
            continue
        if (child / "HEAD").is_file() and (child / "objects").is_dir():
            found.append(child)
            if (child / "modules").is_dir():
                found.extend(submodule_clones(child / "modules"))
        else:
            found.extend(submodule_clones(child))
    return found


def clone_label(clone: Path, modules: Path, worktree: Path) -> str:
    """Name a clone by its path in the worktree, or by its name under `modules` without one."""
    result = git(["config", "--file", str(clone / "config"), "core.worktree"], worktree, check=False)
    if result.returncode == 0 and result.stdout.strip():
        with contextlib.suppress(ValueError):
            return (clone / result.stdout.strip()).resolve().relative_to(worktree.resolve()).as_posix()
    return clone.relative_to(modules).as_posix()


def local_work(worktree: Path, git_dir: Path) -> list[dict[str, Any]]:
    """List the stashes and unpushed commits that only the worktree's submodule clones hold.

    The walk covers every clone in the git directory, not the submodules git lists. A deinitialized
    submodule leaves its clone behind, and removing the worktree deletes it. An unpushed commit is
    one that any local ref or HEAD reaches and no remote-tracking branch does. That covers
    branches, tags, notes, and every other ref outside `refs/remotes`. The stash ref is left out
    because `stash list` already reports each stash. Counting its commits too would list every
    stash twice, once as a stash and once as two commits.
    """
    modules = git_dir / "modules"
    work = []
    for clone in submodule_clones(modules):
        stashes = out(["--git-dir", str(clone), "stash", "list"], worktree).splitlines()
        commits = out(["--git-dir", str(clone), "log", "--exclude=refs/stash", "--all", "--not", "--remotes",
                       "--format=%h %s"], worktree).splitlines()
        if stashes or commits:
            work.append({"submodule": clone_label(clone, modules, worktree), "stashes": stashes, "commits": commits})
    return work


STATUS = ["status", "--porcelain", "--no-renames", "--untracked-files=normal", "--ignore-submodules=none"]


def uncommitted(worktree: Path) -> list[str]:
    """List the changes in the worktree and in every submodule checked out under it.

    The user's git config can hide a change from `git status`. `status.showUntrackedFiles` hides
    untracked files. `diff.ignoreSubmodules` and a submodule's `ignore` setting hide a submodule's
    changes. The options in STATUS override them, but only for the repository the command runs in.
    Git does not hand them to the status it runs inside a submodule. So each submodule, nested ones
    included, runs its own, and a line from one carries its path.
    """
    lines = git(STATUS, worktree).stdout.splitlines()
    paths = git(["submodule", "foreach", "--quiet", "--recursive", "echo $displaypath"], worktree).stdout.splitlines()
    for path in paths:
        lines.extend(f"{line[:3]}{path}/{line[3:]}" for line in git(STATUS, worktree / path).stdout.splitlines())
    return lines


def remove_worktree(root: Path, worktree: Path) -> None:
    """Remove a merged batch's worktree.

    Git refuses `git worktree remove` for any worktree that holds submodules, clean or not, because
    its git directory keeps their clones. The forced removal deletes those clones. A clean status,
    submodules included, does not see a stash or a commit that only a clone holds. So the removal is
    forced only once the status is clean and no clone holds either.
    """
    git_dir = Path(out(["rev-parse", "--absolute-git-dir"], worktree))
    if not (git_dir / "modules").is_dir():
        git(["worktree", "remove", str(worktree)], root)
        return

    dirty = uncommitted(worktree)
    if dirty:
        raise Stop("worktree-not-clean", worktree=str(worktree), status=dirty)

    work = local_work(worktree, git_dir)
    if work:
        where = "; ".join(f"{w['submodule']} holds {len(w['stashes'])} stash(es) and {len(w['commits'])} commit(s) "
                          "no remote has" for w in work)
        raise Stop("worktree-holds-local-work", worktree=str(worktree), work=work,
                   message=f"removing the worktree would delete work only its submodules hold: {where}. "
                           "Push the commits and apply or drop the stashes, then re-run the command")
    git(["worktree", "remove", "--force", str(worktree)], root)


# -- checks ------------------------------------------------------------------------------------


def parse_checks(path: str, plan: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Read a checks file: each batch name mapped to its checks.

    Each check runs in a directory of its batch's worktree.
    """
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise RunError(f"cannot read checks file {path}: {e}") from e
    if not isinstance(raw, dict):
        raise RunError(f"{path} must hold an object that maps batch names to lists of checks")

    names = {b["name"] for b in plan["batches"]}
    parsed: dict[str, list[dict[str, str]]] = {}
    for name, checks in raw.items():
        if name not in names:
            raise RunError(f"{path}: the plan has no batch {name}")
        if not isinstance(checks, list) or not checks:
            raise RunError(f"{path}: batch {name} needs at least one check")

        parsed[name] = []
        for check in checks:
            if not isinstance(check, dict):
                raise RunError(f"{path}: every check in batch {name} must be an object with a command")
            command, cwd = check.get("command"), check.get("cwd", ".")
            if not isinstance(command, str) or not command.strip():
                raise RunError(f"{path}: every check in batch {name} needs a command")
            if not isinstance(cwd, str) or PurePosixPath(cwd).is_absolute() or ".." in PurePosixPath(cwd).parts:
                raise RunError(f"{path}: the cwd of a check in batch {name} must be a directory inside the worktree")
            parsed[name].append({"cwd": PurePosixPath(cwd).as_posix(), "command": command})
    return parsed


def checks_of(run: dict[str, Any], name: str) -> list[dict[str, str]]:
    return run["batches"][name].get("checks") or [{"cwd": ".", "command": run["check_command"]}]


def run_all_checks(run: dict[str, Any], name: str, worktree: Path, log: Path,
                   runner: Callable[[str, Path, Path], int]) -> None:
    """Run the batch's checks in order, and stop at the first one that fails."""
    for i, check in enumerate(checks_of(run, name)):
        where = worktree / check["cwd"]
        if not where.is_dir():
            raise Stop("check-dir-missing", cwd=check["cwd"], worktree=str(worktree))

        check_log = log if i == 0 else log.with_name(f"{log.stem}-{i}{log.suffix}")
        code = runner(check["command"], where, check_log)
        if code != 0:
            raise Stop("local-checks-failed", code=code, cwd=check["cwd"], command=check["command"],
                       log=str(check_log), worktree=str(worktree))


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

    checks = parse_checks(args.checks_file, plan) if args.checks_file else {}

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
                                "picked": False, "checked_head": None, "pushed_head": None, "pr": None,
                                "checks": checks.get(b["name"])}
                    for b in plan["batches"]},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        write(path, run)
    return {"run": str(path), "watch_state": str(watch_file(path)), "ready": ready(run)}


def set_check_command(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.run)
    load(path)

    # An open batch's head passed the old command. Clearing checked_head makes the next open rerun the checks
    # on it. pushed_head stays, so a head that only needs rechecking is not pushed again.
    with locked(path):
        run = load(path)
        run["check_command"] = args.check_command
        recheck = sorted(n for n, b in run["batches"].items()
                         if b["status"] == "open" and b["checked_head"] and not b.get("checks"))
        for name in recheck:
            run["batches"][name]["checked_head"] = None
        write(path, run)
    return {"event": "check-command-set", "check_command": args.check_command, "recheck": recheck}


def set_checks(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.run)
    checks = parse_checks(args.checks_file, load(path)["plan"])

    with locked(path):
        run = load(path)
        recheck = []
        for name, batch_checks in checks.items():
            state = run["batches"][name]
            state["checks"] = batch_checks
            if state["status"] == "open" and state["checked_head"]:
                state["checked_head"] = None
                recheck.append(name)
        write(path, run)
    return {"event": "checks-set", "batches": sorted(checks), "recheck": sorted(recheck)}


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

        failure = populate_submodules(worktree)
        if failure:
            raise Stop("submodule-update-failed", worktree=str(worktree), message=failure)
    elif state["start"] is None:
        # Another run made this worktree. Without its start, nothing tells which commits are this batch's picks.
        raise Stop("worktree-without-run-record", branch=branch, worktree=str(worktree))

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
        submodules_ready(worktree, state["start"], head)
        log = path.with_name(f"{path.name[:-len('.json')]}.{name}.check.log")
        run_all_checks(run, name, worktree, log, run_checks)
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


def run_checks(command: str, cwd: Path, log: Path) -> int:
    result = subprocess.run(shlex.split(command), cwd=cwd, capture_output=True, text=True)
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
        remove_worktree(root, Path(state["worktree"]))
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
    p.add_argument("--checks-file", help="a JSON object that maps batch names to the checks each runs")
    p.add_argument("--state-dir", default="~/.local/state/coding_agent_standards")

    p = sub.add_parser("status", help="report each batch and which are ready")
    p.add_argument("--run", required=True)

    p = sub.add_parser("set-check-command", help="change a live run's local check command")
    p.add_argument("--run", required=True)
    p.add_argument("--check-command", required=True)

    p = sub.add_parser("submodules", help="check that the submodule pointers a range bumps are on their remotes")
    p.add_argument("--worktree", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--tip", required=True)

    p = sub.add_parser("set-checks", help="change the checks a live run's batches run, each in its own directory")
    p.add_argument("--run", required=True)
    p.add_argument("--checks-file", required=True)

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
        elif args.command == "set-check-command":
            result = set_check_command(args)
        elif args.command == "set-checks":
            result = set_checks(args)
        elif args.command == "submodules":
            result = submodules(args)
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
