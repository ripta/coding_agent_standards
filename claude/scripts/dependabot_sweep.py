#!/usr/bin/env python3
"""Do the deterministic parts of sweeping an owner's open dependabot PRs.

    python3 dependabot_sweep.py inventory --owner OWNER [--limit N] [--out FILE]
    python3 dependabot_sweep.py provenance --repo OWNER/NAME --pr N
    python3 dependabot_sweep.py classify --inventory FILE [--repo OWNER/NAME] [--out FILE]
    python3 dependabot_sweep.py fork --repo OWNER/NAME
    python3 dependabot_sweep.py updates --repo OWNER/NAME [--limit N]
    python3 dependabot_sweep.py last-comment --repo OWNER/NAME --pr N
    python3 dependabot_sweep.py merge-method --repo OWNER/NAME [--limit N]

Every subcommand prints JSON on stdout. Nothing here writes to GitHub. `gh` reads its credentials
from ~/.config/gh, which a sandboxed shell cannot read, so run this script through cg or with the
sandbox disabled.

`classify` trusts nothing it has not checked. It runs the provenance check on every PR first, then
sorts each PR into one bucket. A PR that is mergeable with no checks at all gets its own bucket,
because a clean merge state with nothing run is not evidence that the change works.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import pr_watch

DEPENDABOT_LOGIN = "dependabot[bot]"
DEPENDABOT_NODE_ID = "MDM6Qm90NDk2OTkzMzM="
DEPENDABOT_URL = "https://github.com/apps/dependabot"

SEARCH_FIELDS = "repository,number,title,author,createdAt,url,isDraft"
REPO_FIELDS = ("isFork,isArchived,pushedAt,parent,defaultBranchRef,autoMergeAllowed,"
               "mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed")
PR_FIELDS = "number,state,mergeable,mergeStateStatus,statusCheckRollup,baseRefName,headRefOid"

BUCKETS = (
    "provenance-flagged", "archived", "fork", "conflicting", "comment-gated", "needs-approval", "red",
    "waiting-on-ci", "no-checks", "green", "unknown",
)

PASS, FAIL, PENDING, ACTION_REQUIRED = "pass", "fail", "pending", "action_required"

NEEDS_COMMAND = re.compile(r"Needs\s+(/gcbrun\S*)")
UPDATE_JOB = re.compile(r"^(?P<ecosystem>\S+) in (?P<directory>\S+) for .* - Update #(?P<id>\d+)$")


def gh_json(args: list[str]) -> Any:
    return pr_watch.gh_json(args)


# -- inventory -------------------------------------------------------------------------------


def login_of(author: dict[str, Any] | None) -> str:
    """Return the author's login without the `app/` prefix and `[bot]` suffix gh may add."""
    login = (author or {}).get("login") or "ghost"
    login = login.removeprefix("app/")
    return login.removesuffix("[bot]")


def is_bot(author: dict[str, Any] | None) -> bool:
    author = author or {}
    login = author.get("login") or ""
    return bool(author.get("is_bot")) or login.endswith("[bot]") or login.startswith("app/")


def repo_tags(slug: str) -> dict[str, Any]:
    repo = gh_json(["repo", "view", slug, "--json", REPO_FIELDS])
    parent = repo.get("parent") or {}
    parent_slug = parent.get("nameWithOwner")
    if not parent_slug and parent.get("name"):
        parent_slug = f"{(parent.get('owner') or {}).get('login')}/{parent['name']}"
    methods = [m for m, key in (("merge", "mergeCommitAllowed"), ("squash", "squashMergeAllowed"),
                                ("rebase", "rebaseMergeAllowed")) if repo.get(key)]
    return {
        "fork": bool(repo.get("isFork")),
        "archived": bool(repo.get("isArchived")),
        "pushed_at": repo.get("pushedAt"),
        "parent": parent_slug,
        "default_branch": (repo.get("defaultBranchRef") or {}).get("name"),
        "auto_merge_allowed": bool(repo.get("autoMergeAllowed")),
        "merge_methods": methods,
    }


def inventory(owner: str, limit: int) -> dict[str, Any]:
    found = gh_json(["search", "prs", "--owner", owner, "--state", "open", "--limit", str(limit),
                     "--json", SEARCH_FIELDS])
    records = sorted(
        (
            {
                "repo": (pr.get("repository") or {}).get("nameWithOwner"),
                "number": pr["number"],
                "title": pr.get("title"),
                "author": login_of(pr.get("author")),
                "bot": is_bot(pr.get("author")),
                "created_at": pr.get("createdAt"),
                "url": pr.get("url"),
                "draft": bool(pr.get("isDraft")),
            }
            for pr in found
        ),
        key=lambda r: (r["created_at"] or "", r["repo"] or "", r["number"]),
    )

    by_author: dict[str, int] = {}
    for record in records:
        by_author[record["author"]] = by_author.get(record["author"], 0) + 1

    repos: dict[str, Any] = {}
    for slug in sorted({r["repo"] for r in records if r["repo"]}):
        try:
            repos[slug] = repo_tags(slug)
        except pr_watch.GhError as e:
            repos[slug] = {"error": str(e)}

    return {
        "owner": owner,
        "total": len(records),
        "truncated": len(records) >= limit,
        "by_author": dict(sorted(by_author.items(), key=lambda kv: (-kv[1], kv[0]))),
        "dependabot": [r for r in records if r["author"] == "dependabot"],
        "other_bots": [r for r in records if r["bot"] and r["author"] != "dependabot"],
        "contributors": [r for r in records if not r["bot"]],
        "repos": repos,
    }


# -- provenance ------------------------------------------------------------------------------


def provenance(slug: str, number: int) -> dict[str, Any]:
    """Check that dependabot opened the PR and that every commit on it is dependabot's, signed."""
    pr = gh_json(["api", f"repos/{slug}/pulls/{number}"])
    commits = gh_json(["api", f"repos/{slug}/pulls/{number}/commits?per_page=100"])

    user = pr.get("user") or {}
    head_repo = (pr.get("head") or {}).get("repo") or {}
    base_repo = (pr.get("base") or {}).get("repo") or {}
    cross = head_repo.get("full_name") != base_repo.get("full_name")

    flags = []
    if user.get("node_id") != DEPENDABOT_NODE_ID:
        flags.append(f"author node ID is {user.get('node_id')!r}, not dependabot's")
    if user.get("type") != "Bot":
        flags.append(f"author type is {user.get('type')!r}, not Bot")
    if user.get("html_url") != DEPENDABOT_URL:
        flags.append(f"author URL is {user.get('html_url')!r}, not {DEPENDABOT_URL}")
    if cross:
        flags.append("the head branch is in a different repository")

    foreign, unverified = [], []
    for commit in commits:
        sha = commit.get("sha")
        author = (commit.get("author") or {}).get("login")
        verified = bool(((commit.get("commit") or {}).get("verification") or {}).get("verified"))
        if author != DEPENDABOT_LOGIN:
            foreign.append({"sha": sha, "author": author})
        if not verified:
            unverified.append(sha)
    if foreign:
        flags.append(f"{len(foreign)} commit(s) not authored by {DEPENDABOT_LOGIN}")
    if unverified:
        flags.append(f"{len(unverified)} commit(s) without a verified signature")
    if len(commits) >= 100:
        flags.append("the PR has 100 or more commits, so the list may be cut off")

    return {
        "repo": slug,
        "pr": number,
        "ok": not flags,
        "is_cross_repository": cross,
        "commits": len(commits),
        "foreign_commits": foreign,
        "unverified_commits": unverified,
        "flags": flags,
    }


# -- classification --------------------------------------------------------------------------


def check_bucket(node: dict[str, Any]) -> str:
    """Sort one rollup entry into pass, fail, pending, or action_required.

    An empty or null conclusion means the check has not finished, whatever else the node says.
    """
    if node.get("__typename") == "StatusContext":
        state = (node.get("state") or "").upper()
        return PASS if state == "SUCCESS" else FAIL if state in ("FAILURE", "ERROR") else PENDING

    conclusion = (node.get("conclusion") or "").upper()
    if conclusion == "":
        return PENDING
    if conclusion == "ACTION_REQUIRED":
        return ACTION_REQUIRED
    return PASS if conclusion in pr_watch.PASSING_CONCLUSIONS else FAIL


def check_name(node: dict[str, Any]) -> str:
    return node.get("name") or node.get("context") or "?"


def gate_command(summary: str | None, sha: str) -> str | None:
    """Return the comment a comment-gated check asks for, or None when its summary asks for none."""
    match = NEEDS_COMMAND.search(summary or "")
    if not match:
        return None
    return f"/gcbrun({sha})" if "(" in match.group(1) else "/gcbrun"


def gated_checks(slug: str, sha: str, names: list[str]) -> list[dict[str, Any]]:
    data = gh_json(["api", f"repos/{slug}/commits/{sha}/check-runs?per_page=100"])
    result = []
    for run in data.get("check_runs") or []:
        if run.get("name") not in names or (run.get("conclusion") or "").lower() != "action_required":
            continue
        summary = (run.get("output") or {}).get("summary") or ""
        result.append({"name": run["name"], "command": gate_command(summary, sha), "summary": summary[:200]})
    return result


def bucket_for(detail: dict[str, Any], prov: dict[str, Any], tags: dict[str, Any],
               gated: list[dict[str, Any]]) -> str:
    states = [check_bucket(n) for n in detail.get("statusCheckRollup") or []]
    if not prov["ok"]:
        return "provenance-flagged"
    if tags.get("archived"):
        return "archived"
    if tags.get("fork"):
        return "fork"
    if detail.get("mergeable") == "CONFLICTING" or detail.get("mergeStateStatus") == "DIRTY":
        return "conflicting"
    if ACTION_REQUIRED in states:
        return "comment-gated" if any(g["command"] for g in gated) else "needs-approval"
    if FAIL in states:
        return "red"
    if PENDING in states:
        return "waiting-on-ci"
    if not states:
        return "no-checks"
    if detail.get("mergeable") == "MERGEABLE":
        return "green"
    return "unknown"


def settled_detail(slug: str, number: int, retries: int, delay: float,
                   sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Read the PR, asking again while GitHub has not computed whether it merges.

    GitHub computes `mergeable` lazily. The first read after a push often says UNKNOWN.
    """
    detail = gh_json(["pr", "view", str(number), "-R", slug, "--json", PR_FIELDS])
    for _ in range(retries):
        if detail.get("mergeable") != "UNKNOWN":
            break
        sleep(delay)
        detail = gh_json(["pr", "view", str(number), "-R", slug, "--json", PR_FIELDS])
    return detail


def base_protection(slug: str, base: str) -> dict[str, Any] | None:
    """Return the base branch's required checks, or None when they cannot be read."""
    parts = []
    try:
        parts.append(pr_watch.protection_from_rules(gh_json(["api", f"repos/{slug}/rules/branches/{base}"])))
    except pr_watch.GhError:
        return None
    try:
        parts.append(pr_watch.protection_from_classic(gh_json(["api", f"repos/{slug}/branches/{base}/protection"])))
    except pr_watch.GhError as e:
        if "404" not in str(e) and "Not Found" not in str(e):
            return None
    return pr_watch.merge_protection(*parts)


def classify(inv: dict[str, Any], only_repo: str | None, retries: int, delay: float,
             sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    settings: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []

    for record in inv.get("dependabot") or []:
        slug, number = record["repo"], record["number"]
        if only_repo and slug != only_repo:
            continue
        tags = (inv.get("repos") or {}).get(slug) or {}
        try:
            prov = provenance(slug, number)
            detail = settled_detail(slug, number, retries, delay, sleep)
            states = {check_name(n): check_bucket(n) for n in detail.get("statusCheckRollup") or []}
            waiting = [name for name, state in states.items() if state == ACTION_REQUIRED]
            gated = gated_checks(slug, detail["headRefOid"], waiting) if waiting else []

            base = detail.get("baseRefName")
            if (slug, base) not in settings and not tags.get("fork") and not tags.get("archived"):
                protection = base_protection(slug, base)
                required = None if protection is None else protection["required_checks"]
                settings[(slug, base)] = {
                    "repo": slug,
                    "base": base,
                    "auto_merge_allowed": tags.get("auto_merge_allowed"),
                    "required_checks": required,
                    "auto_merge_waits_for_checks": bool(required),
                    "merge_methods": tags.get("merge_methods"),
                }
        except pr_watch.GhError as e:
            errors.append({"repo": slug, "pr": number, "error": str(e)})
            continue

        items.append({
            "repo": slug,
            "number": number,
            "url": record.get("url"),
            "title": record.get("title"),
            "created_at": record.get("created_at"),
            "bucket": bucket_for(detail, prov, tags, gated),
            "mergeable": detail.get("mergeable"),
            "merge_state": detail.get("mergeStateStatus"),
            "sha": detail.get("headRefOid"),
            "base": detail.get("baseRefName"),
            "checks": {
                state: sorted(n for n, s in states.items() if s == state)
                for state in (PASS, FAIL, PENDING, ACTION_REQUIRED)
            },
            "gated": gated,
            "provenance_flags": prov["flags"],
        })

    by_bucket = {b: [f"{i['repo']}#{i['number']}" for i in items if i["bucket"] == b] for b in BUCKETS}
    return {
        "counts": {b: len(v) for b, v in by_bucket.items() if v},
        "buckets": {b: v for b, v in by_bucket.items() if v},
        "items": items,
        "repo_settings": list(settings.values()),
        "errors": errors,
    }


# -- forks -----------------------------------------------------------------------------------


def endpoint_enabled(path: str) -> bool | None:
    """Return whether a settings endpoint says enabled. A 404 means disabled. None means unreadable."""
    try:
        data = gh_json(["api", path])
    except pr_watch.GhError as e:
        if "404" in str(e) or "Not Found" in str(e):
            return False
        return None
    except json.JSONDecodeError:
        return True
    return bool(data.get("enabled", True)) if isinstance(data, dict) else True


def fork_report(slug: str) -> dict[str, Any]:
    tags = repo_tags(slug)
    if not tags["fork"]:
        return {"repo": slug, "fork": False}

    owner = slug.split("/")[0]
    name = slug.split("/")[1]
    branch = tags["default_branch"]
    report: dict[str, Any] = {"repo": slug, "fork": True, "parent": tags["parent"], "archived": tags["archived"]}

    compare = gh_json(["api", f"repos/{tags['parent']}/compare/{branch}...{owner}:{name}:{branch}"])
    report["ahead_by"] = compare.get("ahead_by")
    report["behind_by"] = compare.get("behind_by")
    report["has_own_commits"] = bool(compare.get("ahead_by"))

    configs = []
    for filename in ("dependabot.yml", "dependabot.yaml"):
        try:
            gh_json(["api", f"repos/{slug}/contents/.github/{filename}"])
            configs.append(filename)
        except pr_watch.GhError:
            pass
    report["dependabot_config"] = configs
    report["vulnerability_alerts"] = endpoint_enabled(f"repos/{slug}/vulnerability-alerts")
    report["automated_security_fixes"] = endpoint_enabled(f"repos/{slug}/automated-security-fixes")
    return report


# -- dependabot activity ---------------------------------------------------------------------


def update_runs(slug: str, limit: int) -> dict[str, Any]:
    """List dependabot's update jobs. They show up as Actions runs with the event `dynamic`."""
    data = gh_json(["api", f"repos/{slug}/actions/runs?actor=dependabot%5Bbot%5D&per_page={limit}"])
    updates, graph = [], 0
    for run in data.get("workflow_runs") or []:
        if run.get("event") != "dynamic":
            continue
        name = run.get("name") or ""
        if name.startswith("Configured Graph Update"):
            graph += 1
            continue
        match = UPDATE_JOB.match(name)
        updates.append({
            "name": name,
            "ecosystem": match.group("ecosystem") if match else None,
            "directory": match.group("directory") if match else None,
            "job": match.group("id") if match else None,
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "created_at": run.get("created_at"),
            "url": run.get("html_url"),
        })
    return {"repo": slug, "updates": updates, "graph_updates_skipped": graph}


def last_dependabot_comment(slug: str, number: int) -> dict[str, Any]:
    data = gh_json(["pr", "view", str(number), "-R", slug, "--json", "comments"])
    mine = [c for c in data.get("comments") or [] if login_of(c.get("author")) == "dependabot"]
    if not mine:
        return {"repo": slug, "pr": number, "comment": None}
    latest = max(mine, key=lambda c: c.get("createdAt") or "")
    return {"repo": slug, "pr": number, "comment": {
        "created_at": latest.get("createdAt"), "url": latest.get("url"), "body": latest.get("body")}}


# -- merge method ----------------------------------------------------------------------------


def merge_method_of(commit: dict[str, Any], number: int) -> str:
    if len(commit.get("parents") or []) > 1:
        return "merge"
    subject = ((commit.get("commit") or {}).get("message") or "").splitlines()[0:1]
    if subject and subject[0].rstrip().endswith(f"(#{number})"):
        return "squash"
    return "rebase"


def merge_method(slug: str, limit: int) -> dict[str, Any]:
    merged = gh_json(["pr", "list", "-R", slug, "--state", "merged", "--limit", str(limit),
                      "--json", "number,mergeCommit"])
    seen: dict[str, int] = {}
    for pr in merged:
        oid = (pr.get("mergeCommit") or {}).get("oid")
        if not oid:
            continue
        method = merge_method_of(gh_json(["api", f"repos/{slug}/commits/{oid}"]), pr["number"])
        seen[method] = seen.get(method, 0) + 1
    most = max(seen, key=lambda m: seen[m]) if seen else None
    return {"repo": slug, "observed": seen, "most_common": most}


# -- command line ----------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dependabot_sweep.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inventory", help="list an owner's open PRs, grouped by author, with each repo's tags")
    p.add_argument("--owner", required=True)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--out", type=Path, help="also save the JSON to this file")

    p = sub.add_parser("provenance", help="check that dependabot opened the PR and wrote every commit")
    p.add_argument("--repo", required=True, metavar="OWNER/NAME")
    p.add_argument("--pr", type=int, required=True)

    p = sub.add_parser("classify", help="check provenance and sort an inventory's dependabot PRs into buckets")
    p.add_argument("--inventory", type=Path, required=True, help="a file saved by `inventory --out`")
    p.add_argument("--repo", metavar="OWNER/NAME", help="classify only this repository's PRs")
    p.add_argument("--retries", type=int, default=3, help="rereads while mergeable is UNKNOWN (default 3)")
    p.add_argument("--retry-delay", type=float, default=5, help="seconds between rereads (default 5)")
    p.add_argument("--out", type=Path, help="also save the JSON to this file")

    p = sub.add_parser("fork", help="report whether a fork has commits of its own and its dependabot settings")
    p.add_argument("--repo", required=True, metavar="OWNER/NAME")

    p = sub.add_parser("updates", help="list dependabot's update jobs, which appear as Actions runs")
    p.add_argument("--repo", required=True, metavar="OWNER/NAME")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("last-comment", help="print dependabot's latest comment on a PR")
    p.add_argument("--repo", required=True, metavar="OWNER/NAME")
    p.add_argument("--pr", type=int, required=True)

    p = sub.add_parser("merge-method", help="infer the merge method from the repo's recent merged PRs")
    p.add_argument("--repo", required=True, metavar="OWNER/NAME")
    p.add_argument("--limit", type=int, default=5)

    args = parser.parse_args(argv[1:])

    try:
        if args.command == "inventory":
            result = inventory(args.owner, args.limit)
        elif args.command == "provenance":
            result = provenance(args.repo, args.pr)
        elif args.command == "classify":
            result = classify(json.loads(args.inventory.read_text()), args.repo, args.retries, args.retry_delay)
        elif args.command == "fork":
            result = fork_report(args.repo)
        elif args.command == "updates":
            result = update_runs(args.repo, args.limit)
        elif args.command == "last-comment":
            result = last_dependabot_comment(args.repo, args.pr)
        else:
            result = merge_method(args.repo, args.limit)

        out = getattr(args, "out", None)
        if out:
            out.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    except (pr_watch.GhError, OSError, ValueError) as e:
        print(f"dependabot_sweep: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
