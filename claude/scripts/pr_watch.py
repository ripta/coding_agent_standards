#!/usr/bin/env python3
"""Watch GitHub pull requests for CI results and review activity, and act on review threads.

    python3 pr_watch.py preflight [--base BRANCH]
    python3 pr_watch.py snapshot --pr N
    python3 pr_watch.py watch --pr N [--pr M ...] --state FILE --timeout SECONDS
    python3 pr_watch.py threads --pr N
    python3 pr_watch.py failures --pr N
    python3 pr_watch.py reply --thread ID --body-file FILE
    python3 pr_watch.py comment --pr N --body-file FILE
    python3 pr_watch.py resolve --thread ID

Every subcommand prints JSON on stdout. `watch` prints one JSON object per line, one per event.
Run it from inside the repository's checkout. `gh` reads its credentials from ~/.config/gh, which
a sandboxed shell cannot read, so run this script through cg or with the sandbox disabled.

Replies and comments this script posts carry MARKER. `watch` never reports a comment that carries
it, so the loop's own replies do not wake the loop. The replies come from the user's own `gh`
identity, so filtering by author would also drop the user's real comments.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

MARKER = "<!-- merge-fix-loop -->"

PENDING, PASS, FAIL = "pending", "pass", "fail"

# CheckRun conclusions that count as passing. Everything else that is COMPLETED fails.
PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}

# Consecutive failed polls before `watch` reports an error. A single failed request is usually a
# network blip or a rate-limit window, not a reason to wake the loop.
ERROR_THRESHOLD = 3

PR_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number url state merged isDraft mergeable mergeStateStatus headRefName baseRefName headRefOid
      autoMergeRequest { enabledAt mergeMethod }
      commits(last: 1) { nodes { commit { oid statusCheckRollup { state
        contexts(first: 100) { pageInfo { hasNextPage } nodes {
          __typename
          ... on CheckRun { name status conclusion detailsUrl }
          ... on StatusContext { context state targetUrl }
        } }
      } } } }
      reviewThreads(first: 100) { pageInfo { hasNextPage } nodes {
        id isResolved isOutdated path line
        comments(first: 50) { nodes {
          id databaseId body createdAt url author { login __typename }
        } }
      } }
      reviews(last: 50) { nodes { id state body submittedAt url author { login __typename } } }
      comments(last: 50) { nodes { id body createdAt url author { login __typename } } }
    }
  }
}
"""

REPO_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner viewerPermission autoMergeAllowed mergeCommitAllowed squashMergeAllowed
    rebaseMergeAllowed deleteBranchOnMerge viewerDefaultMergeMethod defaultBranchRef { name }
  }
}
"""

REPLY_MUTATION = """
mutation($thread: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $thread, body: $body}) {
    comment { id url }
  }
}
"""

RESOLVE_MUTATION = """
mutation($thread: ID!) {
  resolveReviewThread(input: {threadId: $thread}) { thread { id isResolved } }
}
"""


class GhError(Exception):
    pass


def gh(args: list[str]) -> str:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True)
    except FileNotFoundError as e:
        raise GhError("gh is not installed") from e
    if result.returncode != 0:
        raise GhError(result.stderr.strip() or f"gh {' '.join(args)} exited {result.returncode}")
    return result.stdout


def gh_json(args: list[str]) -> Any:
    return json.loads(gh(args))


def graphql(query: str, **variables: Any) -> dict[str, Any]:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) else "-f"
        args += [flag, f"{key}={value}"]
    data = gh_json(args)
    if data.get("errors"):
        raise GhError("; ".join(e.get("message", "") for e in data["errors"]))
    return data["data"]


def repo_slug() -> tuple[str, str]:
    owner, name = gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]).strip().split("/")
    return owner, name


def fetch_pr(owner: str, name: str, number: int) -> dict[str, Any]:
    pr = graphql(PR_QUERY, owner=owner, name=name, number=number)["repository"]["pullRequest"]
    if pr is None:
        raise GhError(f"PR #{number} not found in {owner}/{name}")
    return pr


# -- normalization ---------------------------------------------------------------------------


def author_of(node: dict[str, Any]) -> dict[str, Any]:
    author = node.get("author") or {}
    login = author.get("login") or "ghost"
    return {"author": login, "bot": author.get("__typename") == "Bot" or login.endswith("[bot]")}


def normalize_check(node: dict[str, Any]) -> dict[str, Any]:
    if node.get("__typename") == "StatusContext":
        state = node.get("state")
        bucket = PASS if state == "SUCCESS" else FAIL if state in ("FAILURE", "ERROR") else PENDING
        return {"name": node.get("context"), "bucket": bucket, "detail": state, "url": node.get("targetUrl")}

    if node.get("status") != "COMPLETED":
        bucket, detail = PENDING, node.get("status")
    else:
        detail = node.get("conclusion")
        bucket = PASS if detail in PASSING_CONCLUSIONS else FAIL
    return {"name": node.get("name"), "bucket": bucket, "detail": detail, "url": node.get("detailsUrl")}


def checks_of(pr: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    nodes = pr.get("commits", {}).get("nodes") or []
    rollup = (nodes[0]["commit"].get("statusCheckRollup") if nodes else None) or {}
    contexts = rollup.get("contexts") or {}
    checks = [normalize_check(n) for n in contexts.get("nodes") or []]
    return checks, bool((contexts.get("pageInfo") or {}).get("hasNextPage"))


def summarize(pr: dict[str, Any]) -> dict[str, Any]:
    checks, truncated = checks_of(pr)
    threads = pr.get("reviewThreads") or {}
    unresolved = [t for t in threads.get("nodes") or [] if not t.get("isResolved")]
    return {
        "number": pr["number"],
        "url": pr.get("url"),
        "state": pr.get("state"),
        "merged": pr.get("merged"),
        "draft": pr.get("isDraft"),
        "head": pr.get("headRefName"),
        "base": pr.get("baseRefName"),
        "sha": pr.get("headRefOid"),
        "mergeable": pr.get("mergeable"),
        "merge_state": pr.get("mergeStateStatus"),
        "auto_merge": pr.get("autoMergeRequest"),
        "checks": checks,
        "checks_truncated": truncated,
        "pending": sorted(c["name"] for c in checks if c["bucket"] == PENDING),
        "failed": sorted(c["name"] for c in checks if c["bucket"] == FAIL),
        "unresolved_threads": len(unresolved),
        "threads_truncated": bool((threads.get("pageInfo") or {}).get("hasNextPage")),
    }


def thread_view(thread: dict[str, Any]) -> dict[str, Any]:
    comments = [
        {"id": c["id"], "url": c.get("url"), "body": c.get("body", ""), "created": c.get("createdAt"),
         "ours": MARKER in (c.get("body") or ""), **author_of(c)}
        for c in (thread.get("comments") or {}).get("nodes") or []
    ]
    return {"thread": thread["id"], "path": thread.get("path"), "line": thread.get("line"),
            "resolved": thread.get("isResolved"), "outdated": thread.get("isOutdated"), "comments": comments}


# -- events ----------------------------------------------------------------------------------


def pr_events(state: dict[str, Any], pr: dict[str, Any], now: float, appear_timeout: float) -> list[dict[str, Any]]:
    """Compare one poll of a PR against what earlier polls reported, and return the new events.

    `state` is mutated to record what was reported, so the same event is never emitted twice, even
    across separate runs that share a state file. Check events are keyed by head SHA, so a push
    starts the checks over.
    """
    number = pr["number"]
    events: list[dict[str, Any]] = []
    seen: set[str] = set(state.setdefault("seen", []))
    per_pr = state.setdefault("prs", {}).setdefault(str(number), {})

    def emit(event: str, **fields: Any) -> None:
        events.append({"event": event, "pr": number, **fields})

    if pr.get("merged"):
        if not per_pr.get("merged"):
            per_pr["merged"] = True
            emit("merged")
        return events
    if pr.get("state") == "CLOSED":
        if not per_pr.get("closed"):
            per_pr["closed"] = True
            emit("closed")
        return events

    sha = pr.get("headRefOid") or ""
    head = per_pr.setdefault("heads", {}).setdefault(sha, {"first_seen": now, "reported": {}})
    checks, _ = checks_of(pr)

    for check in checks:
        if check["bucket"] == FAIL and head["reported"].get(check["name"]) != FAIL:
            head["reported"][check["name"]] = FAIL
            emit("check-failed", sha=sha, name=check["name"], detail=check["detail"], url=check["url"])

    if checks and all(c["bucket"] != PENDING for c in checks) and not head.get("done"):
        head["done"] = True
        emit("checks-done", sha=sha,
             passed=sorted(c["name"] for c in checks if c["bucket"] == PASS),
             failed=sorted(c["name"] for c in checks if c["bucket"] == FAIL),
             merge_state=pr.get("mergeStateStatus"))
    elif not checks and now - head["first_seen"] >= appear_timeout and not head.get("no_checks"):
        head["no_checks"] = True
        emit("no-checks", sha=sha, waited=int(now - head["first_seen"]))

    if pr.get("mergeStateStatus") == "DIRTY" and not head.get("conflict"):
        head["conflict"] = True
        emit("conflict", sha=sha)

    for thread in (pr.get("reviewThreads") or {}).get("nodes") or []:
        view = thread_view(thread)
        for comment in view["comments"]:
            if comment["id"] in seen:
                continue
            seen.add(comment["id"])
            if not comment["ours"]:
                emit("comment", kind="thread", thread=view["thread"], path=view["path"], line=view["line"],
                     resolved=view["resolved"], outdated=view["outdated"],
                     **{k: comment[k] for k in ("id", "author", "bot", "body", "url")})

    for review in (pr.get("reviews") or {}).get("nodes") or []:
        if review["id"] in seen:
            continue
        seen.add(review["id"])
        body = review.get("body") or ""
        if MARKER not in body and (body.strip() or review.get("state") == "CHANGES_REQUESTED"):
            emit("review", id=review["id"], state=review.get("state"), body=body, url=review.get("url"),
                 **author_of(review))

    for comment in (pr.get("comments") or {}).get("nodes") or []:
        if comment["id"] in seen:
            continue
        seen.add(comment["id"])
        body = comment.get("body") or ""
        if MARKER not in body:
            emit("comment", kind="conversation", id=comment["id"], body=body, url=comment.get("url"),
                 **author_of(comment))

    state["seen"] = sorted(seen)
    return events


def finished(pr: dict[str, Any], state: dict[str, Any], until: str) -> bool:
    per_pr = state.get("prs", {}).get(str(pr["number"]), {})
    if per_pr.get("merged") or per_pr.get("closed"):
        return True
    if until != "checks":
        return False
    head = per_pr.get("heads", {}).get(pr.get("headRefOid") or "", {})
    return bool(head.get("done") or head.get("no_checks"))


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def watch(
    numbers: list[int],
    state_path: Path,
    timeout: float,
    interval: float,
    appear_timeout: float,
    until: str,
    fetch: Callable[[int], dict[str, Any]],
    out: Callable[[dict[str, Any]], None],
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Poll until the exit condition holds. Return the process exit status.

    `until` picks the exit condition:

    - event: exit after the first poll that reports anything. Also exit once every PR merged or closed.
    - checks: exit once every PR's checks finished or never appeared. A closed PR counts as finished.
    - merged: exit once every PR merged or closed. Until then, report events as a stream.
    """
    deadline = clock() + timeout
    failures = 0

    while True:
        state = load_state(state_path)
        events: list[dict[str, Any]] = []
        polled: list[dict[str, Any]] = []
        try:
            for number in numbers:
                pr = fetch(number)
                polled.append(pr)
                events += pr_events(state, pr, clock(), appear_timeout)
            failures = 0
        except GhError as e:
            failures += 1
            if failures >= ERROR_THRESHOLD:
                out({"event": "error", "message": str(e), "consecutive": failures})
                if until == "event":
                    return 2
                failures = 0

        save_state(state_path, state)
        for event in events:
            out(event)

        if until == "event" and events:
            return 0
        if len(polled) == len(numbers) and all(finished(pr, state, until) for pr in polled):
            return 0

        remaining = deadline - clock()
        if remaining <= 0:
            out({"event": "timeout", "prs": numbers, "after": int(timeout)})
            return 124
        sleep(min(interval, remaining))


# -- preflight -------------------------------------------------------------------------------


def ci_systems(root: Path) -> list[dict[str, Any]]:
    """Name the CI systems the checkout configures, and what reading their logs needs."""
    found = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir() and any(workflows.glob("*.y*ml")):
        found.append({"system": "github-actions", "logs": "gh run view --log-failed", "needs": ["gh"]})
    if any(root.glob("cloudbuild*.y*ml")):
        found.append({"system": "cloud-build", "logs": "gcloud builds log", "needs": ["gcloud"]})
    others = {
        ".circleci/config.yml": "circleci",
        ".buildkite": "buildkite",
        "Jenkinsfile": "jenkins",
        "azure-pipelines.yml": "azure-pipelines",
        ".travis.yml": "travis",
    }
    for rel, system in others.items():
        if (root / rel).exists():
            found.append({"system": system, "logs": "the check's details URL", "needs": []})
    return found


def protection_from_rules(rules: list[dict[str, Any]]) -> dict[str, Any]:
    checks: set[str] = set()
    approvals = 0
    threads = False
    for rule in rules:
        params = rule.get("parameters") or {}
        if rule.get("type") == "required_status_checks":
            checks |= {c.get("context") for c in params.get("required_status_checks") or [] if c.get("context")}
        elif rule.get("type") == "pull_request":
            approvals = max(approvals, params.get("required_approving_review_count") or 0)
            threads = threads or bool(params.get("required_review_thread_resolution"))
    return {"required_checks": sorted(checks), "required_approvals": approvals, "thread_resolution": threads}


def protection_from_classic(protection: dict[str, Any]) -> dict[str, Any]:
    status = protection.get("required_status_checks") or {}
    checks = set(status.get("contexts") or []) | {c.get("context") for c in status.get("checks") or []}
    reviews = protection.get("required_pull_request_reviews") or {}
    return {
        "required_checks": sorted(c for c in checks if c),
        "required_approvals": reviews.get("required_approving_review_count") or 0,
        "thread_resolution": bool((protection.get("required_conversation_resolution") or {}).get("enabled")),
    }


def merge_protection(*parts: dict[str, Any]) -> dict[str, Any]:
    return {
        "required_checks": sorted({c for p in parts for c in p["required_checks"]}),
        "required_approvals": max([p["required_approvals"] for p in parts] or [0]),
        "thread_resolution": any(p["thread_resolution"] for p in parts),
    }


def gcloud_status() -> str:
    try:
        result = subprocess.run(["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
                                capture_output=True, text=True)
    except FileNotFoundError:
        return "missing"
    if result.returncode != 0:
        return "error: " + (result.stderr.strip().splitlines() or ["unknown"])[-1]
    return "ok" if result.stdout.strip() else "unauthenticated"


def preflight(base: str | None) -> dict[str, Any]:
    report: dict[str, Any] = {"needs": []}
    try:
        gh(["auth", "status"])
        report["gh"] = "ok"
    except GhError as e:
        report["gh"] = f"error: {e}"
        report["needs"].append("gh cannot authenticate. Run it outside the sandbox, or run `gh auth login`.")
        return report

    owner, name = repo_slug()
    repo = graphql(REPO_QUERY, owner=owner, name=name)["repository"]
    base = base or repo["defaultBranchRef"]["name"]
    report["repo"] = {k: v for k, v in repo.items() if k != "defaultBranchRef"}
    report["base"] = base
    if repo.get("viewerPermission") not in ("WRITE", "MAINTAIN", "ADMIN"):
        report["needs"].append(f"viewer permission is {repo.get('viewerPermission')}; pushing a branch needs WRITE.")
    if not repo.get("autoMergeAllowed"):
        report["needs"].append("auto-merge is off for this repo; the loop must merge with `gh pr merge` once green.")

    slug = repo["nameWithOwner"]
    parts = []
    unknown = []
    try:
        parts.append(protection_from_rules(gh_json(["api", f"repos/{slug}/rules/branches/{base}"])))
    except GhError as e:
        unknown.append(f"rulesets: {e}")
    try:
        parts.append(protection_from_classic(gh_json(["api", f"repos/{slug}/branches/{base}/protection"])))
    except GhError as e:
        # 404 means no classic protection. Anything else, usually 403, means it could not be read.
        if "404" not in str(e) and "Not Found" not in str(e):
            unknown.append(f"branch protection: {e}")
    report["protection"] = merge_protection(*parts) if parts else None
    report["protection_unreadable"] = unknown

    report["ci"] = ci_systems(Path.cwd())
    if any("gcloud" in system["needs"] for system in report["ci"]):
        report["gcloud"] = gcloud_status()
        if report["gcloud"] != "ok":
            report["needs"].append(f"Cloud Build logs need gcloud, which is {report['gcloud']}. "
                                   "Run `gcloud auth login` before the loop starts.")
    return report


# -- thread actions --------------------------------------------------------------------------


def marked(body: str) -> str:
    return body if MARKER in body else f"{body.rstrip()}\n\n{MARKER}"


def failures_of(pr: dict[str, Any]) -> list[dict[str, Any]]:
    checks, _ = checks_of(pr)
    result = []
    for check in checks:
        if check["bucket"] != FAIL:
            continue
        url = check["url"] or ""
        entry = {**check, "system": "other"}
        actions = re.search(r"/actions/runs/(\d+)(?:/job/(\d+))?", url)
        if actions:
            entry.update(system="github-actions", run=actions.group(1), job=actions.group(2))
        elif "cloud-build" in url or "cloudbuild" in url:
            build = re.search(r"/builds(?:;region=[^/]+)?/([0-9a-f-]{36})", url)
            region = re.search(r"region=([a-z0-9-]+)", url)
            entry.update(system="cloud-build", build=build.group(1) if build else None,
                         region=region.group(1) if region else None)
        result.append(entry)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pr_watch.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", help="report gh access, merge settings, protection, and CI log needs")
    p.add_argument("--base", help="branch the PRs target; defaults to the repo's default branch")

    p = sub.add_parser("snapshot", help="print one PR's state, checks, and unresolved thread count")
    p.add_argument("--pr", type=int, required=True)

    p = sub.add_parser("watch", help="poll PRs and print one JSON line per new event")
    p.add_argument("--pr", type=int, action="append", required=True, help="repeat to watch several PRs")
    p.add_argument("--state", type=Path, required=True, help="file recording what was already reported")
    p.add_argument("--timeout", type=float, required=True, help="seconds before printing a timeout event")
    p.add_argument("--interval", type=float, default=60, help="seconds between polls (default 60)")
    p.add_argument("--appear-timeout", type=float, default=600,
                   help="seconds to wait for a head commit's first check before reporting no-checks (default 600)")
    p.add_argument("--until", choices=("event", "checks", "merged"), default="event",
                   help="event: exit on the first event; checks: exit when checks finish; "
                        "merged: stream events until every PR merges or closes (default event)")

    p = sub.add_parser("threads", help="print a PR's unresolved review threads")
    p.add_argument("--pr", type=int, required=True)

    p = sub.add_parser("failures", help="print a PR's failing checks, with run or build IDs for log lookup")
    p.add_argument("--pr", type=int, required=True)

    p = sub.add_parser("reply", help="reply to a review thread; the body gets the loop's marker")
    p.add_argument("--thread", required=True)
    p.add_argument("--body-file", type=Path, required=True)

    p = sub.add_parser("comment", help="post a conversation comment; the body gets the loop's marker")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--body-file", type=Path, required=True)

    p = sub.add_parser("resolve", help="resolve a review thread")
    p.add_argument("--thread", required=True)

    args = parser.parse_args(argv[1:])

    def emit(obj: Any) -> None:
        print(json.dumps(obj), flush=True)

    try:
        if args.command == "preflight":
            emit(preflight(args.base))
        elif args.command in ("snapshot", "threads", "failures"):
            pr = fetch_pr(*repo_slug(), args.pr)
            if args.command == "snapshot":
                emit(summarize(pr))
            elif args.command == "threads":
                emit([thread_view(t) for t in pr["reviewThreads"]["nodes"] if not t["isResolved"]])
            else:
                emit(failures_of(pr))
        elif args.command == "watch":
            owner, name = repo_slug()
            return watch(args.pr, args.state, args.timeout, args.interval, args.appear_timeout, args.until,
                         lambda n: fetch_pr(owner, name, n), emit)
        elif args.command == "reply":
            data = graphql(REPLY_MUTATION, thread=args.thread, body=marked(args.body_file.read_text()))
            emit(data["addPullRequestReviewThreadReply"]["comment"])
        elif args.command == "comment":
            url = gh(["pr", "comment", str(args.pr), "--body", marked(args.body_file.read_text())]).strip()
            emit({"url": url})
        elif args.command == "resolve":
            emit(graphql(RESOLVE_MUTATION, thread=args.thread)["resolveReviewThread"]["thread"])
    except (GhError, OSError) as e:
        print(f"pr_watch: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
