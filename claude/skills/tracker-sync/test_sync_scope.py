"""Tests for sync_scope.py. Run: uv run --with pytest pytest claude/skills/tracker-sync"""

import json
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


def _commit(repo: Path, path: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as fh:
        fh.write(f"{message}\n")
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


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
