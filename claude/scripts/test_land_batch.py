"""Tests for land_batch.py. Run: uv run --with pytest pytest claude/scripts

Git runs for real, against bare repos shaped like a fork checkout: `upstream` holds the mainline and
`origin` is the fork that batch branches push to. Only gh is faked, at pr_watch.py's helpers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import land_batch
import pr_watch

REPO = "acme/widget"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(cwd: Path, name: str, text: str, message: str) -> str:
    (cwd / name).write_text(text)
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", message)
    return git(cwd, "rev-parse", "HEAD")


@pytest.fixture(autouse=True)
def git_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_EDITOR", "true")


class FakeGitHub:
    """Stands in for gh: PR creation, listing, and merging, and the PR state fetch_pr returns."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.prs: dict[int, dict[str, Any]] = {}
        self.listed: list[dict[str, Any]] = []
        self.children: list[dict[str, Any]] = []

    def gh(self, args: list[str]) -> str:
        self.calls.append(args)
        if args[:2] == ["pr", "create"]:
            number = 40 + len(self.prs)
            self.prs[number] = self.pr(number)
            return f"https://github.com/{REPO}/pull/{number}\n"
        if args[:2] == ["pr", "list"]:
            return json.dumps(self.children if "--base" in args else self.listed)
        if args[:2] == ["pr", "merge"]:
            return ""
        raise AssertionError(f"unexpected gh call {args}")

    def pr(self, number: int, **extra: Any) -> dict[str, Any]:
        return {"number": number, "url": f"u/{number}", "state": "OPEN", "merged": False, "baseRefName": "main",
                "headRefOid": None, "autoMergeRequest": None, "mergeStateStatus": "BLOCKED", **extra}

    def set(self, number: int, checks: list[tuple[str, str, str]] = (), **fields: Any) -> None:
        nodes = [{"__typename": "CheckRun", "name": n, "status": s, "conclusion": c} for n, s, c in checks]
        self.prs[number].update(fields, commits={"nodes": [{"commit": {"statusCheckRollup": {
            "contexts": {"nodes": nodes}}}}]})

    def fetch_pr(self, owner: str, name: str, number: int) -> dict[str, Any]:
        assert f"{owner}/{name}" == REPO
        return self.prs[number]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    upstream, fork, checkout = tmp_path / "upstream.git", tmp_path / "fork.git", tmp_path / "checkout"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(upstream))
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(fork))
    git(tmp_path, "clone", "-q", str(upstream), str(checkout))
    git(checkout, "checkout", "-q", "-b", "main")
    base = commit(checkout, "a.txt", "one\n", "base")
    git(checkout, "push", "-q", "origin", "main")
    git(checkout, "remote", "rename", "origin", "upstream")
    git(checkout, "remote", "add", "origin", str(fork))
    git(checkout, "fetch", "-q", "upstream")

    git(checkout, "checkout", "-q", "-b", "work")
    first = commit(checkout, "a.txt", "one\ntwo\n", "add two")
    second = commit(checkout, "b.txt", "bee\n", "add bee")

    plan = {"base": base, "tip": second, "batches": [
        {"name": "one", "commits": [first], "after": []},
        {"name": "two", "commits": [second], "after": ["one"]}]}
    preflight = {"repo": {"nameWithOwner": REPO, "autoMergeAllowed": True, "deleteBranchOnMerge": True},
                 "protection": {"required_checks": ["ci"]}, "protection_unreadable": [],
                 "merge_methods": {"allowed": ["MERGE", "SQUASH"]},
                 "remotes": {"mainline": "upstream", "push": "origin", "push_repo": "someone/widget",
                             "head_prefix": "someone:", "fork": True}}
    files = tmp_path / "files"
    files.mkdir()
    (files / "plan.json").write_text(json.dumps(plan))
    (files / "preflight.json").write_text(json.dumps(preflight))
    (files / "title").write_text("Add two\n")
    (files / "body.md").write_text("- Adds two.\n")

    fake = FakeGitHub()
    monkeypatch.setattr(pr_watch, "gh", fake.gh)
    monkeypatch.setattr(pr_watch, "fetch_pr", fake.fetch_pr)
    checks: list[Path] = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: checks.append(wt) or 0)

    state = tmp_path / "state"
    code, result = call("init", "--plan", str(files / "plan.json"), "--preflight", str(files / "preflight.json"),
                        "--snapshot", second, "--onto", base, "--batch-tip", second, "--mainline", "main",
                        "--merge-method", "MERGE", "--topic", "work", "--worktrees", str(tmp_path / "wt"),
                        "--staging-branch", "work", "--staging-worktree", str(checkout),
                        "--check-command", "make ci", "--review-policy", "bots", "--deadline", "2099-01-01T00:00:00Z",
                        "--state-dir", str(state))
    assert code == 0, result
    return {"checkout": checkout, "upstream": upstream, "fork": fork, "files": files, "gh": fake, "checks": checks,
            "run": Path(result["run"]), "state": state, "first": first, "second": second}


def call(*argv: str) -> tuple[int, Any]:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = land_batch.main(list(argv))
    text = buffer.getvalue().strip()
    return code, json.loads(text) if text else None


def open_one(world: dict[str, Any], batch: str = "one", *extra: str) -> tuple[int, Any]:
    files = world["files"]
    return call("open", "--run", str(world["run"]), "--batch", batch, "--title-file", str(files / "title"),
                "--body-file", str(files / "body.md"), *extra)


def run_state(world: dict[str, Any]) -> dict[str, Any]:
    return json.loads(world["run"].read_text())


# -- init --------------------------------------------------------------------------------------


def test_init_writes_a_versioned_run_file_where_old_plugins_do_not_look(world):
    run = run_state(world)
    assert world["run"].parent == world["state"] / "land-branch" / "v3"
    assert run["version"] == 1 and run["remotes"]["head_prefix"] == "someone:"
    assert land_batch.ready(run) == ["one"]


def test_init_refuses_to_overwrite_a_run(world, capsys):
    run = run_state(world)
    code, _ = call("init", "--plan", str(world["files"] / "plan.json"),
                   "--preflight", str(world["files"] / "preflight.json"), "--snapshot", run["snapshot"],
                   "--onto", run["onto"], "--batch-tip", run["batch_tip"], "--mainline", "main",
                   "--merge-method", "MERGE", "--topic", "work", "--worktrees", "w", "--staging-branch", "work",
                   "--staging-worktree", str(world["checkout"]), "--check-command", "make ci",
                   "--review-policy", "bots", "--deadline", "d", "--state-dir", str(world["state"]))
    assert code == 1 and "already exists" in capsys.readouterr().err


def test_a_hand_kept_run_file_is_refused(world, capsys):
    """Catches the script misreading a run file an older plugin wrote by hand."""
    run = run_state(world)
    del run["version"]
    world["run"].write_text(json.dumps(run))
    assert call("status", "--run", str(world["run"]))[0] == 1
    assert "by hand" in capsys.readouterr().err


# -- open --------------------------------------------------------------------------------------


def test_open_lands_the_batch_on_the_fork_and_opens_the_pr_against_the_base_repo(world):
    code, result = open_one(world)
    assert code == 0 and result["event"] == "opened" and result["pr"] == 40

    branch = "agent/work/one"
    pushed = git(world["fork"], "rev-parse", f"refs/heads/{branch}")
    assert git(world["upstream"], "for-each-ref", f"refs/heads/{branch}") == ""
    assert git(world["fork"], "rev-parse", f"{pushed}^") == git(world["upstream"], "rev-parse", "main")
    assert git(world["fork"], "log", "-1", "--format=%s", pushed) == "add two"

    create = next(c for c in world["gh"].calls if c[:2] == ["pr", "create"])
    assert create[create.index("--head") + 1] == "someone:" + branch
    assert create[create.index("--repo") + 1] == REPO and create[create.index("--base") + 1] == "main"

    loop = json.loads((world["state"] / "merge-fix-loop" / "acme-widget-40.loop.json").read_text())
    assert loop["merge_into"] == "main" and loop["branch"] == branch
    assert run_state(world)["batches"]["one"]["status"] == "open"


def test_open_refuses_a_batch_whose_after_batch_has_not_merged(world):
    code, result = open_one(world, "two")
    assert code == 3 and result == {"stop": "not-ready", "batch": "two", "waiting_for": ["one"]}


def test_open_resumes_after_the_coordinator_resolves_a_conflict(world):
    """Catches a rerun that re-picks, or gives up, after a conflict the coordinator resolved by hand."""
    other = world["checkout"].parent / "other"
    git(other.parent, "clone", "-q", str(world["upstream"]), str(other))
    commit(other, "a.txt", "one\nTWO\n", "mainline moved")
    git(other, "push", "-q", "origin", "main")

    code, result = open_one(world)
    assert code == 3 and result["stop"] == "cherry-pick-conflict" and result["conflicts"] == ["a.txt"]

    worktree = Path(result["worktree"])
    assert open_one(world)[1]["stop"] == "cherry-pick-in-progress"
    (worktree / "a.txt").write_text("one\nTWO\ntwo\n")
    git(worktree, "add", "a.txt")
    git(worktree, "cherry-pick", "--continue")

    code, result = open_one(world)
    assert code == 0 and result["event"] == "opened"
    assert sum(c[:2] == ["pr", "create"] for c in world["gh"].calls) == 1


def test_open_reruns_checks_after_a_fix_and_never_pushes_a_failing_head(world, monkeypatch):
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: 2)
    code, result = open_one(world)
    assert code == 3 and result["stop"] == "local-checks-failed"
    assert git(world["fork"], "for-each-ref", "refs/heads/agent/work/one") == ""

    worktree = Path(result["worktree"])
    fixed = commit(worktree, "a.txt", "one\ntwo\nfixed\n", "fix the check")
    seen = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: seen.append(wt) or 0)
    code, result = open_one(world)
    assert code == 0 and seen == [worktree]
    assert git(world["fork"], "rev-parse", "refs/heads/agent/work/one") == fixed


def test_open_adopts_the_pr_a_crashed_run_already_opened(world):
    """Catches a duplicate PR when a run died between gh pr create and the run-file write."""
    world["gh"].listed = [{"number": 7, "url": "u/7", "headRepositoryOwner": {"login": "elsewhere"}},
                          {"number": 9, "url": "u/9", "headRepositoryOwner": {"login": "someone"}}]
    code, result = open_one(world)
    assert code == 0 and result["pr"] == 9
    assert not any(c[:2] == ["pr", "create"] for c in world["gh"].calls)


# -- merge -------------------------------------------------------------------------------------


@pytest.mark.parametrize("checks, fields, stop", [
    ([], {}, "no-checks"),
    ([("ci", "IN_PROGRESS", None)], {}, "checks-pending"),
    ([("ci", "COMPLETED", "FAILURE")], {}, "checks-failed"),
    ([("ci", "COMPLETED", "SUCCESS")], {"baseRefName": "agent/work/zero"}, "base-not-mainline"),
    ([("ci", "COMPLETED", "SUCCESS")], {"headRefOid": "0" * 40}, "head-moved"),
])
def test_merge_refuses_until_the_pushed_head_passed_its_checks(world, checks, fields, stop):
    """Catches auto-merge turned on early. On a CLEAN PR, `gh pr merge --auto` merges at once."""
    open_one(world)
    head = run_state(world)["batches"]["one"]["pushed_head"]
    world["gh"].set(40, checks, **{"headRefOid": head, **fields})
    code, result = call("merge", "--run", str(world["run"]), "--batch", "one")
    assert code == 3 and result["stop"] == stop
    assert not any(c[:2] == ["pr", "merge"] for c in world["gh"].calls)


def test_merge_turns_on_while_only_a_check_that_is_not_required_failed(world):
    """Regression: a red optional check held the batch forever, where the hand procedure merges past it."""
    open_one(world)
    head = run_state(world)["batches"]["one"]["pushed_head"]
    world["gh"].set(40, [("ci", "COMPLETED", "SUCCESS"), ("lint-docs", "COMPLETED", "FAILURE")], headRefOid=head)
    code, result = call("merge", "--run", str(world["run"]), "--batch", "one")
    assert code == 0 and result["event"] == "auto-merge-on" and result["failed_not_required"] == ["lint-docs"]


def test_unreadable_protection_counts_every_check_as_required(world):
    run = run_state(world)
    run["required_checks"] = None
    world["run"].write_text(json.dumps(run))
    open_one(world)
    head = run_state(world)["batches"]["one"]["pushed_head"]
    world["gh"].set(40, [("ci", "COMPLETED", "SUCCESS"), ("lint-docs", "COMPLETED", "FAILURE")], headRefOid=head)
    code, result = call("merge", "--run", str(world["run"]), "--batch", "one")
    assert code == 3 and result["stop"] == "checks-failed" and result["failed"] == ["lint-docs"]


def test_a_closed_pr_stops_its_batch(world):
    open_one(world)
    world["gh"].set(40, state="CLOSED")
    code, result = call("merge", "--run", str(world["run"]), "--batch", "one")
    assert code == 3 and result["stop"] == "pr-closed"
    assert run_state(world)["batches"]["one"]["status"] == "stopped"


def test_merge_turns_on_auto_merge_with_the_runs_method(world):
    open_one(world)
    head = run_state(world)["batches"]["one"]["pushed_head"]
    world["gh"].set(40, [("ci", "COMPLETED", "SUCCESS")], headRefOid=head)
    code, result = call("merge", "--run", str(world["run"]), "--batch", "one")
    assert code == 0 and result["event"] == "auto-merge-on"
    assert ["pr", "merge", "40", "--repo", REPO, "--auto", "--merge"] in world["gh"].calls


# -- finish ------------------------------------------------------------------------------------


def test_finish_refuses_a_pr_that_has_not_merged(world):
    open_one(world)
    world["gh"].set(40)
    code, result = call("finish", "--run", str(world["run"]), "--batch", "one")
    assert code == 3 and result["stop"] == "not-merged"
    assert Path(run_state(world)["batches"]["one"]["worktree"]).exists()


def test_finish_refuses_while_a_pr_is_based_on_the_branch(world):
    open_one(world)
    world["gh"].set(40, merged=True, state="MERGED")
    world["gh"].children = [{"number": 41}]
    code, result = call("finish", "--run", str(world["run"]), "--batch", "one")
    assert code == 3 and result == {"stop": "open-prs-on-branch", "batch": "one", "prs": [41]}


def test_finish_cleans_up_and_names_the_batches_it_made_ready(world):
    open_one(world)
    world["gh"].set(40, merged=True, state="MERGED")
    worktree = Path(run_state(world)["batches"]["one"]["worktree"])
    code, result = call("finish", "--run", str(world["run"]), "--batch", "one")
    assert code == 0 and result["ready"] == ["two"] and result["all_merged"] is False

    assert not worktree.exists()
    assert git(world["checkout"], "for-each-ref", "refs/heads/agent/work/one") == ""
    assert git(world["fork"], "for-each-ref", "refs/heads/agent/work/one") == ""
    assert not (world["state"] / "merge-fix-loop" / "acme-widget-40.loop.json").exists()
    assert run_state(world)["batches"]["one"]["status"] == "merged"

    code, result = call("finish", "--run", str(world["run"]), "--batch", "one")
    assert code == 3 and result["stop"] == "not-open"


def test_open_pushes_a_rebased_branch_with_a_lease_pinned_to_the_head_it_pushed(world):
    """Catches a rerun after a rebase that fails a plain push, or overwrites a push it never made."""
    open_one(world)
    worktree = Path(run_state(world)["batches"]["one"]["worktree"])
    git(worktree, "commit", "-q", "--amend", "-m", "add two, reworded")

    code, result = open_one(world)
    assert code == 0
    assert git(world["fork"], "rev-parse", "refs/heads/agent/work/one") == git(worktree, "rev-parse", "HEAD")

    other = world["checkout"].parent / "intruder"
    git(other.parent, "clone", "-q", "-b", "agent/work/one", str(world["fork"]), str(other))
    commit(other, "c.txt", "sea\n", "someone else's push")
    git(other, "push", "-q", "origin", "agent/work/one")
    intruder = git(other, "rev-parse", "HEAD")
    git(worktree, "commit", "-q", "--amend", "-m", "add two, again")

    code, result = open_one(world)
    assert code == 2 and ("stale info" in result["error"] or "rejected" in result["error"])
    assert git(world["fork"], "rev-parse", "refs/heads/agent/work/one") == intruder
