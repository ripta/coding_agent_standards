"""Tests for land_batch.py. Run: uv run --with pytest pytest claude/scripts

Git runs for real, against bare repos shaped like a fork checkout: `upstream` holds the mainline and
`origin` is the fork that batch branches push to. Only gh is faked, at pr_watch.py's helpers.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import land_batch
import pr_watch

REPO = "acme/widget"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(cwd: Path, name: str, text: str, message: str) -> str:
    (cwd / name).parent.mkdir(parents=True, exist_ok=True)
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

    # A submodule cloned from a local bare repo needs the file transport, which git blocks by default.
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")


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
def make_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., dict[str, Any]]:
    """Builds the fork-shaped checkout, optionally with a submodule the first batch bumps.

    `submodule` is None for no submodule, "pushed" when the bump targets a commit on the submodule's
    remote, and "unpushed" when it targets a commit only the checkout's own submodule clone holds.
    `nested` gives the submodule a submodule of its own, at `sub/inner`.
    """

    def make(submodule: str | None = None, nested: bool = False) -> dict[str, Any]:
        upstream, fork, checkout = tmp_path / "upstream.git", tmp_path / "fork.git", tmp_path / "checkout"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(upstream))
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(fork))
        git(tmp_path, "clone", "-q", str(upstream), str(checkout))
        git(checkout, "checkout", "-q", "-b", "main")

        extra: dict[str, Any] = {}
        if submodule:
            sub_remote, sub_work = tmp_path / "sub.git", tmp_path / "sub-work"
            git(tmp_path, "init", "-q", "--bare", "-b", "main", str(sub_remote))
            git(tmp_path, "clone", "-q", str(sub_remote), str(sub_work))
            git(sub_work, "checkout", "-q", "-b", "main")
            commit(sub_work, "lib.txt", "one\n", "lib one")
            if nested:
                inner_remote, inner_work = tmp_path / "inner.git", tmp_path / "inner-work"
                git(tmp_path, "init", "-q", "--bare", "-b", "main", str(inner_remote))
                git(tmp_path, "clone", "-q", str(inner_remote), str(inner_work))
                git(inner_work, "checkout", "-q", "-b", "main")
                commit(inner_work, "deep.txt", "deep\n", "deep one")
                git(inner_work, "push", "-q", "origin", "main")
                git(sub_work, "submodule", "add", "-q", str(inner_remote), "inner")
                git(sub_work, "commit", "-q", "-m", "add inner")
            git(sub_work, "push", "-q", "origin", "main")
            git(checkout, "submodule", "add", "-q", str(sub_remote), "sub")
            extra = {"sub_remote": sub_remote, "sub_clone": checkout / "sub"}

        base = commit(checkout, "a.txt", "one\n", "base")
        git(checkout, "push", "-q", "origin", "main")
        git(checkout, "remote", "rename", "origin", "upstream")
        git(checkout, "remote", "add", "origin", str(fork))
        git(checkout, "fetch", "-q", "upstream")

        git(checkout, "checkout", "-q", "-b", "work")
        (checkout / "apps" / "a").mkdir(parents=True)
        (checkout / "apps" / "a" / "Makefile").write_text("ci:\n")
        git(checkout, "add", "apps")
        if submodule:
            tip = commit(checkout / "sub", "lib.txt", "one\ntwo\n", "lib two")
            if submodule == "pushed":
                git(checkout / "sub", "push", "-q", "origin", "HEAD:main")
            git(checkout, "add", "sub")
            extra["sub_tip"] = tip
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
                            "--check-command", "make ci", "--review-policy", "bots",
                            "--deadline", "2099-01-01T00:00:00Z", "--state-dir", str(state))
        assert code == 0, result
        return {"checkout": checkout, "upstream": upstream, "fork": fork, "files": files, "gh": fake,
                "checks": checks, "run": Path(result["run"]), "state": state, "first": first, "second": second,
                **extra}

    return make


@pytest.fixture
def world(make_world: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    return make_world()


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


def init_with_prefix(world: dict[str, Any], prefix: str) -> tuple[int, Any]:
    files = world["files"]
    preflight = json.loads((files / "preflight.json").read_text())
    preflight["branches"] = {"prefix": prefix}
    (files / "prefixed.json").write_text(json.dumps(preflight))

    run = run_state(world)
    return call("init", "--plan", str(files / "plan.json"), "--preflight", str(files / "prefixed.json"),
                "--snapshot", run["snapshot"], "--onto", run["onto"], "--batch-tip", run["batch_tip"],
                "--mainline", "main", "--merge-method", "MERGE", "--topic", "work", "--worktrees", run["worktrees"],
                "--staging-branch", "work", "--staging-worktree", str(world["checkout"]),
                "--check-command", "make ci", "--review-policy", "bots", "--deadline", "2099-01-01T00:00:00Z",
                "--state-dir", str(world["state"] / "prefixed"))


def test_batch_branches_take_the_prefix_preflight_settled(world):
    """Catches a batch branch named under agent/ in a repo whose rulesets reject a slash."""
    code, result = init_with_prefix(world, "me.agent.")
    assert code == 0, result

    world = {**world, "run": Path(result["run"])}
    code, result = open_one(world)
    assert code == 0, result

    assert run_state(world)["batches"]["one"]["branch"] == "me.agent.work.one"
    assert git(world["fork"], "for-each-ref", "--format=%(refname)") == "refs/heads/me.agent.work.one"


def test_init_refuses_a_prefix_that_does_not_end_in_a_separator(world, capsys):
    """Catches a prefix that would glue the topic onto it, such as `meagentwork.one`."""
    assert init_with_prefix(world, "me.agent")[0] == 1
    assert "separator" in capsys.readouterr().err


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


def test_open_stops_on_a_worktree_the_run_file_did_not_record(world, monkeypatch):
    """Catches a crash on `None..HEAD` when a fresh init meets a worktree an earlier run left behind."""
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: 2)
    code, result = open_one(world)
    assert code == 3 and result["stop"] == "local-checks-failed"
    worktree = result["worktree"]

    run = run_state(world)
    run["batches"]["one"] = {"status": "not-started", "branch": None, "worktree": None, "start": None,
                             "picked": False, "checked_head": None, "pushed_head": None, "pr": None}
    world["run"].write_text(json.dumps(run))

    for extra in ((), ("--picked",)):
        code, result = open_one(world, "one", *extra)
        assert code == 3, result
        assert result == {"stop": "worktree-without-run-record", "batch": "one", "branch": "agent/work/one",
                          "worktree": worktree}


def test_a_new_check_command_reruns_the_checks_on_an_open_batch(world, monkeypatch):
    """Catches a changed check command that open skips because the head already passed the old one."""
    code, result = open_one(world)
    assert code == 0 and result["event"] == "opened"
    pushed = git(world["fork"], "rev-parse", "refs/heads/agent/work/one")

    code, result = call("set-check-command", "--run", str(world["run"]), "--check-command", "make test")
    assert code == 0 and result == {"event": "check-command-set", "check_command": "make test", "recheck": ["one"]}

    seen = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: seen.append(command) or 0)
    code, result = open_one(world)
    assert code == 0 and result["event"] == "open" and seen == ["make test"]
    assert git(world["fork"], "rev-parse", "refs/heads/agent/work/one") == pushed


def test_open_adopts_the_pr_a_crashed_run_already_opened(world):
    """Catches a duplicate PR when a run died between gh pr create and the run-file write."""
    world["gh"].listed = [{"number": 7, "url": "u/7", "headRepositoryOwner": {"login": "elsewhere"}},
                          {"number": 9, "url": "u/9", "headRepositoryOwner": {"login": "someone"}}]
    code, result = open_one(world)
    assert code == 0 and result["pr"] == 9
    assert not any(c[:2] == ["pr", "create"] for c in world["gh"].calls)


# -- submodules --------------------------------------------------------------------------------


def test_open_populates_submodules_at_the_batch_pointer_before_the_checks(make_world, monkeypatch):
    """Catches checks that run beside an empty submodule directory, so they never test the submodule's code."""
    world = make_world(submodule="pushed")
    seen = []

    def check(command, wt, log):
        lib = wt / "sub" / "lib.txt"
        seen.append(lib.read_text() if lib.exists() else None)
        return 0

    monkeypatch.setattr(land_batch, "run_checks", check)
    code, result = open_one(world)
    assert code == 0, result
    assert seen == ["one\ntwo\n"]


def test_open_stops_on_a_submodule_commit_that_is_not_on_its_remote_and_resumes_once_it_is(make_world, monkeypatch):
    """Catches a pointer bump landing in the mainline that no clone can fetch. A local run cannot see it."""
    world = make_world(submodule="unpushed")
    ran = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: ran.append(wt) or 0)

    code, result = open_one(world)
    assert code == 3 and result["stop"] == "submodule-commit-not-on-remote"
    assert result["submodules"] == [{"path": "sub", "commit": world["sub_tip"], "url": str(world["sub_remote"])}]
    assert "sub" in result["message"] and str(world["sub_remote"]) in result["message"]
    assert ran == []
    assert git(world["fork"], "for-each-ref", "refs/heads/agent/work/one") == ""

    git(world["sub_clone"], "push", "-q", "origin", "HEAD:main")
    code, result = open_one(world)
    assert code == 0 and result["event"] == "opened"
    assert len(ran) == 1


def test_open_stops_when_the_submodule_update_fails_for_a_commit_the_remote_does_hold(make_world, monkeypatch):
    """Catches a failed submodule update read as a missing commit, or ignored so the checks run on stale code."""
    world = make_world(submodule="pushed")
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: 2)
    code, result = open_one(world)
    assert code == 3 and result["stop"] == "local-checks-failed"

    # A local edit in the submodule blocks the checkout of the pointer, as a coordinator's stray edit would.
    worktree = Path(result["worktree"])
    git(worktree / "sub", "checkout", "-q", "HEAD~1")
    (worktree / "sub" / "lib.txt").write_text("stray\n")
    ran = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: ran.append(wt) or 0)

    code, result = open_one(world)
    assert code == 3 and result["stop"] == "submodule-update-failed"
    assert "lib.txt" in result["message"] and ran == []
    assert run_state(world)["batches"]["one"]["checked_head"] is None

    git(worktree / "sub", "checkout", "-q", "--", "lib.txt")
    code, result = open_one(world)
    assert code == 0 and result["event"] == "opened" and len(ran) == 1


def test_the_submodules_command_checks_a_range_before_any_batch_exists(make_world):
    """Catches a range whose pointer bumps the staging checkout can see, but no remote holds."""
    world = make_world(submodule="unpushed")
    run = run_state(world)
    args = ("submodules", "--worktree", str(world["checkout"]), "--base", run["onto"], "--tip", run["batch_tip"])

    code, result = call(*args)
    assert code == 3 and result["stop"] == "submodule-commit-not-on-remote"
    assert result["submodules"] == [{"path": "sub", "commit": world["sub_tip"], "url": str(world["sub_remote"])}]

    git(world["sub_clone"], "push", "-q", "origin", "HEAD:main")
    code, result = call(*args)
    assert code == 0 and result == {"event": "submodules-on-remote", "gitlinks": {"sub": world["sub_tip"]}}


@pytest.mark.parametrize("ignore", ["diff.ignoreSubmodules", ".gitmodules"])
def test_the_pointer_check_sees_a_bump_that_the_config_asks_diff_to_ignore(make_world, ignore):
    """Catches `ignore = all` hiding the bumped pointer, so an unpushed commit passes the guard.

    The setting comes from the user's git config, or from the repo's .gitmodules.
    """
    world = make_world(submodule="unpushed")
    if ignore == "diff.ignoreSubmodules":
        git(world["checkout"], "config", "diff.ignoreSubmodules", "all")
    else:
        git(world["checkout"], "config", "-f", ".gitmodules", "submodule.sub.ignore", "all")

    run = run_state(world)
    code, result = call("submodules", "--worktree", str(world["checkout"]), "--base", run["onto"],
                        "--tip", run["batch_tip"])
    assert code == 3 and result["stop"] == "submodule-commit-not-on-remote", result
    assert [m["path"] for m in result["submodules"]] == ["sub"]


def test_open_reports_a_submodule_that_failed_to_clone_as_a_failed_update(make_world, monkeypatch):
    """Catches a clone that failed on the network or on auth, reported as a missing commit.

    The first stop is at worktree creation. The rerun reaches the pointer check, which used to read
    the empty submodule directory as a missing commit. It cannot prove how git words each kind of
    clone failure.
    """
    world = make_world(submodule="pushed")
    ran = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: ran.append(wt) or 0)
    gone = world["sub_remote"].with_name("sub-gone.git")
    world["sub_remote"].rename(gone)

    for attempt in range(2):
        code, result = open_one(world)
        assert code == 3 and result["stop"] == "submodule-update-failed", (attempt, result)
        assert str(world["sub_remote"]) in result["message"]
    assert ran == [] and run_state(world)["batches"]["one"]["checked_head"] is None

    gone.rename(world["sub_remote"])
    code, result = open_one(world)
    assert code == 0 and result["event"] == "opened" and len(ran) == 1


def test_the_submodules_command_reports_a_failed_clone_not_a_missing_commit(make_world, tmp_path):
    """Catches the same misreport when a range is checked where the submodule was never cloned."""
    world = make_world(submodule="pushed")
    fresh = tmp_path / "fresh"
    git(tmp_path, "clone", "-q", str(world["checkout"]), str(fresh))
    world["sub_remote"].rename(world["sub_remote"].with_name("sub-gone.git"))

    run = run_state(world)
    code, result = call("submodules", "--worktree", str(fresh), "--base", run["onto"], "--tip", run["batch_tip"])
    assert code == 3 and result["stop"] == "submodule-update-failed", result
    assert str(world["sub_remote"]) in result["message"]


def test_the_submodules_command_passes_a_range_that_bumps_none(world):
    run = run_state(world)
    code, result = call("submodules", "--worktree", str(world["checkout"]), "--base", run["onto"],
                        "--tip", run["batch_tip"])
    assert code == 0 and result == {"event": "submodules-on-remote", "gitlinks": {}}


def test_finish_removes_a_worktree_that_holds_submodules(make_world):
    """Catches `git worktree remove` refusing a worktree with a populated submodule, whatever its state."""
    world = make_world(submodule="pushed")
    assert open_one(world)[0] == 0
    worktree = Path(run_state(world)["batches"]["one"]["worktree"])
    assert (worktree / "sub" / "lib.txt").exists()

    world["gh"].set(40, merged=True, state="MERGED")
    code, result = call("finish", "--run", str(world["run"]), "--batch", "one")
    assert code == 0, result
    assert not worktree.exists()
    assert git(world["checkout"], "for-each-ref", "refs/heads/agent/work/one") == ""


def test_finish_keeps_a_worktree_whose_submodule_holds_edits(make_world):
    """Catches the forced removal that a submodule needs discarding work that plain removal would refuse."""
    world = make_world(submodule="pushed")
    assert open_one(world)[0] == 0
    worktree = Path(run_state(world)["batches"]["one"]["worktree"])
    (worktree / "sub" / "lib.txt").write_text("unsaved\n")

    world["gh"].set(40, merged=True, state="MERGED")
    code, result = call("finish", "--run", str(world["run"]), "--batch", "one")
    assert code == 3 and result["stop"] == "worktree-not-clean"
    assert any("sub" in line for line in result["status"])
    assert (worktree / "sub" / "lib.txt").read_text() == "unsaved\n"
    assert run_state(world)["batches"]["one"]["status"] == "open"


def merged_worktree(world: dict[str, Any]) -> Path:
    assert open_one(world)[0] == 0
    world["gh"].set(40, merged=True, state="MERGED")
    return Path(run_state(world)["batches"]["one"]["worktree"])


def finish_one(world: dict[str, Any]) -> tuple[int, Any]:
    return call("finish", "--run", str(world["run"]), "--batch", "one")


def stash_an_edit(clone: Path, name: str) -> None:
    (clone / name).write_text("stashed\n")
    git(clone, "stash", "-q")


def commit_on_a_local_branch(clone: Path, name: str) -> None:
    pointer = git(clone, "rev-parse", "HEAD")
    git(clone, "checkout", "-q", "-b", "local-only")
    commit(clone, name, "local\n", "local only")
    git(clone, "checkout", "-q", "--detach", pointer)


def commit_on_a_local_tag(clone: Path, name: str) -> None:
    pointer = git(clone, "rev-parse", "HEAD")
    commit(clone, name, "local\n", "local only")
    git(clone, "tag", "local-only")
    git(clone, "checkout", "-q", "--detach", pointer)


def commit_on_another_local_ref(clone: Path, name: str) -> None:
    pointer = git(clone, "rev-parse", "HEAD")
    git(clone, "update-ref", "refs/saved/local-only", commit(clone, name, "local\n", "local only"))
    git(clone, "checkout", "-q", "--detach", pointer)


def note_on_a_commit(clone: Path, name: str) -> None:
    git(clone, "notes", "add", "-m", "local only", "HEAD")


def assert_kept_for_local_work(world: dict[str, Any], worktree: Path, where: str, kind: str) -> None:
    code, result = finish_one(world)
    assert code == 3 and result["stop"] == "worktree-holds-local-work", result
    [found] = result["work"]
    assert found["submodule"] == where and found[kind] and not found["stashes" if kind == "commits" else "commits"]
    assert where in result["message"]
    assert worktree.exists() and run_state(world)["batches"]["one"]["status"] == "open"


@pytest.mark.parametrize("nested, where, name", [(False, "sub", "lib.txt"), (True, "sub/inner", "deep.txt")])
@pytest.mark.parametrize("hide, kind", [(stash_an_edit, "stashes"), (commit_on_a_local_branch, "commits")])
def test_finish_keeps_a_worktree_whose_submodule_holds_work_a_clean_status_cannot_see(
    make_world, nested, where, name, hide, kind
):
    """Catches the forced removal deleting a stash or a local-only commit in a submodule.

    The submodule may be nested. The status check passes on both, and plain removal is refused
    whatever the state. A stash must not also show as a commit, which is how a guard that counts
    every ref would report it. It cannot prove that every kind of unreferenced work is caught. A
    commit that only a reflog still names is not.
    """
    world = make_world(submodule="pushed", nested=nested)
    worktree = merged_worktree(world)
    hide(worktree / where, name)
    assert git(worktree, "status", "--porcelain", "--ignore-submodules=none") == ""

    assert_kept_for_local_work(world, worktree, where, kind)


@pytest.mark.parametrize("hide", [commit_on_a_local_tag, commit_on_another_local_ref, note_on_a_commit])
def test_finish_keeps_a_worktree_whose_submodule_holds_a_commit_only_a_local_ref_other_than_a_branch_reaches(
    make_world, hide
):
    """Catches a guard that reads only branches, and deletes a commit that a tag, a note, or another ref keeps.

    The commit sits on no branch, and the clone's HEAD has moved off it. The status is clean, and
    the unpushed work lives only in the clone the forced removal deletes.
    """
    world = make_world(submodule="pushed")
    worktree = merged_worktree(world)
    hide(worktree / "sub", "lib.txt")
    assert git(worktree, "status", "--porcelain", "--ignore-submodules=none") == ""
    assert git(worktree / "sub", "branch", "--list", "local-only") == ""

    assert_kept_for_local_work(world, worktree, "sub", "commits")


def test_finish_keeps_a_worktree_whose_deinitialized_submodule_still_holds_a_stash(make_world):
    """Catches a guard that walks only the submodules git lists, and misses a clone left behind.

    Deinitializing empties the submodule's directory and leaves a clean status. The clone and its
    stash stay in the git directory that the forced removal deletes.
    """
    world = make_world(submodule="pushed")
    worktree = merged_worktree(world)
    stash_an_edit(worktree / "sub", "lib.txt")
    git(worktree, "submodule", "deinit", "-q", "-f", "sub")
    assert git(worktree, "status", "--porcelain", "--ignore-submodules=none") == ""

    code, result = finish_one(world)
    assert code == 3 and result["stop"] == "worktree-holds-local-work", result
    assert [w["submodule"] for w in result["work"]] == ["sub"] and result["work"][0]["stashes"]
    assert worktree.exists()


def leave_a_file(clone: Path, name: str) -> None:
    (clone / name).write_text("mine\n")


def edit_a_tracked_file(clone: Path, name: str) -> None:
    (clone / name).write_text("edited\n")


@pytest.mark.parametrize(
    "setting, value, where, name, change",
    [
        ("status.showUntrackedFiles", "no", ".", "scratch.txt", leave_a_file),
        ("status.showUntrackedFiles", "no", "sub", "scratch.txt", leave_a_file),
        ("status.showUntrackedFiles", "no", "sub/inner", "scratch.txt", leave_a_file),
        ("diff.ignoreSubmodules", "all", "sub/inner", "deep.txt", edit_a_tracked_file),
        ("submodule.inner.ignore", "all", "sub/inner", "deep.txt", edit_a_tracked_file),
    ],
)
def test_finish_keeps_a_worktree_with_a_change_the_users_git_config_hides_from_status(
    make_world, monkeypatch, tmp_path, setting, value, where, name, change
):
    """Catches the forced removal deleting a file or an edit that the user's own git config keeps out of status.

    `status.showUntrackedFiles` hides an untracked file in the worktree and in each submodule.
    `diff.ignoreSubmodules` and a submodule's `ignore` setting hide a change in a nested submodule,
    since the status option that overrides them reaches only the first level. It cannot prove that
    no other setting hides a change.
    """
    world = make_world(submodule="pushed", nested=True)
    worktree = merged_worktree(world)

    config = tmp_path / "user.gitconfig"
    git(tmp_path, "config", "--file", str(config), setting, value)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))

    change(worktree / where, name)
    assert git(worktree, "status", "--porcelain", "--ignore-submodules=none") == "", "the setting must hide it"

    code, result = finish_one(world)
    assert code == 3 and result["stop"] == "worktree-not-clean", result
    assert any(name in line for line in result["status"]), result["status"]
    assert (worktree / where / name).exists()
    assert run_state(world)["batches"]["one"]["status"] == "open"


# -- per-batch checks --------------------------------------------------------------------------


def checks_file(world: dict[str, Any], mapping: dict[str, Any]) -> Path:
    path = world["files"] / "checks.json"
    path.write_text(json.dumps(mapping))
    return path


def test_open_runs_each_check_the_batch_names_in_its_own_directory(world, monkeypatch):
    """Catches a monorepo batch that runs the root's checks, or another app's, instead of its own."""
    path = checks_file(world, {"one": [{"cwd": "apps/a", "command": "make ci"},
                                       {"cwd": ".", "command": "make lint-docs"}]})
    code, result = call("set-checks", "--run", str(world["run"]), "--checks-file", str(path))
    assert code == 0 and result == {"event": "checks-set", "batches": ["one"], "recheck": []}

    seen = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: seen.append((command, wt, log.name)) or 0)
    code, result = open_one(world)
    assert code == 0, result

    worktree = Path(run_state(world)["batches"]["one"]["worktree"])
    assert [(c, wt) for c, wt, _ in seen] == [("make ci", worktree / "apps" / "a"), ("make lint-docs", worktree)]
    assert len({log for _, _, log in seen}) == 2


def test_a_batch_without_its_own_checks_runs_the_runs_command_at_the_root(world, monkeypatch):
    seen = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: seen.append((command, wt)) or 0)
    assert open_one(world)[0] == 0
    worktree = Path(run_state(world)["batches"]["one"]["worktree"])
    assert seen == [("make ci", worktree)]


def test_a_failing_check_stops_the_batch_and_names_the_check_that_failed(world, monkeypatch):
    path = checks_file(world, {"one": [{"cwd": "apps/a", "command": "make ci"},
                                       {"cwd": ".", "command": "make lint-docs"}]})
    assert call("set-checks", "--run", str(world["run"]), "--checks-file", str(path))[0] == 0

    seen = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: seen.append(command) or 2)
    code, result = open_one(world)
    assert code == 3 and result["stop"] == "local-checks-failed" and result["code"] == 2
    assert result["cwd"] == "apps/a" and result["command"] == "make ci"
    assert seen == ["make ci"]


def test_a_check_directory_the_head_lacks_is_a_stop_not_a_crash(world):
    path = checks_file(world, {"one": [{"cwd": "apps/missing", "command": "make ci"}]})
    assert call("set-checks", "--run", str(world["run"]), "--checks-file", str(path))[0] == 0

    code, result = open_one(world)
    assert code == 3 and result["stop"] == "check-dir-missing" and result["cwd"] == "apps/missing"
    assert git(world["fork"], "for-each-ref", "refs/heads/agent/work/one") == ""


@pytest.mark.parametrize("mapping, message", [
    ({"nine": [{"cwd": ".", "command": "make ci"}]}, "no batch nine"),
    ({"one": []}, "at least one check"),
    ({"one": [{"cwd": "../elsewhere", "command": "make ci"}]}, "inside the worktree"),
    ({"one": [{"cwd": "/etc", "command": "make ci"}]}, "inside the worktree"),
    ({"one": [{"cwd": ".", "command": ""}]}, "command"),
])
def test_checks_that_name_no_batch_or_leave_the_worktree_are_refused(world, capsys, mapping, message):
    """Catches a checks file that runs a command outside the batch's own worktree."""
    path = checks_file(world, mapping)
    assert call("set-checks", "--run", str(world["run"]), "--checks-file", str(path))[0] == 1
    assert message in capsys.readouterr().err
    assert run_state(world)["batches"]["one"]["checks"] is None


def test_new_checks_rerun_an_open_batch_but_a_new_run_command_leaves_it_alone(world, monkeypatch):
    """Catches a run-wide command change that reruns, or skips rerunning, a batch with checks of its own."""
    path = checks_file(world, {"one": [{"cwd": "apps/a", "command": "make ci"}]})
    assert call("set-checks", "--run", str(world["run"]), "--checks-file", str(path))[0] == 0
    assert open_one(world)[0] == 0

    code, result = call("set-check-command", "--run", str(world["run"]), "--check-command", "make test")
    assert code == 0 and result["recheck"] == []

    path = checks_file(world, {"one": [{"cwd": "apps/a", "command": "make lint"}]})
    code, result = call("set-checks", "--run", str(world["run"]), "--checks-file", str(path))
    assert code == 0 and result["recheck"] == ["one"]

    seen = []
    monkeypatch.setattr(land_batch, "run_checks", lambda command, wt, log: seen.append(command) or 0)
    assert open_one(world)[1]["event"] == "open" and seen == ["make lint"]


def test_init_takes_the_per_batch_checks(world, tmp_path):
    run = run_state(world)
    path = checks_file(world, {"two": [{"cwd": "apps/a", "command": "make ci"}]})
    code, result = call("init", "--plan", str(world["files"] / "plan.json"),
                        "--preflight", str(world["files"] / "preflight.json"), "--snapshot", run["snapshot"],
                        "--onto", run["onto"], "--batch-tip", run["batch_tip"], "--mainline", "main",
                        "--merge-method", "MERGE", "--topic", "work", "--worktrees", run["worktrees"],
                        "--staging-branch", "work", "--staging-worktree", str(world["checkout"]),
                        "--check-command", "make ci", "--review-policy", "bots",
                        "--deadline", "2099-01-01T00:00:00Z", "--checks-file", str(path),
                        "--state-dir", str(tmp_path / "second-state"))
    assert code == 0, result
    batches = json.loads(Path(result["run"]).read_text())["batches"]
    assert batches["one"]["checks"] is None
    assert batches["two"]["checks"] == [{"cwd": "apps/a", "command": "make ci"}]


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
