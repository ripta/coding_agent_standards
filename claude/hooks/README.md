# Hooks

`hooks.json` is loaded by the `coding-standards` plugin. It wires six events:

- `SessionStart` runs `link-current.sh`. It points
  `~/.claude/coding-standards-current` at the installed plugin, so profiles
  import the standards from the same commit as the tools. It skips
  `--plugin-dir` sessions, which would otherwise link a working tree. A
  session that resumes or compacts on an older snapshot links the one
  `installed_plugins.json` lists instead of its own. It also
  runs `revisit-notice.sh`, which prints one line when a revisit hook in the
  project's proposals has passed, and nothing otherwise. Last, `check-setup.sh`
  creates `~/.local/state/coding_agent_standards/`, and checks that the
  machine and the project are set up. It prints nothing when they are. In a
  project it runs `standards_imports.py check`. Four warnings name imports
  that load nothing, or load only by accident, and give the fix
  `/update-profile`. An old `profiles/`, `languages/`, `practices/`,
  `project-management/`, or `knowledge/` path loads nothing once the checkout
  is current, because the directory moved under `claude/`. An old `claude/...`
  path, or one no mapping covers, reads the checkout's working tree and not the
  installed plugin. A path missing from the plugin snapshot, or with no `@`,
  loads nothing. A fifth warning names a project that imports the standards
  but has not approved external imports. Its fix is to accept the prompt in an
  interactive session, and `/update-profile` cannot do it. The check also names
  hook commands in `.claude/settings.json` and `settings.local.json` that run
  the checkout, and gives the link path to use. A `--plugin-dir` session also
  gets a check of the link, and a one-line notice when the project's imports
  read the installed snapshot while the tools come from the working tree.
  `guardian-session-start.sh` tells a `<domain name>_guardian` session that
  comes back by resume, `/clear`, or fork to re-run its Starting steps.
  `standards-on-demand.py` forgets which docs it named once the session
  compacts or clears. See `PreToolUse` below.
- `UserPromptSubmit` runs `name-guardian.sh`. When the prompt is `/guardian`
  with a domain name as its first argument, it names the session
  `<domain name>_guardian`, replacing any custom title.
- `SessionEnd` runs `guardian-session-end.sh`. When the session was a
  guardian that ran its start hooks, it runs that guardian's stop hooks,
  detached. See "Hooks" in `project-management/guardian.md`.
- `PreToolUse` on `Bash` runs `block-broad-find.sh`, `block-rm-rf.sh`, and `block-private-terms.sh`. See "Private Terms"
  below. `block-rm-rf.sh` denies an `rm` that has both a recursive and a force flag, in any spelling. It sees inside
  `sh -c`, `eval`, subshells, and command substitutions. Text that only mentions the command passes: a quoted string, a
  comment, or a heredoc body that no shell reads. `rm-rf.py` does the work. Its reason checks each operand on disk. It
  suggests `unlink` for a file or symlink and `rmdir` for an empty directory. A non-empty directory must be emptied
  first, or deleted by the user. It catches accidents and is no sandbox. It does not follow `ssh`, `su -c`, or
  variables.
- `PreToolUse` on the file tools runs `standards-on-demand.py`. Profiles leave the project-management docs and
  `practices/makefile.md` out of startup context. The first time a session reads or changes a proposal, an ADR, the
  queue, or a Makefile, the hook names the docs to read. It matches a file's resolved path too, so a symlinked `spec/`
  directory counts. It never blocks a call.
- `PostToolUse` on `Edit|Write` runs `format-edited-file.sh`. It runs `make fmt-select FILES=<path>` on the edited
  file, in the repo that holds it, when that repo has the target. See "Formatting Edited Files" in
  `practices/makefile.md`.
- `Stop` reminds you to run `make test` and `make lint` when those targets exist.

It also loads one hooks module, `work-queue-progress.tsx`, under `modules`. It
draws a `/work-queue` run's progress in a band above the prompt. `/queue` opens
the full queue in a pane, and `/queue clear` hides the band. The coordinator
reports each change through the `work_queue_status` tool it registers. The
mod also counts each subagent's tool calls on its own. It stays out of sight
until a run reports. Check it with `claude plugin validate claude` and
`claude plugin test claude`.

`block-redirection.sh` and `cg-check.sh` ship here too. They are not wired into
`hooks.json`. Reference them from a project's own settings when you want them.

## Opt-In Hooks

These are not wired into `hooks.json` either. Each one suits only some
projects. Wire one from the project's `.claude/settings.json` by absolute path,
since `${CLAUDE_PLUGIN_ROOT}` is not set there. The examples go through the plugin link,
`~/.claude/coding-standards-current`, so a hook runs the installed commit and not the
checkout's working tree.

- `block-pm-references.sh` denies an Edit or Write to a source file whose new
  text names a proposal, ADR, or bug ID, or a phase or milestone number. It
  enforces the rule in `rules/work-discipline.md`. Markdown, `spec/`, and
  `.claude/` are exempt. Pass the project's proposal prefixes as arguments.
- `audit-pm-refs.sh` is the same check on Stop, over every tracked file. It
  also catches text that arrived through Bash. It greps the whole tree, so clean
  up existing references before wiring it, or every stop fails. Both hooks take
  their pattern from `lib-pm-refs.sh`.
- `protect-golden-files.sh` denies hand-writing a `.golden` file, through Edit,
  Write, or Bash. Goldens must come from the project's update target.
- `block-zig-cache.sh` denies running a binary from `.zig-cache/` and deleting
  the cache. `settings/zig-dev.json` already wires it.
- `block-config-access.py` denies Read, Edit, Write, MultiEdit, NotebookEdit, Grep, and Glob any path under
  `~/.config` except `~/.config/coding_agent_standards`. It resolves `~`, `..`, and symlinks first. It also denies a
  Grep or Glob rooted above `~/.config`. `scripts/setup_permissions.py` wires it into the user's settings, through
  `~/.claude/coding-standards-current`, when those settings deny all of `~/.config`.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/coding-standards-current/hooks/block-pm-references.sh MOSK"
          }
        ]
      },
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/coding-standards-current/hooks/protect-golden-files.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/coding-standards-current/hooks/audit-pm-refs.sh MOSK"
          }
        ]
      }
    ]
  }
}
```

## Private Terms

`block-private-terms.sh` denies a `git commit` that carries a private term into a repo whose
visibility is public or unknown. It backs up the promotion check in `rules/disclosure.md`.
`private-terms.py` does the work.

- Terms live in `~/.config/coding_agent_standards/private-terms.txt`, one per line. Blank lines
  and `#` comments are ignored. You maintain the file by hand. Sessions may write only the `*.json`
  preference files beside it, through the Write and Edit tools. Changing this list needs your
  approval.
- Without the file, the hook allows everything. Other users of this plugin see nothing.
- A term matches as a whole word, case-insensitively. The hook checks the added lines of the
  commit and the commit command's text, which holds the message. A commit by path or with `-a`
  is checked against the working tree, since that is what it commits.
- Visibility comes first from `git config codingstandards.visibility`, set to `private`,
  `protected`, or `public`. Otherwise it comes from the host through `gh repo view`. Only
  `public` and unknown repos are checked. A repo with no remote is unknown, so a private one
  declares itself once with `git config codingstandards.visibility private`. The setting is
  per-clone and never committed.
- Host lookups are cached in `~/.local/state/coding_agent_standards/term-guard/visibility.json`.
  A public result never expires. A private one expires after 24 hours, so a repo made public is
  caught within a day. A failed lookup counts as unknown and is not cached.

Commits made outside Claude Code can run the same check from git. In a repo's `.git/hooks/`,
or the directory `core.hooksPath` names:

```sh
# pre-commit
exec python3 "$HOME/.claude/coding-standards-current/hooks/private-terms.py" pre-commit

# commit-msg
exec python3 "$HOME/.claude/coding-standards-current/hooks/private-terms.py" commit-msg "$1"
```

If the list blocks more than it protects, remove the hook from `hooks.json`.

### Alternatives Not Taken

One machine-wide list came first. These were weighed and deferred, to pick up if it proves
insufficient:

- Per-repo term files kept in each private repo, found through paths listed in the machine-wide
  file. They would let a repo's terms travel with it.
- A guard on `SendMessage`, blocking terms in messages to sessions with a less private domain.
  It guards the wrong boundary. A guardian needs a request's private evidence to verify it, and
  nothing is disclosed until a commit. It would also first need a check that a `PreToolUse`
  matcher fires on `SendMessage`.
- Recording each entry's visibility in the `domain.json` that the guardian start hooks save beside
  the ledger. The commit-time guard reads the repo's own visibility instead, so it needs none.

## Tests

Each `test_<hook>.py` feeds commands to one shell hook and checks its
decision. `hooktest.py` holds the shared runner. Run them with
`uv run --with pytest pytest claude/hooks`.

## Parked Configs Do Not Belong in hooks.json

Claude Code refuses to load a plugin whose `hooks.json` has a matcher-shaped
object anywhere outside the `hooks` object. The loader scans every other
top-level key three levels deep. Any object with a non-empty `hooks` array trips
it. The error names `PreToolUse/PermissionRequest` no matter which key caused it.

A leading underscore does not exempt the key. Neither does a `_note` field. Keep
disabled configs in this file as fenced code, not in `hooks.json`.

## Disabled: make lint on git commit

This ran `make lint` before every `git commit`. It is off because it blocks
commits in projects with no Makefile or no `lint` target.

To re-enable, add this to `hooks.PreToolUse` in `hooks.json`:

```json
{
  "matcher": "Bash(git commit*)",
  "hooks": [
    {
      "type": "command",
      "command": "make lint"
    }
  ]
}
```
