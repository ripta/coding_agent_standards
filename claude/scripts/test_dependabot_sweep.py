"""Tests for dependabot_sweep.py.

Every GitHub call goes through a fake `gh_json` keyed on the arguments, so no test touches the
network. All names, SHAs, and IDs are synthetic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import dependabot_sweep as ds
import pr_watch

SLUG = "example-owner/example-repo"
SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
BOT = {"login": "dependabot[bot]", "node_id": ds.DEPENDABOT_NODE_ID, "type": "Bot", "html_url": ds.DEPENDABOT_URL}


def commit(login: str | None = "dependabot[bot]", verified: bool = True, sha: str = "c0ffee") -> dict[str, Any]:
    return {"sha": sha, "author": {"login": login} if login else None,
            "commit": {"verification": {"verified": verified}}}


def pull(user: dict[str, Any] = BOT, head: str = SLUG, base: str = SLUG) -> dict[str, Any]:
    return {"user": user, "head": {"repo": {"full_name": head}}, "base": {"repo": {"full_name": base}}}


class FakeGh:
    """Answer gh calls from a table of (leading arguments) to canned replies."""

    def __init__(self, routes: dict[tuple[str, ...], Any]) -> None:
        self.routes = routes
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> Any:
        self.calls.append(args)
        for prefix, reply in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if tuple(args[: len(prefix)]) == prefix:
                if isinstance(reply, Exception):
                    raise reply
                return reply(args) if callable(reply) else reply
        raise AssertionError(f"unexpected gh call: {args}")


@pytest.fixture
def gh(monkeypatch: pytest.MonkeyPatch):
    def install(routes: dict[tuple[str, ...], Any]) -> FakeGh:
        fake = FakeGh(routes)
        monkeypatch.setattr(ds, "gh_json", fake)
        return fake

    return install


# -- provenance --------------------------------------------------------------------------------


def provenance_routes(user=BOT, commits=None, **pull_args):
    return {
        ("api", f"repos/{SLUG}/pulls/4"): pull(user, **pull_args),
        ("api", f"repos/{SLUG}/pulls/4/commits?per_page=100"): [commit()] if commits is None else commits,
    }


def test_a_dependabot_pr_with_signed_dependabot_commits_passes(gh) -> None:
    gh(provenance_routes())
    result = ds.provenance(SLUG, 4)
    assert result["ok"] and result["flags"] == []


@pytest.mark.parametrize(
    ("routes", "needle"),
    [
        (provenance_routes(user={**BOT, "node_id": "MDM6Qm90MDAwMDA="}), "node ID"),
        (provenance_routes(user={**BOT, "type": "User"}), "type"),
        (provenance_routes(head="other-owner/example-repo"), "different repository"),
        (provenance_routes(commits=[commit(), commit("someone-else", sha="beef01")]), "not authored by"),
        (provenance_routes(commits=[commit(None, sha="beef02")]), "not authored by"),
        (provenance_routes(commits=[commit(verified=False)]), "without a verified signature"),
    ],
)
def test_provenance_flags_what_does_not_belong_to_dependabot(gh, routes, needle) -> None:
    gh(routes)
    result = ds.provenance(SLUG, 4)
    assert not result["ok"]
    assert any(needle in flag for flag in result["flags"])


def test_provenance_names_the_foreign_commits(gh) -> None:
    gh(provenance_routes(commits=[commit(), commit("someone-else", sha="beef01")]))
    assert ds.provenance(SLUG, 4)["foreign_commits"] == [{"sha": "beef01", "author": "someone-else"}]


# -- inventory ---------------------------------------------------------------------------------


def search_result():
    def pr(repo, number, login, created, is_bot=True):
        return {"repository": {"nameWithOwner": repo}, "number": number, "title": f"t{number}",
                "author": {"login": login, "is_bot": is_bot}, "createdAt": created,
                "url": f"https://example.invalid/{repo}/pull/{number}", "isDraft": False}

    return [
        pr("example-owner/b", 2, "app/dependabot", "2026-02-01T00:00:00Z"),
        pr("example-owner/a", 1, "dependabot[bot]", "2026-01-01T00:00:00Z"),
        pr("example-owner/a", 3, "app/renovate", "2026-03-01T00:00:00Z"),
        pr("example-owner/b", 4, "some-person", "2026-04-01T00:00:00Z", is_bot=False),
    ]


def repo_view(fork=False, archived=False):
    return {"isFork": fork, "isArchived": archived, "pushedAt": "2026-05-01T00:00:00Z",
            "parent": {"nameWithOwner": "upstream-owner/b"} if fork else None,
            "defaultBranchRef": {"name": "main"}, "autoMergeAllowed": True,
            "mergeCommitAllowed": True, "squashMergeAllowed": True, "rebaseMergeAllowed": False}


def test_inventory_splits_dependabot_other_bots_and_people_oldest_first(gh) -> None:
    gh({
        ("search", "prs"): search_result(),
        ("repo", "view", "example-owner/a"): repo_view(),
        ("repo", "view", "example-owner/b"): repo_view(fork=True),
    })
    inv = ds.inventory("example-owner", 1000)

    assert [r["number"] for r in inv["dependabot"]] == [1, 2]
    assert [r["number"] for r in inv["other_bots"]] == [3]
    assert [r["number"] for r in inv["contributors"]] == [4]
    assert inv["by_author"] == {"dependabot": 2, "renovate": 1, "some-person": 1}
    assert inv["repos"]["example-owner/b"]["fork"] and inv["repos"]["example-owner/b"]["parent"] == "upstream-owner/b"
    assert inv["repos"]["example-owner/a"]["merge_methods"] == ["merge", "squash"]
    assert not inv["truncated"]


def test_inventory_reports_a_full_page_as_possibly_truncated(gh) -> None:
    gh({("search", "prs"): search_result()[:1], ("repo", "view"): repo_view()})
    assert ds.inventory("example-owner", 1)["truncated"]


def test_an_unreadable_repo_does_not_stop_the_inventory(gh) -> None:
    gh({("search", "prs"): search_result()[:1], ("repo", "view"): pr_watch.GhError("denied")})
    assert ds.inventory("example-owner", 1000)["repos"]["example-owner/b"] == {"error": "denied"}


# -- checks and buckets ------------------------------------------------------------------------


def run(name="ci", conclusion="SUCCESS", status="COMPLETED"):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        (run(conclusion="SUCCESS"), "pass"),
        (run(conclusion="SKIPPED"), "pass"),
        (run(conclusion="FAILURE"), "fail"),
        (run(conclusion="ACTION_REQUIRED"), "action_required"),
        (run(conclusion="", status="IN_PROGRESS"), "pending"),
        (run(conclusion=None, status="QUEUED"), "pending"),
        (run(conclusion=""), "pending"),
        ({"__typename": "StatusContext", "context": "x", "state": "PENDING"}, "pending"),
        ({"__typename": "StatusContext", "context": "x", "state": "ERROR"}, "fail"),
    ],
)
def test_check_buckets_treat_an_empty_conclusion_as_pending(node, expected) -> None:
    assert ds.check_bucket(node) == expected


def detail(checks, mergeable="MERGEABLE", state="CLEAN"):
    return {"statusCheckRollup": checks, "mergeable": mergeable, "mergeStateStatus": state, "headRefOid": SHA,
            "baseRefName": "main"}


OK = {"ok": True, "flags": []}
BAD = {"ok": False, "flags": ["x"]}
PLAIN = {"fork": False, "archived": False}
GATED = [{"name": "ci", "command": "/gcbrun", "summary": ""}]


@pytest.mark.parametrize(
    ("det", "prov", "tags", "gated", "bucket"),
    [
        (detail([run()]), OK, PLAIN, [], "green"),
        (detail([run(), run("lint", "FAILURE")]), OK, PLAIN, [], "red"),
        (detail([run(conclusion="")]), OK, PLAIN, [], "waiting-on-ci"),
        (detail([]), OK, PLAIN, [], "no-checks"),
        (detail([run(conclusion="ACTION_REQUIRED")]), OK, PLAIN, GATED, "comment-gated"),
        (detail([run(conclusion="ACTION_REQUIRED")]), OK, PLAIN, [], "needs-approval"),
        (detail([run("a", "FAILURE")], "CONFLICTING", "DIRTY"), OK, PLAIN, [], "conflicting"),
        (detail([run()], "UNKNOWN", "UNKNOWN"), OK, PLAIN, [], "unknown"),
        (detail([run()]), OK, {"fork": True}, [], "fork"),
        (detail([run()]), OK, {"archived": True, "fork": True}, [], "archived"),
        (detail([run()], "CONFLICTING", "DIRTY"), BAD, PLAIN, [], "provenance-flagged"),
    ],
)
def test_bucket_for(det, prov, tags, gated, bucket) -> None:
    assert ds.bucket_for(det, prov, tags, gated) == bucket


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ("Needs /gcbrun from a collaborator", "/gcbrun"),
        ("Needs /gcbrun(<sha>) to run latest commit", f"/gcbrun({SHA})"),
        ("Needs /gcbrun(a1b2c3) to run latest commit", f"/gcbrun({SHA})"),
        ("Waiting for an approval", None),
        (None, None),
    ],
)
def test_gate_command_pins_the_head_sha_only_when_asked(summary, expected) -> None:
    assert ds.gate_command(summary, SHA) == expected


# -- classify ----------------------------------------------------------------------------------


def inventory_file():
    rec = {"repo": SLUG, "number": 4, "title": "bump x", "created_at": "2026-01-01T00:00:00Z", "url": "u"}
    return {"dependabot": [rec], "repos": {SLUG: {"fork": False, "archived": False, "auto_merge_allowed": True,
                                               "merge_methods": ["squash"]}}}


def test_classify_reads_the_gate_text_from_rest_not_the_rollup(gh) -> None:
    gated_run = {"name": "ci (proj-a)", "conclusion": "action_required",
                 "output": {"summary": "Needs /gcbrun(<sha>) to run latest commit"}}
    other_run = {"name": "lint", "conclusion": "success", "output": {"summary": ""}}
    fake = gh({
        **provenance_routes(),
        ("pr", "view", "4"): detail([run("ci (proj-a)", "ACTION_REQUIRED"), run("lint")]),
        ("api", f"repos/{SLUG}/commits/{SHA}/check-runs?per_page=100"): {"check_runs": [gated_run, other_run]},
        ("api", f"repos/{SLUG}/rules/branches/main"): [],
        ("api", f"repos/{SLUG}/branches/main/protection"): pr_watch.GhError("HTTP 404: Not Found"),
    })
    result = ds.classify(inventory_file(), None, 0, 0)

    item = result["items"][0]
    assert item["bucket"] == "comment-gated"
    assert item["gated"][0]["command"] == f"/gcbrun({SHA})"
    assert result["buckets"] == {"comment-gated": [f"{SLUG}#4"]}
    assert result["repo_settings"][0]["auto_merge_waits_for_checks"] is False
    assert any(c[0] == "api" and "check-runs" in c[1] for c in fake.calls)


def test_classify_asks_again_while_mergeable_is_unknown(gh) -> None:
    replies = iter([detail([run()], "UNKNOWN", "UNKNOWN"), detail([run()], "UNKNOWN", "UNKNOWN"), detail([run()])])
    gh({("pr", "view", "4"): lambda args: next(replies)})
    slept = []
    result = ds.settled_detail(SLUG, 4, 3, 7, slept.append)
    assert result["mergeable"] == "MERGEABLE"
    assert slept == [7, 7]


def test_classify_gives_up_rereading_after_the_retries(gh) -> None:
    gh({("pr", "view", "4"): detail([run()], "UNKNOWN", "UNKNOWN")})
    slept = []
    assert ds.settled_detail(SLUG, 4, 2, 1, slept.append)["mergeable"] == "UNKNOWN"
    assert len(slept) == 2


def test_classify_reports_a_failed_pr_and_goes_on(gh) -> None:
    gh({("api", f"repos/{SLUG}/pulls/4"): pr_watch.GhError("rate limited")})
    result = ds.classify(inventory_file(), None, 0, 0)
    assert result["items"] == [] and result["errors"][0]["error"] == "rate limited"


def test_classify_keeps_a_required_check_in_the_repo_settings(gh) -> None:
    gh({
        **provenance_routes(),
        ("pr", "view", "4"): detail([run()]),
        ("api", f"repos/{SLUG}/rules/branches/main"): [
            {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ci"}]}}],
        ("api", f"repos/{SLUG}/branches/main/protection"): pr_watch.GhError("HTTP 404: Not Found"),
    })
    result = ds.classify(inventory_file(), None, 0, 0)
    assert result["items"][0]["bucket"] == "green"
    assert result["repo_settings"][0]["required_checks"] == ["ci"]
    assert result["repo_settings"][0]["auto_merge_waits_for_checks"] is True


# -- forks, updates, comments, merge method ----------------------------------------------------


def test_fork_report_counts_the_forks_own_commits(gh) -> None:
    gh({
        ("repo", "view"): repo_view(fork=True),
        ("api", "repos/upstream-owner/b/compare/main...example-owner:example-repo:main"): {"ahead_by": 2, "behind_by": 5},
        ("api", f"repos/{SLUG}/contents/.github/dependabot.yml"): {"name": "dependabot.yml"},
        ("api", f"repos/{SLUG}/contents/.github/dependabot.yaml"): pr_watch.GhError("HTTP 404: Not Found"),
        ("api", f"repos/{SLUG}/vulnerability-alerts"): json.JSONDecodeError("empty", "", 0),
        ("api", f"repos/{SLUG}/automated-security-fixes"): {"enabled": False, "paused": False},
    })
    report = ds.fork_report(SLUG)
    assert report["has_own_commits"] and report["ahead_by"] == 2
    assert report["dependabot_config"] == ["dependabot.yml"]
    assert report["vulnerability_alerts"] is True
    assert report["automated_security_fixes"] is False


def test_a_missing_settings_endpoint_means_disabled(gh) -> None:
    gh({("api",): pr_watch.GhError("HTTP 404: Not Found")})
    assert ds.endpoint_enabled("repos/x/y/vulnerability-alerts") is False


def test_a_denied_settings_endpoint_is_unknown(gh) -> None:
    gh({("api",): pr_watch.GhError("HTTP 403: Forbidden")})
    assert ds.endpoint_enabled("repos/x/y/vulnerability-alerts") is None


def test_a_non_fork_reports_nothing_more(gh) -> None:
    gh({("repo", "view"): repo_view()})
    assert ds.fork_report(SLUG) == {"repo": SLUG, "fork": False}


def test_update_runs_keep_update_jobs_and_count_graph_jobs_apart(gh) -> None:
    runs = {"workflow_runs": [
        {"event": "dynamic", "name": "go_modules in / for example-dep - Update #9001", "status": "queued",
         "conclusion": None, "created_at": "t", "html_url": "u1"},
        {"event": "dynamic", "name": "Configured Graph Update: go_modules in /", "status": "completed"},
        {"event": "push", "name": "ci", "status": "completed"},
    ]}
    gh({("api",): runs})
    result = ds.update_runs(SLUG, 50)
    assert [(u["ecosystem"], u["directory"], u["job"], u["status"]) for u in result["updates"]] == [
        ("go_modules", "/", "9001", "queued")]
    assert result["graph_updates_skipped"] == 1


def test_last_comment_is_the_newest_one_from_dependabot(gh) -> None:
    comments = {"comments": [
        {"author": {"login": "dependabot"}, "createdAt": "2026-01-01", "body": "old", "url": "u1"},
        {"author": {"login": "some-person"}, "createdAt": "2026-03-01", "body": "hi", "url": "u2"},
        {"author": {"login": "dependabot"}, "createdAt": "2026-02-01", "body": "new", "url": "u3"},
    ]}
    gh({("pr", "view"): comments})
    assert ds.last_dependabot_comment(SLUG, 4)["comment"]["body"] == "new"


def test_merge_method_reads_parents_and_the_squash_suffix(gh) -> None:
    def commit_for(args):
        oid = args[1].rsplit("/", 1)[1]
        return {
            "m1": {"parents": [1, 2], "commit": {"message": "Merge pull request #1"}},
            "s2": {"parents": [1], "commit": {"message": "bump x (#2)\n\nbody"}},
            "s3": {"parents": [1], "commit": {"message": "bump y (#3)"}},
            "r4": {"parents": [1], "commit": {"message": "bump z"}},
        }[oid]

    gh({
        ("pr", "list"): [{"number": n, "mergeCommit": {"oid": f"{k}{n}"}} for k, n in
                         (("m", 1), ("s", 2), ("s", 3), ("r", 4))] + [{"number": 5, "mergeCommit": None}],
        ("api",): commit_for,
    })
    result = ds.merge_method(SLUG, 5)
    assert result["observed"] == {"merge": 1, "squash": 2, "rebase": 1}
    assert result["most_common"] == "squash"
