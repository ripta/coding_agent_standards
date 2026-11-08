"""Tests for pr_watch.py. Run: uv run --with pytest pytest claude/scripts"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import pr_watch


def _run(name, status="COMPLETED", conclusion="SUCCESS", url=None):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion, "detailsUrl": url}


def _comment(cid, body, login="reviewer", typename="User"):
    return {"id": cid, "body": body, "createdAt": "t", "url": f"u/{cid}",
            "author": {"login": login, "__typename": typename}}


def _pr(checks=(), threads=(), reviews=(), comments=(), sha="s1", **extra):
    pr = {
        "number": 7, "state": "OPEN", "merged": False, "headRefOid": sha, "mergeStateStatus": "BLOCKED",
        "commits": {"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": list(checks)}}}}]},
        "reviewThreads": {"nodes": list(threads)},
        "reviews": {"nodes": list(reviews)},
        "comments": {"nodes": list(comments)},
    }
    pr.update(extra)
    return pr


def _thread(tid, *comments, resolved=False):
    return {"id": tid, "isResolved": resolved, "isOutdated": False, "path": "a.py", "line": 3,
            "comments": {"nodes": list(comments)}}


def _kinds(events):
    return [e["event"] for e in events]


def test_status_context_and_check_run_buckets():
    assert pr_watch.normalize_check({"__typename": "StatusContext", "context": "ci", "state": "ERROR"})["bucket"] == "fail"
    assert pr_watch.normalize_check({"__typename": "StatusContext", "context": "ci", "state": "EXPECTED"})["bucket"] == "pending"
    assert pr_watch.normalize_check(_run("x", conclusion="SKIPPED"))["bucket"] == "pass"
    assert pr_watch.normalize_check(_run("x", conclusion="TIMED_OUT"))["bucket"] == "fail"
    assert pr_watch.normalize_check(_run("x", status="IN_PROGRESS", conclusion=None))["bucket"] == "pending"


def test_failure_is_reported_before_the_rest_finish_and_only_once():
    state = {}
    pr = _pr([_run("lint", conclusion="FAILURE"), _run("test", status="QUEUED", conclusion=None)])
    assert _kinds(pr_watch.pr_events(state, pr, 0, 600)) == ["check-failed"]
    assert pr_watch.pr_events(state, pr, 1, 600) == []

    done = _pr([_run("lint", conclusion="FAILURE"), _run("test")])
    events = pr_watch.pr_events(state, done, 2, 600)
    assert _kinds(events) == ["checks-done"]
    assert events[0]["failed"] == ["lint"] and events[0]["passed"] == ["test"]


def test_rerun_on_the_same_head_reports_again():
    """A rerun keeps the head SHA. Its pending state starts the check over, so its result is reported again.

    Catches a watch that keys reported checks by head alone and goes silent after `gh run rerun`.
    """
    state = {}
    first = _pr([_run("test", conclusion="FAILURE", url="job/1")])
    assert _kinds(pr_watch.pr_events(state, first, 0, 600)) == ["check-failed", "checks-done"]

    rerun = _pr([_run("test", status="QUEUED", conclusion=None, url="job/2")])
    assert pr_watch.pr_events(state, rerun, 1, 600) == []

    again = _pr([_run("test", conclusion="FAILURE", url="job/2")])
    events = pr_watch.pr_events(state, again, 2, 600)
    assert _kinds(events) == ["check-failed", "checks-done"]
    assert events[0]["url"] == "job/2" and events[1]["failed"] == ["test"]


def test_rerun_that_finishes_between_polls_is_reported_by_its_new_url():
    """A rerun can finish inside one poll interval, so no poll sees it pending. Its new URL marks it.

    Catches a reset that only watches for a check returning to pending.
    """
    state = {}
    pr_watch.pr_events(state, _pr([_run("test", conclusion="FAILURE", url="job/1")]), 0, 600)

    events = pr_watch.pr_events(state, _pr([_run("test", url="job/2")]), 1, 600)
    assert _kinds(events) == ["checks-done"]
    assert events[0]["passed"] == ["test"] and events[0]["failed"] == []
    assert pr_watch.pr_events(state, _pr([_run("test", url="job/2")]), 2, 600) == []


def test_watch_until_checks_waits_out_a_rerun_on_a_finished_head(tmp_path):
    """A state file that saw the head finish must not end a watch armed while a rerun is pending."""
    clock = _Clock()
    state = tmp_path / "s.json"
    pr_watch.watch([7], state, 3600, 60, 600, "checks", lambda n: _pr([_run("t", conclusion="FAILURE", url="job/1")]),
                   [].append, clock, clock.sleep)

    polls = iter([_pr([_run("t", status="IN_PROGRESS", conclusion=None, url="job/2")]), _pr([_run("t", url="job/2")])])
    out = []
    status = pr_watch.watch([7], state, 3600, 60, 600, "checks", lambda n: next(polls), out.append, clock, clock.sleep)
    assert status == 0 and _kinds(out) == ["checks-done"] and out[0]["passed"] == ["t"]


def test_new_head_starts_the_checks_over():
    state = {}
    pr_watch.pr_events(state, _pr([_run("test", conclusion="FAILURE")]), 0, 600)
    events = pr_watch.pr_events(state, _pr([_run("test", conclusion="FAILURE")], sha="s2"), 1, 600)
    assert _kinds(events) == ["check-failed", "checks-done"]


def test_no_checks_waits_for_the_appear_timeout():
    state = {}
    assert pr_watch.pr_events(state, _pr(), 0, 600) == []
    assert pr_watch.pr_events(state, _pr(), 599, 600) == []
    assert _kinds(pr_watch.pr_events(state, _pr(), 600, 600)) == ["no-checks"]
    assert pr_watch.pr_events(state, _pr(), 900, 600) == []


def test_loop_comments_are_skipped_and_bots_are_flagged():
    state = {}
    thread = _thread("T1", _comment("c1", "nit: rename", "coderabbitai", "Bot"),
                     _comment("c2", "Renamed.\n\n" + pr_watch.MARKER, "ripta"))
    events = pr_watch.pr_events(state, _pr(threads=[thread]), 0, 600)
    assert _kinds(events) == ["comment"]
    assert events[0]["bot"] is True and events[0]["thread"] == "T1"

    thread["comments"]["nodes"].append(_comment("c3", "thanks, but also X", "coderabbitai", "Bot"))
    events = pr_watch.pr_events(state, _pr(threads=[thread]), 1, 600)
    assert [e["id"] for e in events] == ["c3"]


def test_user_comment_from_same_login_is_reported():
    events = pr_watch.pr_events({}, _pr(comments=[_comment("i1", "please split this", "ripta")]), 0, 600)
    assert _kinds(events) == ["comment"] and events[0]["kind"] == "conversation"


def test_empty_approval_is_not_an_event_but_changes_requested_is():
    reviews = [
        {"id": "r1", "state": "APPROVED", "body": "", "author": {"login": "h", "__typename": "User"}},
        {"id": "r2", "state": "CHANGES_REQUESTED", "body": "", "author": {"login": "h", "__typename": "User"}},
    ]
    events = pr_watch.pr_events({}, _pr(reviews=reviews), 0, 600)
    assert [e["id"] for e in events] == ["r2"]


def test_behind_is_reported_once_per_head():
    state = {}
    assert _kinds(pr_watch.pr_events(state, _pr(mergeStateStatus="BEHIND"), 0, 600)) == ["behind"]
    assert pr_watch.pr_events(state, _pr(mergeStateStatus="BEHIND"), 1, 600) == []
    assert _kinds(pr_watch.pr_events(state, _pr(mergeStateStatus="BEHIND", sha="s2"), 2, 600)) == ["behind"]


def test_merged_and_conflict_events():
    state = {}
    events = pr_watch.pr_events(state, _pr(mergeStateStatus="DIRTY"), 0, 600)
    assert _kinds(events) == ["conflict"]
    assert _kinds(pr_watch.pr_events(state, _pr(merged=True, state="MERGED"), 1, 600)) == ["merged"]
    assert pr_watch.pr_events(state, _pr(merged=True, state="MERGED"), 2, 600) == []


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_watch_exits_on_first_event_and_resumes_from_state(tmp_path):
    clock = _Clock()
    polls = iter([_pr([_run("t", status="QUEUED", conclusion=None)]), _pr([_run("t")])])
    out = []
    state = tmp_path / "state.json"
    status = pr_watch.watch([7], state, 3600, 60, 600, "event", lambda n: next(polls), out.append, clock, clock.sleep)
    assert status == 0 and _kinds(out) == ["checks-done"] and clock.now == 60

    out.clear()
    status = pr_watch.watch([7], state, 120, 60, 600, "event", lambda n: _pr([_run("t")]), out.append,
                            clock, clock.sleep)
    assert status == 124 and _kinds(out) == ["timeout"]
    assert json.loads(state.read_text())["prs"]["7"]["heads"]["s1"]["done"] is True


def test_watch_until_checks_waits_for_every_pr(tmp_path):
    clock = _Clock()
    prs = {7: iter([_pr(), _pr([_run("t")])]), 8: iter([_pr([_run("t")], number=8), _pr([_run("t")], number=8)])}
    out = []
    status = pr_watch.watch([7, 8], tmp_path / "s.json", 3600, 60, 600, "checks", lambda n: next(prs[n]),
                            out.append, clock, clock.sleep)
    assert status == 0
    assert [(e["pr"], e["event"]) for e in out] == [(8, "checks-done"), (7, "checks-done")]


def test_watch_reports_repeated_errors(tmp_path):
    clock = _Clock()

    def fail(n):
        raise pr_watch.GhError("HTTP 502")

    out = []
    status = pr_watch.watch([7], tmp_path / "s.json", 3600, 60, 600, "event", fail, out.append, clock, clock.sleep)
    assert status == 2 and out == [{"event": "error", "message": "HTTP 502", "consecutive": 3}]


def test_protection_merges_rulesets_and_classic():
    rules = [
        {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ci"}]}},
        {"type": "pull_request", "parameters": {"required_approving_review_count": 1,
                                                "required_review_thread_resolution": True}},
    ]
    classic = {"required_status_checks": {"contexts": ["lint"]},
               "required_pull_request_reviews": {"required_approving_review_count": 2}}
    merged = pr_watch.merge_protection(pr_watch.protection_from_rules(rules), pr_watch.protection_from_classic(classic))
    assert merged == {"required_checks": ["ci", "lint"], "required_approvals": 2, "thread_resolution": True}


def test_ci_systems(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (tmp_path / "cloudbuild.yaml").write_text("steps: []\n")
    assert [s["system"] for s in pr_watch.ci_systems(tmp_path)] == ["github-actions", "cloud-build"]


def test_failures_extract_log_ids():
    pr = _pr([
        _run("unit", conclusion="FAILURE", url="https://github.com/o/r/actions/runs/123/job/456"),
        _run("gcb", conclusion="FAILURE",
             url="https://console.cloud.google.com/cloud-build/builds;region=us-west1/"
                 "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0?project=p"),
        _run("ok"),
    ])
    unit, gcb = pr_watch.failures_of(pr)
    assert (unit["system"], unit["run"], unit["job"]) == ("github-actions", "123", "456")
    assert (gcb["system"], gcb["region"], gcb["build"]) == ("cloud-build", "us-west1", "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")


def test_marker_is_added_once():
    assert pr_watch.marked("done").endswith(pr_watch.MARKER)
    assert pr_watch.marked(pr_watch.marked("done")).count(pr_watch.MARKER) == 1


REPO = {"mergeCommitAllowed": True, "squashMergeAllowed": True, "rebaseMergeAllowed": False}


def test_merge_methods_start_from_repo_switches():
    assert pr_watch.merge_methods(REPO, []) == {"allowed": ["MERGE", "SQUASH"], "merge_queue": None}
    assert pr_watch.merge_methods(REPO, None)["allowed"] == ["MERGE", "SQUASH"]


def test_merge_methods_are_narrowed_by_rulesets():
    linear = pr_watch.merge_methods(REPO, [{"type": "required_linear_history"}])
    assert linear["allowed"] == ["SQUASH"]

    restricted = [{"type": "pull_request", "parameters": {"allowed_merge_methods": ["merge", "rebase"]}}]
    assert pr_watch.merge_methods(REPO, restricted)["allowed"] == ["MERGE"]

    unrestricted = [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}]
    assert pr_watch.merge_methods(REPO, unrestricted)["allowed"] == ["MERGE", "SQUASH"]


def test_merge_queue_makes_stacking_unviable():
    methods = pr_watch.merge_methods(REPO, [{"type": "merge_queue", "parameters": {"merge_method": "SQUASH"}}])
    assert methods["merge_queue"] == {"merge_method": "SQUASH"}
    summary = pr_watch.stacking_summary(methods)
    assert summary["viable"] is False and summary["reasons"] == ["the base uses a merge queue"]


def test_stacking_needs_merge_commits():
    methods = pr_watch.merge_methods(REPO, [{"type": "required_linear_history"}])
    assert pr_watch.stacking_summary(methods) == {
        "viable": False, "reasons": ["merge commits are not allowed on the base"]}
    assert pr_watch.stacking_summary(pr_watch.merge_methods(REPO, [])) == {"viable": True, "reasons": []}


def test_strict_up_to_date_from_rulesets_and_classic():
    strict_rule = {"type": "required_status_checks",
                   "parameters": {"strict_required_status_checks_policy": True, "required_status_checks": []}}
    loose_rule = {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": False}}
    assert pr_watch.strict_from_rules([strict_rule]) is True
    assert pr_watch.strict_from_rules([loose_rule]) is False
    assert pr_watch.strict_from_classic({"required_status_checks": {"strict": True}}) is True
    assert pr_watch.strict_from_classic({"required_status_checks": {"strict": False}}) is False
    assert pr_watch.strict_from_classic({}) is False


WORKFLOWS = {
    "plain": ("on:\n  push:\n    branches: [main]\n  pull_request:\njobs: {}\n", "yes"),
    "types only": ("on:\n  pull_request:\n    types: [opened]\n  push:\n", "yes"),
    "inline list": ("on: [push, pull_request]\n", "yes"),
    "inline scalar": ("on: pull_request\n", "yes"),
    "list item": ("on:\n  - push\n  - pull_request\n", "yes"),
    "literal branches": ("on:\n  pull_request:\n    branches:\n      - main\n      - 'release'\n", "no"),
    "inline branches": ("on:\n  pull_request:\n    branches: [main]\n", "no"),
    "glob branches": ("on:\n  pull_request:\n    branches:\n      - 'agent/**'\n", "unknown"),
    "ignore": ("on:\n  pull_request:\n    branches-ignore:\n      - docs\n", "unknown"),
    "inline mapping filter": ("on:\n  pull_request: {branches: [main]}\n", "unknown"),
    "push filter only": ("on:\n  push:\n    branches: [main]\n", None),
    "target is not pull_request": ("on:\n  pull_request_target:\n", None),
    "event name in a condition": ("on: push\njobs:\n  a:\n    if: github.event_name == 'pull_request'\n", None),
    "comment": ("on:\n  push:\n  # pull_request:\n", None),
}


def test_workflow_pr_bases():
    for label, (text, expected) in WORKFLOWS.items():
        assert pr_watch.workflow_pr_bases(text) == expected, label


def _workflows(root, **files):
    folder = root / ".github" / "workflows"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / f"{name}.yml").write_text(text)
    return pr_watch.ci_systems(root)


def test_ci_other_bases_is_yes_when_every_pr_workflow_builds_any_base(tmp_path):
    systems = _workflows(tmp_path, ci=WORKFLOWS["plain"][0], lint=WORKFLOWS["types only"][0])
    assert pr_watch.ci_other_bases(tmp_path, systems)["answer"] == "yes"


def test_ci_other_bases_is_unknown_when_workflows_disagree(tmp_path):
    """The required check may come from the filtered workflow, so one unfiltered workflow proves nothing."""
    systems = _workflows(tmp_path, ci=WORKFLOWS["plain"][0], lint=WORKFLOWS["inline branches"][0])
    assert pr_watch.ci_other_bases(tmp_path, systems)["answer"] == "unknown"


def test_ci_other_bases_is_no_when_every_pr_workflow_filters(tmp_path):
    systems = _workflows(tmp_path, ci=WORKFLOWS["inline branches"][0], push=WORKFLOWS["push filter only"][0])
    assert pr_watch.ci_other_bases(tmp_path, systems)["answer"] == "no"


def test_ci_other_bases_is_no_without_pr_workflows(tmp_path):
    systems = _workflows(tmp_path, push=WORKFLOWS["push filter only"][0])
    answer = pr_watch.ci_other_bases(tmp_path, systems)
    assert answer["answer"] == "no" and "pull_request" in answer["reason"]


def test_ci_other_bases_unknown_for_filters_and_other_systems(tmp_path):
    systems = _workflows(tmp_path, ci=WORKFLOWS["plain"][0], lint=WORKFLOWS["ignore"][0])
    assert pr_watch.ci_other_bases(tmp_path, systems)["answer"] == "unknown"

    (tmp_path / "cloudbuild.yaml").write_text("steps: []\n")
    systems = pr_watch.ci_systems(tmp_path)
    answer = pr_watch.ci_other_bases(tmp_path, [s for s in systems if s["system"] == "cloud-build"])
    assert answer["answer"] == "unknown" and "outside the checkout" in answer["reason"]


def test_ci_other_bases_unknown_without_ci(tmp_path):
    assert pr_watch.ci_other_bases(tmp_path, [])["answer"] == "unknown"


BUILD_URL = "https://console.cloud.google.com/cloud-build/builds;region=us-central1/build-1?project=111"
TRIGGER_URL = "https://console.cloud.google.com/cloud-build/triggers;region=us-central1/edit/trig-1?project=111"
GLOBAL_BUILD_URL = "https://console.cloud.google.com/cloud-build/builds/build-1?project=111"


def _cb_run(name="ci (proj-a)", url=BUILD_URL, app="google-cloud-developer-connect"):
    return {"name": name, "app": {"slug": app}, "details_url": url}


def _fake_cloud(monkeypatch, runs, trigger, merged=(("1", "sha1"),), build_trigger="trig-1", fail=None):
    gcloud_calls = []

    def fake_gh_json(args):
        if args[:2] == ["pr", "list"]:
            return [{"number": int(n), "headRefOid": sha} for n, sha in merged]
        return {"check_runs": runs.get(args[1].split("/commits/")[1].split("/")[0], [])}

    def fake_gcloud(args):
        gcloud_calls.append(args)
        if fail and fail in args:
            raise pr_watch.GcloudError(f"{fail} denied")
        if args[:2] == ["projects", "describe"]:
            return "proj-a\n"
        if args[:2] == ["builds", "describe"]:
            return build_trigger + "\n"
        return json.dumps(trigger)

    monkeypatch.setattr(pr_watch, "gh_json", fake_gh_json)
    monkeypatch.setattr(pr_watch, "gcloud", fake_gcloud)
    return gcloud_calls


def _verdict(required=()):
    return pr_watch.cloud_build_verdict("o/r", "main", list(required))


def test_cloud_build_developer_connect_trigger_matching_everything_is_yes(monkeypatch):
    calls = _fake_cloud(monkeypatch, {"sha1": [_cb_run()]},
                        {"name": "t", "developerConnectEventConfig": {"pullRequest": {"branch": ".*"}}})
    assert _verdict()["answer"] == "yes"
    assert ["builds", "describe", "build-1", "--project", "proj-a", "--region", "us-central1",
            "--format=value(buildTriggerId)"] in calls


def test_cloud_build_first_gen_trigger_filtered_to_main_is_no(monkeypatch):
    _fake_cloud(monkeypatch, {"sha1": [_cb_run(app="google-cloud-build")]},
                {"name": "main-only", "github": {"pullRequest": {"branch": "^main$"}}})
    answer = _verdict()
    assert answer["answer"] == "no" and "main-only" in answer["reason"]


def test_cloud_build_trigger_url_skips_the_build_lookup(monkeypatch):
    calls = _fake_cloud(monkeypatch, {"sha1": [_cb_run(url=TRIGGER_URL)]},
                        {"repositoryEventConfig": {"pullRequest": {"branch": ".*"}}})
    assert _verdict()["answer"] == "yes"
    assert not any(c[:2] == ["builds", "describe"] for c in calls)


def test_cloud_build_global_build_url_omits_region(monkeypatch):
    calls = _fake_cloud(monkeypatch, {"sha1": [_cb_run(url=GLOBAL_BUILD_URL)]},
                        {"github": {"pullRequest": {"branch": ".*"}}})
    assert _verdict()["answer"] == "yes"
    assert all("--region" not in c for c in calls)


def test_cloud_build_push_trigger_does_not_build_prs(monkeypatch):
    _fake_cloud(monkeypatch, {"sha1": [_cb_run()]}, {"name": "pusher", "github": {"push": {"branch": ".*"}}})
    assert _verdict()["answer"] == "no"


def test_cloud_build_re2_pattern_python_rejects_is_unknown(monkeypatch):
    _fake_cloud(monkeypatch, {"sha1": [_cb_run()]}, {"github": {"pullRequest": {"branch": "(?P<x"}}})
    assert _verdict()["answer"] == "unknown"


def test_cloud_build_lookup_failure_is_unknown_with_the_step(monkeypatch):
    _fake_cloud(monkeypatch, {"sha1": [_cb_run()]}, {}, fail="projects")
    answer = _verdict()
    assert answer["answer"] == "unknown" and "projects denied" in answer["reason"]


def test_cloud_build_without_check_runs_is_unknown(monkeypatch):
    _fake_cloud(monkeypatch, {"sha1": [_cb_run(app="github-actions")]}, {})
    answer = _verdict()
    assert answer["answer"] == "unknown" and "no Cloud Build check runs" in answer["reason"]


def test_cloud_build_uses_the_newest_pr_with_cloud_build_checks_and_looks_each_trigger_up_once(monkeypatch):
    calls = _fake_cloud(monkeypatch, {"sha1": [], "sha2": [_cb_run("a"), _cb_run("b")]},
                        {"github": {"pullRequest": {"branch": ".*"}}}, merged=(("1", "sha1"), ("2", "sha2")))
    assert _verdict()["answer"] == "yes"
    assert sum(c[:3] == ["builds", "triggers", "describe"] for c in calls) == 1
    assert sum(c[:2] == ["projects", "describe"] for c in calls) == 1


def test_cloud_build_only_required_checks_count(monkeypatch):
    _fake_cloud(monkeypatch, {"sha1": [_cb_run("required"), _cb_run("optional", url=TRIGGER_URL)]},
                {"github": {"pullRequest": {"branch": "^main$"}}})
    assert _verdict(["other"])["answer"] == "unknown"
    assert _verdict(["required"])["answer"] == "no"


def test_ci_other_bases_takes_the_cloud_build_verdict(tmp_path):
    (tmp_path / "cloudbuild.yaml").write_text("steps: []\n")
    systems = pr_watch.ci_systems(tmp_path)
    assert pr_watch.ci_other_bases(tmp_path, systems, {"answer": "yes", "reason": "r"})["answer"] == "yes"
    unreadable = {"answer": "unknown", "reason": "gcloud is unauthenticated"}
    assert pr_watch.ci_other_bases(tmp_path, systems, unreadable)["reason"] == "gcloud is unauthenticated"


REPO_SLUG = "example-owner/example-repo"


# -- pr_watch --repo ---------------------------------------------------------------------------


def test_repo_override_skips_the_checkout_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(args):
        raise AssertionError("must not ask the checkout")

    monkeypatch.setattr(pr_watch, "gh", forbidden)
    assert pr_watch.repo_slug("example-owner/example-repo") == ("example-owner", "example-repo")


@pytest.mark.parametrize("bad", ["example-repo", "a/b/c", "a b/c", "#12"])
def test_repo_override_must_look_like_owner_slash_name(bad: str) -> None:
    with pytest.raises(pr_watch.GhError, match="OWNER/NAME"):
        pr_watch.repo_slug(bad)


def test_snapshot_with_repo_queries_that_repository(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    seen = []

    def fake_fetch(owner, name, number):
        seen.append((owner, name, number))
        return {"number": number, "state": "OPEN", "merged": False, "headRefOid": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"}

    monkeypatch.setattr(pr_watch, "fetch_pr", fake_fetch)
    assert pr_watch.main(["pr_watch.py", "--repo", REPO_SLUG, "snapshot", "--pr", "4"]) == 0
    assert seen == [("example-owner", "example-repo", 4)]
    assert json.loads(capsys.readouterr().out)["number"] == 4


def test_comment_with_repo_targets_that_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(pr_watch, "gh", lambda args: calls.append(args) or "https://example.invalid/c\n")
    body = tmp_path / "body.md"
    body.write_text("hello")
    assert pr_watch.main(["pr_watch.py", "--repo", REPO_SLUG, "comment", "--pr", "4", "--body-file", str(body)]) == 0
    assert calls[0][:5] == ["pr", "comment", "4", "-R", REPO_SLUG]
