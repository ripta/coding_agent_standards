"""Find the remote that holds the repo PRs land in, shared by pr_watch.py and tracker-sync.

In a fork checkout `origin` is the user's fork and the base repo is on another remote, often
`upstream`. Callers that read `origin` as the base repo get the fork's copy of everything.

A fork checkout can land PRs in either repo. The user's choice is the PR target, saved per fork in
PR_TARGETS_FILE as `parent` or `fork`. `gh repo set-default` is the other way to choose, and it
holds for one clone only.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Callable

PR_TARGETS_FILE = "~/.config/coding_agent_standards/pr-targets.json"
PR_TARGETS = ("parent", "fork")


class GhError(Exception):
    pass


class BaseRepoUnsettled(Exception):
    """The checkout's base repo depends on a choice the user has not made, or made twice differently."""


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


SLUG_TAIL = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?(/?)$")


def sibling_url(url: str, slug: str) -> str | None:
    """Point a clone URL at another repo on the same host, keeping its scheme, user, port, and alias.

    A fork and its parent live on one host, so the parent's URL is the fork's with the owner/name
    swapped. Returns None when `url` names no owner/name to swap.
    """
    url = url.strip()
    if remote_slug(url) is None:
        return None
    return SLUG_TAIL.sub(lambda m: slug + (m.group(1) or "") + m.group(2), url, count=1)


def saved_pr_target(key: str) -> str | None:
    """Read the PR target saved for the fork `key`, shaped {"repos": {key: {"target": ...}}}.

    Keys match case-insensitively. A missing file, or no target for the fork, gives None. A file
    that cannot be parsed, or a target that is neither `parent` nor `fork`, raises ValueError.
    """
    path = Path(PR_TARGETS_FILE).expanduser()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{PR_TARGETS_FILE} cannot be read: {e}") from e

    for saved, settings in ((data.get("repos") if isinstance(data, dict) else None) or {}).items():
        if saved.lower() == key.lower() and isinstance(settings, dict) and settings.get("target") is not None:
            target = settings["target"]
            if target not in PR_TARGETS:
                raise ValueError(f"{PR_TARGETS_FILE}: the target for {saved} is {target!r}, "
                                 f"not one of {', '.join(PR_TARGETS)}")
            return target
    return None


def decide_pr_target(fork: str, parent: str, key: str, saved: str | None,
                     explicit: str | None) -> tuple[str | None, str | None]:
    """Settle where a fork checkout's PRs land, from the saved target and gh's explicit choice.

    `explicit` is `parent` or `fork` when `gh repo set-default` named one of the two, else None.
    gh's own pick when nothing was set is a heuristic, not a choice, so callers pass None for it.
    Returns the target, or None and the need that says what the user must decide.
    """
    where = f'`repos["{key}"].target` in {PR_TARGETS_FILE}'
    repos = {"parent": parent, "fork": fork}
    if saved and explicit and saved != explicit:
        return None, (f"{where} lands PRs from {fork} in {repos[saved]}, but `gh repo set-default` in this "
                      f"checkout chose {repos[explicit]}. Ask the user which repo the PRs land in. Save it as "
                      f"`parent` or `fork` in {where}, run `gh repo set-default --unset`, then rerun.")
    if saved or explicit:
        return saved or explicit, None
    return None, (f"this checkout's {fork} is a fork of {parent}, and no PR target is saved for it. Ask the user "
                  f"whether PRs land in {parent} (`parent`) or in {fork} (`fork`). Save the answer in {where}, "
                  f"then rerun.")


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
        url = sibling_url(urls.get("origin") or next(iter(urls.values()), ""), base) or f"https://github.com/{base}.git"
        report["needs"].append(f"no git remote points at {base}. Add one with "
                               f"`git remote add upstream {url}`, then fetch it.")
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


def gh_base_repo(root: Path) -> dict[str, str | None] | None:
    """Ask gh for the base repo's owner/name as `slug`, and its parent's as `parent` when it is a fork.

    None when gh is missing, signed out, or offline, or when the host is one gh does not serve.
    """
    try:
        result = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner,parent"],
                                cwd=root, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(data, dict) or "/" not in (data.get("nameWithOwner") or ""):
        return None

    parent = data.get("parent") or {}
    login, name = (parent.get("owner") or {}).get("login"), parent.get("name")
    return {"slug": data["nameWithOwner"], "parent": f"{login}/{name}" if login and name else None}


def find_base_remote(root: Path,
                     lookup: Callable[[Path], dict[str, str | None] | None] = gh_base_repo) -> str | None:
    """Name the remote that holds the base repo, or None when the checkout has no remote.

    A saved PR target comes first. A remote whose fork is saved as `fork` is the base. A lone remote
    is the base unless gh says it is a fork. Then the saved target or `gh repo set-default` must
    settle it, or this raises BaseRepoUnsettled with what to do. With several remotes, gh's answer
    picks the remote whose URL names that repo. When gh cannot answer, or no remote holds its
    answer, the fallback is a remote named `upstream`, then `origin`. The fallback is a guess,
    which is why gh comes first.
    """
    urls, resolved, _ = git_remotes(root)
    if not urls:
        return None
    try:
        saved = {name: saved_pr_target(key) for name, key in ((n, repo_key(u)) for n, u in urls.items()) if key}
    except ValueError as e:
        raise BaseRepoUnsettled(f"{e}. Fix the file, then rerun.") from e
    if len(urls) == 1:
        return lone_base_remote(root, next(iter(urls.items())), resolved, saved, lookup)

    slugs = {name: remote_slug(url) or url for name, url in urls.items()}
    chosen = sorted(name for name, target in saved.items() if target == "fork")
    if len(chosen) > 1:
        raise BaseRepoUnsettled(f"remotes {', '.join(chosen)} each have `fork` saved as their PR target in "
                                f"{PR_TARGETS_FILE}. Keep it for the one PRs land in, then rerun.")
    if chosen:
        name = chosen[0]
        if resolved and resolved != name:
            raise BaseRepoUnsettled(decide_pr_target(slugs[name], slugs[resolved], repo_key(urls[name]) or name,
                                                     "fork", "parent")[1])
        return name
    if resolved and saved.get(resolved) == "parent":
        parent = (lookup(root) or {}).get("parent") or f"the parent of {slugs[resolved]}"
        raise BaseRepoUnsettled(decide_pr_target(slugs[resolved], parent, repo_key(urls[resolved]) or resolved,
                                                 "parent", "fork")[1])

    base = (lookup(root) or {}).get("slug")
    if base:
        holders = sorted(name for name, url in urls.items() if (remote_slug(url) or "").lower() == base.lower())
        if holders:
            return pick_mainline(holders, resolved)

    for name in ("upstream", "origin"):
        if name in urls:
            return name
    return None


def lone_base_remote(root: Path, remote: tuple[str, str], resolved: str | None, saved: dict[str, str | None],
                     lookup: Callable[[Path], dict[str, str | None] | None]) -> str:
    """Settle the base of a checkout whose one remote may be a fork whose parent no remote holds."""
    name, url = remote
    target = saved.get(name)
    if target == "fork":
        return name

    repo = lookup(root) or {}
    fork, parent = repo.get("slug") or remote_slug(url) or url, repo.get("parent")
    if not parent:
        if target == "parent":
            raise BaseRepoUnsettled(f"`parent` is saved as the PR target for {fork} in {PR_TARGETS_FILE}, but gh "
                                    f"cannot name its parent. Check `gh auth status`, then rerun.")
        return name

    target, need = decide_pr_target(fork, parent, repo_key(url) or url, target, "fork" if resolved == name else None)
    if target == "fork":
        return name
    if target == "parent":
        raise BaseRepoUnsettled(f"PRs from {fork} land in {parent}, which no remote here holds. Run "
                                f"`git remote add upstream {sibling_url(url, parent)}` and `git fetch upstream`, "
                                f"then rerun.")
    raise BaseRepoUnsettled(need)
