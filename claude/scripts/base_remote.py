"""Find the remote that holds the repo PRs land in, shared by pr_watch.py and tracker-sync.

In a fork checkout `origin` is the user's fork and the base repo is on another remote, often
`upstream`. Callers that read `origin` as the base repo get the fork's copy of everything.
"""

from __future__ import annotations

import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Callable


class GhError(Exception):
    pass


# A remote URL names its repo by its last two path segments, on any host. SSH host aliases, user
# names in the URL, and GitHub Enterprise hosts all leave those segments alone, and gh reports the
# repo as the same owner/name.
REMOTE_URL = re.compile(r"^(?:[a-z+]+://[^/]+/|[^/:]+:)(?:.*/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def repo_key(url: str) -> str | None:
    """Reduce a clone URL to host/path, the key machine-local config files save a repo under.

    SSH and HTTPS clones of one repo reduce to the same key. The host is lowercased and the path is
    kept as written, so callers compare keys case-insensitively. Returns None for a URL with no host.
    """
    url = url.strip()
    scp = re.match(r"^[\w.-]+@([\w.-]+):(?!//)(.+)$", url)
    if scp:
        host, path = scp.groups()
    else:
        parts = urllib.parse.urlsplit(url)
        if not parts.scheme or not parts.hostname:
            return None
        host, path = parts.hostname, parts.path
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return f"{host.lower()}/{path}"


def remote_slug(url: str) -> str | None:
    match = REMOTE_URL.match(url.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def git_remotes(root: Path) -> tuple[dict[str, str], str | None, str | None]:
    """Return the checkout's remote URLs, the remote gh resolved as the base, and remote.pushDefault."""

    def config(*args: str) -> list[str]:
        result = subprocess.run(["git", "config", *args], cwd=root, capture_output=True, text=True)
        return result.stdout.splitlines() if result.returncode == 0 else []

    urls = {}
    for line in config("--get-regexp", r"^remote\..*\.url$"):
        key, _, url = line.partition(" ")
        urls[key[len("remote."):-len(".url")]] = url

    resolved = None
    for line in config("--get-regexp", r"^remote\..*\.gh-resolved$"):
        key, _, value = line.partition(" ")
        if value == "base":
            resolved = key[len("remote."):-len(".gh-resolved")]

    push_default = (config("--get", "remote.pushDefault") or [None])[0]
    return urls, resolved, push_default


def pick_mainline(holders: list[str], resolved: str | None) -> str:
    """Choose among remotes that hold the base repo. `holders` is sorted and not empty."""
    return resolved if resolved in holders else "origin" if "origin" in holders else holders[0]


def resolve_remotes(urls: dict[str, str], base: str, resolved: str | None, push_default: str | None,
                    lookup: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """Name the remote that holds the base repo and the remote that agent branches push to.

    A fork checkout fetches the mainline from one remote, often `upstream`, and pushes to the fork,
    often `origin`. A PR from a fork names its head as `owner:branch`, so `head_prefix` carries the
    owner. `lookup(slug)` returns the repo's `parent` slug and whether the viewer `can_push` to it.

    Anything this cannot settle goes in `needs` with what to run, and its remote stays None. A
    guess here would fetch a stale mainline or push to a repo nobody reviews.
    """
    slugs = {name: remote_slug(url) for name, url in urls.items()}
    report: dict[str, Any] = {"mainline": None, "push": None, "push_repo": None, "fork": False,
                              "head_prefix": "", "needs": []}

    holders = sorted(name for name, slug in slugs.items() if slug and slug.lower() == base.lower())
    if not holders:
        report["needs"].append(f"no git remote points at {base}. Add one with "
                               f"`git remote add upstream https://github.com/{base}.git`, then fetch it.")
        return report
    mainline = pick_mainline(holders, resolved)
    report["mainline"] = mainline

    def settle(push: str, info: dict[str, Any] | None) -> dict[str, Any]:
        push_repo = slugs.get(push) or base
        fork = push_repo.lower() != base.lower()
        report.update(push=push, push_repo=push_repo, fork=fork,
                      head_prefix=push_repo.split("/")[0] + ":" if fork else "")
        if fork and info is not None and not info.get("can_push"):
            report["needs"].append(f"the viewer cannot push to {push_repo}, the fork on remote {push}.")
        return report

    if push_default:
        if push_default not in urls:
            report["needs"].append(f"remote.pushDefault names {push_default}, which is not a remote here.")
            return report
        return settle(push_default, None)

    forks = {}
    for name in sorted(urls):
        slug = slugs[name]
        if name in holders or not slug:
            continue
        try:
            info = lookup(slug)
        except GhError as e:
            report["needs"].append(f"cannot tell whether remote {name} ({slug}) is a fork of {base}: {e}. "
                                   f"Set `git config remote.pushDefault <remote>` to name the push remote.")
            return report
        if (info.get("parent") or "").lower() == base.lower():
            forks[name] = info

    if not forks:
        return settle(mainline, None)
    if len(forks) == 1:
        name = next(iter(forks))
        return settle(name, forks[name])
    if "origin" in forks:
        return settle("origin", forks["origin"])
    report["needs"].append(f"remotes {', '.join(sorted(forks))} are all forks of {base}. "
                           f"Set `git config remote.pushDefault <remote>` to name the one to push to.")
    return report


def gh_base_slug(root: Path) -> str | None:
    """Ask gh for the base repo's owner/name. None when gh is missing, signed out, or offline."""
    try:
        result = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                                cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    slug = result.stdout.strip()
    return slug if result.returncode == 0 and "/" in slug else None


def find_base_remote(root: Path, lookup: Callable[[Path], str | None] = gh_base_slug) -> str | None:
    """Name the remote that holds the base repo, or None when the checkout has no remote.

    A checkout with one remote needs no lookup. With several, gh's answer picks the remote whose
    URL names that repo. When gh cannot answer, or no remote holds its answer, the fallback is a
    remote named `upstream`, then `origin`. The fallback is a guess, which is why gh comes first.
    """
    urls, resolved, _ = git_remotes(root)
    if not urls:
        return None
    if len(urls) == 1:
        return next(iter(urls))

    base = lookup(root)
    if base:
        holders = sorted(name for name, url in urls.items() if (remote_slug(url) or "").lower() == base.lower())
        if holders:
            return pick_mainline(holders, resolved)

    for name in ("upstream", "origin"):
        if name in urls:
            return name
    return None
