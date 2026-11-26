"""Tests for sync_scope.py. Run: uv run --with pytest pytest claude/skills/tracker-sync"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import sync_scope


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit_staged(repo: Path, message: str, when: str | None = None) -> str:
    """Commit what is staged. `when` sets both commit dates, as an ISO 8601 string."""
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else None
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return _git(repo, "rev-parse", "HEAD")


def _commit(repo: Path, path: str, message: str, when: str | None = None) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as fh:
        fh.write(f"{message}\n")
    _git(repo, "add", path)
    return _commit_staged(repo, message, when)


def _init(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "T")
    _git(path, "config", "commit.gpgsign", "false")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "remote", "add", "origin", "git@github.com:Acme/Mono.git")
    _commit(repo, "apps/a/README.md", "init a")
    _commit(repo, "apps/b/README.md", "init b")
    return repo


@pytest.fixture(autouse=True)
def no_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every test off the network and off the real home. A test that wants gh's answer sets its own."""
    monkeypatch.setattr(sync_scope, "gh_base_repo", lambda root: None)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def save_target(tmp_path: Path, key: str, target: str) -> None:
    path = tmp_path / "home" / ".config" / "coding_agent_standards" / "pr-targets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"repos": {key: {"target": target}}}))


@pytest.fixture
def config(tmp_path: Path) -> Path:
    return tmp_path / "cfg" / "tracker-sync.json"


def run(capsys, config: Path, repo: Path, *argv: str) -> tuple[int, dict | None, str]:
    code = sync_scope.main(["--config", str(config), "--repo-dir", str(repo), *argv])
    out, err = capsys.readouterr()
    return code, (json.loads(out) if code == 0 else None), err


def setup_jira(capsys, config: Path, repo: Path) -> None:
    run(
        capsys,
        config,
        repo,
        "add-tracker",
        "--name",
        "j",
        "--type",
        "jira",
        "--assignee",
        "acct-1",
        "--site",
        "acme.atlassian.net",
    )


@pytest.mark.parametrize(
    ("url", "want"),
    [
        ("git@github.com:Acme/Mono.git", "github.com/Acme/Mono"),
        ("https://github.com/Acme/Mono.git", "github.com/Acme/Mono"),
        ("https://user@GitHub.com/Acme/Mono/", "github.com/Acme/Mono"),
        ("ssh://git@github.com:22/Acme/Mono.git", "github.com/Acme/Mono"),
    ],
)
def test_normalize_remote(url: str, want: str) -> None:
    assert sync_scope.normalize_remote(url) == want


@pytest.mark.parametrize(
    ("token", "want"),
    [
        ("jira:CI-1", {"type": "jira", "kind": "epic", "id": "CI-1"}),
        ("linear:Platform Revamp", {"type": "linear", "kind": "project", "id": "Platform Revamp"}),
        ("gh:acme/mono#12", {"type": "github", "kind": "tracking-issue", "id": "acme/mono#12"}),
        (
            "gh:acme/mono/milestone/v2 launch",
            {"type": "github", "kind": "milestone", "id": "acme/mono/v2 launch"},
        ),
        ("gh:acme/mono/label/infra", {"type": "github", "kind": "label", "id": "acme/mono/infra"}),
        ("CI-3718", {"type": None, "kind": None, "id": "CI-3718"}),
        ("apps/a", None),
    ],
)
def test_parse_ref(token: str, want: dict | None) -> None:
    assert sync_scope.parse_ref(token) == want


def test_parse_ref_rejects_malformed_github() -> None:
    with pytest.raises(sync_scope.SyncError):
        sync_scope.parse_ref("gh:acme/mono")


def test_scope_without_config_reports_unmapped(capsys, config: Path, repo: Path) -> None:
    code, out, _ = run(capsys, config, repo, "scope", "apps/a", "CI-9")
    assert code == 0
    assert out["repo"] == "github.com/Acme/Mono"
    assert out["selected"] == []
    assert out["unmapped"]["paths"] == ["apps/a"]
    assert out["unmapped"]["refs"] == [{"type": None, "kind": None, "id": "CI-9"}]
    assert not config.exists()


def test_first_run_needs_since_then_scans_only_mapped_paths(capsys, config, repo) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "apps/a/x.py", "feat(a): land it\n\nCloses CI-2; fixes #7")
    _commit(repo, "apps/b/y.py", "feat(b): unrelated CI-3")

    _, out, _ = run(capsys, config, repo, "scope")
    [entry] = out["selected"]
    assert entry["since_source"] == "none"
    assert entry["commits"] == []

    _, out, _ = run(capsys, config, repo, "scope", "--since", base)
    [entry] = out["selected"]
    assert entry["since_source"] == "override"
    assert [c["subject"] for c in entry["commits"]] == ["feat(a): land it"]
    assert entry["commits"][0]["refs"] == ["#7", "CI-2"]
    assert entry["changed_files"] == ["apps/a/x.py"]
    assert entry["tracker"]["site"] == "acme.atlassian.net"


def test_the_oldest_commit_in_range_may_have_no_body(capsys, config, repo) -> None:
    """Regression: an empty body at the end of the log let the output's strip eat the field
    separators, and scope crashed on a one-line commit. Real history is mostly one-line commits."""
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "apps/a/x.py", "feat(a): subject only CI-4")

    _, out, _ = run(capsys, config, repo, "scope", "--since", base)
    [entry] = out["selected"]
    assert [c["subject"] for c in entry["commits"]] == ["feat(a): subject only CI-4"]
    assert entry["commits"][0]["refs"] == ["CI-4"]


def test_advance_moves_watermark_forward_only(capsys, config, repo) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    old = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "apps/a/x.py", "feat(a): one")
    head = _git(repo, "rev-parse", "HEAD")
    advance = ["advance", "--mapping", "0", "--tracker", "j", "--kind", "epic", "--id", "CI-1"]

    code, out, _ = run(capsys, config, repo, *advance, "--commit", head)
    assert code == 0 and out["to"] == head

    _, out, _ = run(capsys, config, repo, "scope")
    assert out["selected"][0]["since_source"] == "watermark"
    assert out["selected"][0]["commits"] == []

    code, _, err = run(capsys, config, repo, *advance, "--commit", old)
    assert code == 1 and "does not descend" in err


def test_unreachable_watermark_is_invalid(capsys, config, repo) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    data = json.loads(config.read_text())
    data["mappings"][0]["groups"][0]["last_synced_commit"] = "0" * 40
    config.write_text(json.dumps(data))

    _, out, _ = run(capsys, config, repo, "scope")
    assert out["selected"][0]["since_source"] == "invalid-watermark"
    assert out["selected"][0]["since"] is None


def test_many_to_many_selection(capsys, config, repo) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-tracker", "--name", "gh", "--type", "github", "--assignee", "me")
    run(
        capsys,
        config,
        repo,
        "add-mapping",
        "--path",
        "apps/a",
        "--group",
        "j",
        "epic",
        "CI-1",
        "--group",
        "gh",
        "label",
        "acme/mono/infra",
    )
    run(capsys, config, repo, "add-mapping", "--path", "apps/b", "--group", "j", "epic", "CI-1")

    _, out, _ = run(capsys, config, repo, "scope", "CI-1")
    assert sorted(s["mapping"] for s in out["selected"]) == [0, 1]

    _, out, _ = run(capsys, config, repo, "scope", "apps/a")
    assert [s["group"]["id"] for s in out["selected"]] == ["CI-1", "acme/mono/infra"]

    _, out, _ = run(capsys, config, repo, "scope", "apps/b", "gh:acme/mono/label/infra")
    assert out["selected"] == []
    assert out["unmapped"]["paths"] == ["apps/b"]


def test_add_mapping_extends_same_path_set(capsys, config, repo) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    _, out, _ = run(
        capsys,
        config,
        repo,
        "add-mapping",
        "--path",
        "./apps/a/",
        "--group",
        "j",
        "epic",
        "CI-1",
        "--group",
        "j",
        "epic",
        "CI-2",
    )
    assert out == {"mapping": 0, "action": "extended", "added_groups": 1}


def test_other_clone_url_form_shares_mappings(capsys, config, repo) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    _git(repo, "remote", "set-url", "origin", "https://github.com/acme/mono")
    _, out, _ = run(capsys, config, repo, "scope")
    assert len(out["selected"]) == 1


def test_behind_origin_counts_without_fetching(capsys, config, repo) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    ahead = _commit(repo, "apps/a/z.py", "upstream work")
    _git(repo, "update-ref", "refs/remotes/origin/main", ahead)
    _git(repo, "reset", "-q", "--hard", base)
    _, out, _ = run(capsys, config, repo, "scope")
    assert out["behind_origin"] == 1


BASE_URL = "git@github.com:Acme/Mono.git"
FORK_URL = "git@github.com:me/Mono.git"
BASE_KEY = "github.com/Acme/Mono"
FORK_KEY = "github.com/me/Mono"


@pytest.fixture
def fork(tmp_path: Path, repo: Path) -> Path:
    """A clone whose origin is the fork and whose upstream is the base repo.

    The fork lags the base by one commit and names `dev` as its default branch. The base names
    `main`. The remotes carry fake URLs and are fetched from bare repos by path.
    """
    base_bare = tmp_path / "base.git"
    fork_bare = tmp_path / "fork.git"
    for bare in (base_bare, fork_bare):
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)

    _git(repo, "branch", "dev")
    _git(repo, "push", "-q", str(fork_bare), "main:main", "main:dev")
    _commit(repo, "apps/a/base.py", "base only work")
    _git(repo, "push", "-q", str(base_bare), "main:main")
    _commit(repo, "apps/a/base2.py", "more base only work")
    _git(repo, "push", "-q", str(base_bare), "main:main")
    _git(repo, "reset", "-q", "--hard", "HEAD~2")

    _git(repo, "remote", "set-url", "origin", FORK_URL)
    _git(repo, "remote", "add", "upstream", BASE_URL)
    _git(repo, "fetch", "-q", str(fork_bare), "+refs/heads/*:refs/remotes/origin/*")
    _git(repo, "fetch", "-q", str(base_bare), "+refs/heads/*:refs/remotes/upstream/*")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/dev")
    _git(repo, "symbolic-ref", "refs/remotes/upstream/HEAD", "refs/remotes/upstream/main")
    return repo


def test_fork_checkout_keys_mappings_by_the_base_remote(
    capsys, config, fork, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_scope, "gh_base_repo", lambda root: {"slug": "Acme/Mono", "parent": None})
    setup_jira(capsys, config, fork)
    run(capsys, config, fork, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")

    assert json.loads(config.read_text())["mappings"][0]["repo"] == BASE_KEY

    _, out, _ = run(capsys, config, fork, "scope")
    assert out["repo"] == BASE_KEY
    assert out["default_branch"] == "main"
    assert len(out["selected"]) == 1


def test_fork_checkout_without_gh_falls_back_to_upstream(capsys, config, fork) -> None:
    _, out, _ = run(capsys, config, fork, "scope")
    assert out["repo"] == BASE_KEY
    assert out["default_branch"] == "main"


def test_fork_checkout_counts_behind_against_the_base_remote(capsys, config, fork) -> None:
    _, out, _ = run(capsys, config, fork, "scope")
    assert out["behind_origin"] == 2


def test_fork_saved_as_the_pr_target_is_the_base(capsys, config, fork, tmp_path) -> None:
    """Catches a checkout that lands PRs in its fork, yet tracker-sync reads the parent's mainline."""
    save_target(tmp_path, FORK_KEY.lower(), "fork")
    _, out, _ = run(capsys, config, fork, "scope")
    assert out["repo"] == FORK_KEY
    assert out["base_remote"] == "origin"


def _lone_fork(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(repo, "remote", "set-url", "origin", FORK_URL)
    monkeypatch.setattr(sync_scope, "gh_base_repo", lambda root: {"slug": "me/Mono", "parent": "Acme/Mono"})


def test_lone_fork_remote_without_a_target_stops_and_names_both_repos(
    capsys, config, repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a checkout whose only remote is a fork read the fork's lagging mainline as the base."""
    _lone_fork(repo, monkeypatch)
    code, _, err = run(capsys, config, repo, "scope")
    assert code == 1
    assert "me/Mono" in err and "Acme/Mono" in err and "pr-targets.json" in err and FORK_KEY in err


def test_lone_fork_remote_saved_as_fork_is_the_base(capsys, config, repo, tmp_path, monkeypatch) -> None:
    _lone_fork(repo, monkeypatch)
    save_target(tmp_path, FORK_KEY, "fork")
    _, out, _ = run(capsys, config, repo, "scope")
    assert out["repo"] == FORK_KEY


def test_lone_fork_remote_chosen_with_set_default_is_the_base(capsys, config, repo, monkeypatch) -> None:
    _lone_fork(repo, monkeypatch)
    _git(repo, "config", "remote.origin.gh-resolved", "base")
    _, out, _ = run(capsys, config, repo, "scope")
    assert out["repo"] == FORK_KEY


def test_lone_fork_remote_saved_as_parent_names_the_remote_to_add(
    capsys, config, repo, tmp_path, monkeypatch
) -> None:
    """Catches a parent URL built for github.com over HTTPS when the fork is cloned over SSH."""
    _lone_fork(repo, monkeypatch)
    save_target(tmp_path, FORK_KEY, "parent")
    code, _, err = run(capsys, config, repo, "scope")
    assert code == 1
    assert "git remote add upstream git@github.com:Acme/Mono.git" in err


def test_lone_fork_remote_with_conflicting_choices_stops(capsys, config, repo, tmp_path, monkeypatch) -> None:
    _lone_fork(repo, monkeypatch)
    _git(repo, "config", "remote.origin.gh-resolved", "base")
    save_target(tmp_path, FORK_KEY, "parent")
    code, _, err = run(capsys, config, repo, "scope")
    assert code == 1
    assert "gh repo set-default --unset" in err


def test_mapping_saved_under_the_fork_key_moves_to_the_base_key(capsys, config, fork) -> None:
    setup_jira(capsys, config, fork)
    saved = json.loads(config.read_text())
    saved["mappings"] = [
        {
            "repo": FORK_KEY,
            "paths": ["apps/a"],
            "groups": [{"tracker": "j", "kind": "epic", "id": "CI-1", "last_synced_commit": None}],
        }
    ]
    config.write_text(json.dumps(saved))

    _, out, _ = run(capsys, config, fork, "scope")
    assert len(out["selected"]) == 1
    assert json.loads(config.read_text())["mappings"][0]["repo"] == BASE_KEY


def test_fork_key_mappings_stay_when_the_base_key_already_has_mappings(
    capsys, config, fork
) -> None:
    setup_jira(capsys, config, fork)
    run(capsys, config, fork, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    saved = json.loads(config.read_text())
    saved["mappings"].append({**saved["mappings"][0], "repo": FORK_KEY, "paths": ["apps/b"]})
    config.write_text(json.dumps(saved))

    run(capsys, config, fork, "scope")
    assert [m["repo"] for m in json.loads(config.read_text())["mappings"]] == [BASE_KEY, FORK_KEY]


def test_single_remote_clone_keeps_its_key_and_leaves_the_config_alone(
    capsys, config, repo
) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", "apps/a", "--group", "j", "epic", "CI-1")
    before = config.read_text()

    _, out, _ = run(capsys, config, repo, "scope")
    assert out["repo"] == BASE_KEY
    assert config.read_text() == before


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["add-tracker", "--name", "j", "--type", "jira", "--assignee", "a"], "needs --site"),
        (["add-mapping", "--path", "apps/a", "--group", "nope", "epic", "X-1"], "unknown tracker"),
        (["add-mapping", "--path", "apps/zzz", "--group", "nope", "epic", "X-1"], "does not exist"),
        (["scope", "../escape"], "relative to the repository root"),
    ],
)
def test_errors(capsys, config, repo, argv: list[str], message: str) -> None:
    code, _, err = run(capsys, config, repo, *argv)
    assert code == 1 and message in err


def test_invalid_kind_in_config_is_rejected(capsys, config, repo) -> None:
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "trackers": {"gh": {"type": "github", "assignee": "me"}},
                "mappings": [
                    {
                        "repo": "github.com/Acme/Mono",
                        "paths": ["apps/a"],
                        "groups": [{"tracker": "gh", "kind": "epic", "id": "x"}],
                    }
                ],
            }
        )
    )
    code, _, err = run(capsys, config, repo, "scope")
    assert code == 1 and "not valid for github" in err


# -- paths that another repo owns ------------------------------------------


@pytest.fixture
def core(tmp_path: Path) -> Path:
    """A repo to mount as a submodule."""
    core = _init(tmp_path / "core")
    _commit(core, "src/a.py", "init core")
    return core


def _mount(repo: Path, core: Path, mount: str = "libs/core") -> None:
    _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(core), mount)
    _git(repo, "commit", "-q", "-m", "add core")


def _bump(repo: Path, mount: str = "libs/core") -> None:
    _git(repo / mount, "pull", "-q", "--ff-only", "origin", "main")
    _git(repo, "add", mount)
    _git(repo, "commit", "-q", "-m", "bump core")


def _map(capsys, config: Path, repo: Path, path: str) -> None:
    setup_jira(capsys, config, repo)
    run(capsys, config, repo, "add-mapping", "--path", path, "--group", "j", "epic", "CI-1")


def test_a_path_inside_a_submodule_reports_the_submodules_own_commits(capsys, config, repo, core) -> None:
    """Catches a log run in the checkout. It answers nothing for a path a submodule owns."""
    _mount(repo, core)
    _map(capsys, config, repo, "libs/core/src")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(core, "src/b.py", "core: land it\n\nCloses CI-5")
    _bump(repo)

    _, out, _ = run(capsys, config, repo, "scope", "--since", base)
    [entry] = out["selected"]
    assert [c["subject"] for c in entry["commits"]] == ["core: land it"]
    assert entry["commits"][0]["refs"] == ["CI-5"]
    assert entry["commits"][0]["repo"] == str((repo / "libs/core").resolve())
    assert entry["changed_files"] == ["libs/core/src/b.py"]
    assert entry["external"] == [
        {
            "repo": str((repo / "libs/core").resolve()),
            "paths": ["libs/core/src"],
            "since": _git(core, "rev-parse", "HEAD~1"),
            "head": _git(core, "rev-parse", "HEAD"),
            "range": "pin",
        }
    ]


def test_a_submodule_root_reports_its_commits_and_the_bump_that_adopted_them(
    capsys, config, repo, core
) -> None:
    """Catches a mapping on the submodule's own path that reports the bump and none of the work."""
    _mount(repo, core)
    _map(capsys, config, repo, "libs/core")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(core, "src/b.py", "core: land it")
    _bump(repo)

    _, out, _ = run(capsys, config, repo, "scope", "--since", base)
    [entry] = out["selected"]
    assert sorted(c["subject"] for c in entry["commits"]) == ["bump core", "core: land it"]
    assert entry["changed_files"] == ["libs/core", "libs/core/src/b.py"]


def test_a_submodule_commit_the_checkout_does_not_pin_is_not_reported(capsys, config, repo, core) -> None:
    """The range is what the checkout's default branch adopted, so unadopted work waits for its bump."""
    _mount(repo, core)
    _map(capsys, config, repo, "libs/core/src")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(core, "src/b.py", "core: adopted")
    _bump(repo)
    _commit(core, "src/c.py", "core: not yet adopted")
    _git(repo / "libs/core", "pull", "-q", "--ff-only", "origin", "main")

    _, out, _ = run(capsys, config, repo, "scope", "--since", base)
    [entry] = out["selected"]
    assert [c["subject"] for c in entry["commits"]] == ["core: adopted"]
    assert entry["changed_files"] == ["libs/core/src/b.py"]


def test_a_submodule_pin_the_clone_lacks_stops_and_names_the_path(capsys, config, repo, core) -> None:
    """Catches a scan that reads a clone behind the pin as no work."""
    _mount(repo, core)
    _map(capsys, config, repo, "libs/core/src")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--cacheinfo", f"160000,{'1' * 40},libs/core")
    _git(repo, "commit", "-q", "-m", "pin a commit the clone lacks")

    code, _, err = run(capsys, config, repo, "scope", "--since", base)
    assert code == 1
    assert "libs/core" in err and "1" * 40 in err


def test_a_symlinked_specs_dir_reports_the_specs_repo_commits_in_the_checkouts_window(
    capsys, config, repo, tmp_path
) -> None:
    """Catches a log run in the checkout. It answers nothing beyond a symlink.

    The specs repo has no pin, so its window is the dates of the watermark and the head. A commit
    after the head waits for the next sync, and one before the watermark was reported already.
    """
    specs = _init(tmp_path / "specs")
    _commit(specs, "app/proposals/P-1.md", "spec: before the window", when="2024-01-10T12:00:00+00:00")
    _commit(specs, "app/proposals/P-2.md", "spec: inside the window\n\nCI-6", when="2024-03-01T12:00:00+00:00")
    _commit(specs, "app/proposals/P-3.md", "spec: after the window", when="2024-05-01T12:00:00+00:00")
    (repo / "spec").symlink_to(specs / "app")
    _git(repo, "add", "spec")
    _commit_staged(repo, "link specs", when="2024-02-01T12:00:00+00:00")
    _map(capsys, config, repo, "spec/proposals")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "apps/a/x.py", "work", when="2024-04-01T12:00:00+00:00")

    _, out, _ = run(capsys, config, repo, "scope", "--since", base)
    [entry] = out["selected"]
    assert [c["subject"] for c in entry["commits"]] == ["spec: inside the window"]
    assert entry["commits"][0]["refs"] == ["CI-6"]
    assert entry["changed_files"] == ["spec/proposals/P-2.md"]
    [external] = entry["external"]
    assert external["repo"] == str(specs.resolve())
    assert external["range"] == "date"
    assert external["paths"] == ["spec/proposals"]


def test_a_symlink_inside_the_checkout_reads_the_real_path_and_reports_the_mapped_one(
    capsys, config, repo
) -> None:
    (repo / "link").symlink_to("apps/a")
    _map(capsys, config, repo, "link")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "apps/a/x.py", "feat(a): land it")

    _, out, _ = run(capsys, config, repo, "scope", "--since", base)
    [entry] = out["selected"]
    assert [c["subject"] for c in entry["commits"]] == ["feat(a): land it"]
    assert entry["changed_files"] == ["link/x.py"]
    assert "external" not in entry
    assert all("repo" not in c for c in entry["commits"])


def test_a_mapped_path_outside_any_repo_stops(capsys, config, repo, tmp_path) -> None:
    """Catches a path that no repo tracks, which a log reads as no work."""
    loose = tmp_path / "loose"
    loose.mkdir()
    (repo / "notes").symlink_to(loose)
    _map(capsys, config, repo, "notes")
    base = _git(repo, "rev-parse", "HEAD")

    code, _, err = run(capsys, config, repo, "scope", "--since", base)
    assert code == 1
    assert "notes" in err and "not in a git repository" in err
