# Hooks

`hooks.json` is loaded by the `coding-standards` plugin. It wires six events:

- `SessionStart` runs `link-current.sh`. It points
  `~/.claude/coding-standards-current` at the installed plugin, so profiles
  import the standards from the same commit as the tools. It skips
  `--plugin-dir` sessions, which would otherwise link a working tree. It also
  runs `revisit-notice.sh`, which prints one line when a revisit hook in the
  project's proposals has passed, and nothing otherwise. Last, `check-setup.sh`
  creates `~/.local/state/coding_agent_standards/`, and checks that the
  machine and the project are set up. It prints nothing when they are.
  `guardian-session-start.sh` tells a `<domain name>_guardian` session that
  comes back by resume, `/clear`, or fork to re-run its Starting steps.
- `UserPromptSubmit` runs `name-guardian.sh`. When the prompt is `/guardian`
  with a domain name as its first argument, it names the session
  `<domain name>_guardian`, replacing any custom title.
- `SessionEnd` runs `guardian-session-end.sh`. When the session was a
  guardian that ran its start hooks, it runs that guardian's stop hooks,
  detached. See "Hooks" in `project-management/guardian.md`.
- `PreToolUse` on `Bash` runs `block-broad-find.sh` and `block-private-terms.sh`. See "Private Terms" below.
- `PostToolUse` on `Edit|Write` runs `make fmt` when the target exists.
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
since `${CLAUDE_PLUGIN_ROOT}` is not set there. The examples assume the repo
lives at `~/projects/coding_agent_standards`.

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
- `block-rm-rf.sh` denies an `rm` that has both a recursive and a force flag,
  in any spelling. Its reason checks each operand on disk. It suggests `unlink`
  for a file or symlink and `rmdir` for an empty directory. A non-empty
  directory must be emptied first, or deleted by the user. Wire it on `Bash`.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/projects/coding_agent_standards/claude/hooks/block-pm-references.sh MOSK"
          }
        ]
      },
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/projects/coding_agent_standards/claude/hooks/protect-golden-files.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/projects/coding_agent_standards/claude/hooks/audit-pm-refs.sh MOSK"
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
