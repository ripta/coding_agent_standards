# Configuration

The plugin's skills, hooks, and scripts read user settings from two places: files in
`~/.config/coding_agent_standards/`, and `git config` keys under `codingstandards.`. Every setting goes in one of them,
by the rules below. A new setting never invents a third place.

Two other kinds of data look like settings but are not:

- A convention everyone on a project shares, such as its commit style or its proposals directory, belongs to the
  project. It lives in the project's committed instructions, or in its history. A skill detects it there.
- State that tools write as they run, such as a guardian's ledger or a run file, lives in
  `~/.local/state/coding_agent_standards/`. See "Machine-local state" in `skills/README.md`.

## Where a Setting Goes

A setting goes in `~/.config/coding_agent_standards/` by default. That covers a user's preference for a skill, and a
setting that belongs to a remote repo. A repo setting is saved under the base repo's key, so every clone, fork checkout,
worktree, and scratch clone of that repo finds it. See "Repo Keys".

A setting goes in `git config` only when it describes one checkout, and no repo key can name it. The example is
`codingstandards.visibility` for a repo with no remote. Such a repo has no host to key by, and no host to ask.

The test is what the setting belongs to:

- A user's preference, the same in every repo: a file in `~/.config/coding_agent_standards/`
- A fact about a remote repo, such as a host rule its branch names must meet: a file in
  `~/.config/coding_agent_standards/`, keyed by the base repo
- A fact about one checkout that has no repo key: `git config codingstandards.<key>`

`git config` is per clone. A re-clone loses it, and every worktree of a clone shares it. That is why a fact about a
remote repo does not go there.

## Files

- One JSON file per skill, named after the skill, such as `session-report.json`. A setting that several skills share
  through one script is named after what it configures, such as `branches.json`
- A file that a hook reads may take a simpler form when the hook needs one. `private-terms.txt` is a plain list, and
  `guardian-hooks/` is a directory of executables
- Precedence: an explicit value in the user's request, then the file, then asking the user. After asking, write the
  answer to the file
- Write the file with the Write or Edit tool, never through Bash. Keep entries you did not change. "Machine-local
  configuration" in `skills/README.md` says why Bash cannot write there
- Never commit the file anywhere, and never copy its values into a skill
- Validate what you read before relying on it. A stale value is re-asked and rewritten. A file that cannot be parsed is
  reported, never overwritten

### Repo Keys

A repo setting is keyed by the base repo: the repo PRs land in, not a fork. The key is that repo's remote URL reduced to
`host/path`, such as `github.com/acme/widget`. SSH and HTTPS clones reduce to the same key. `repo_key` in
`scripts/base_remote.py` computes it. Compare keys case-insensitively.

A file that holds repo settings keeps them under `repos`, one entry per key:

```json
{"repos": {"github.com/acme/widget": {"prefix": "me.agent."}}}
```

`tracker-sync.json` predates this shape. It keeps a `mappings` list whose entries name their `repo` by the same key.

## Git Config Keys

- Name a key `codingstandards.<name>`, with the name in lower camel case
- Only the user sets a key. The agent never writes one. A key can switch a guard off, as `codingstandards.visibility`
  does for the private-terms hook
- A key is never committed. Tell the user the exact `! git config codingstandards.<name> <value>` to run

## Inventory

Each setting the plugin reads is listed here. `tests/test_standards.py` fails when a file under `claude/` names a
setting this table does not list, or when the table lists one nothing names.

| Setting | Holds | Read by |
|---|---|---|
| `~/.config/coding_agent_standards/branches.json` | The prefix for agent-owned branch names, per repo | `pr_watch.py preflight` |
| `~/.config/coding_agent_standards/cloudbuild.json` | The GCP project, region, connections, and release app for Cloud Build | `cloudbuild`, `debug-ci` |
| `~/.config/coding_agent_standards/presentation.json` | Where decks are written, their theme, and their speaker notes | `presentation` |
| `~/.config/coding_agent_standards/session-report.json` | Where reports are written | `session-report`, `research-audit`, `presentation` |
| `~/.config/coding_agent_standards/tracker-sync.json` | Trackers, and the repo paths mapped to their groups | `tracker-sync` |
| `~/.config/coding_agent_standards/walkthrough.json` | Where walkthrough pages are written | `walkthrough` |
| `~/.config/coding_agent_standards/private-terms.txt` | Terms that must not reach a public repo | `private-terms.py` hook |
| `~/.config/coding_agent_standards/guardian-hooks/` | Hooks a guardian runs at start and stop | `guardian_hooks.py` |
| `codingstandards.visibility` | A checkout's visibility, for a repo the host cannot answer for | `private-terms.py` hook |
