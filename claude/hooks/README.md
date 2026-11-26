# Hooks

`hooks.json` is loaded by the `coding-standards` plugin. It wires six events:

- `SessionStart` runs `link-current.sh`. It points
  `~/.claude/coding-standards-current` at the installed plugin, so profiles
  import the standards from the same commit as the tools. It skips
  `--plugin-dir` sessions, which would otherwise link a working tree. A
  session that resumes or compacts on an older snapshot links the one
  `installed_plugins.json` lists instead of its own. It also
  runs `revisit-notice.sh`, which prints one line for each proposals directory
  whose revisit hook has passed, and nothing otherwise. It checks every
  `spec/proposals` and `docs/proposals` under the project root, so a monorepo's
  per-app proposals are covered. A `spec` or `docs` symlinked to a central specs
  directory counts, tracked or not. Each line names its directory. Last,
  `check-setup.sh`
  creates `~/.local/state/coding_agent_standards/`, and checks that the
  machine and the project are set up. It always prints the plugin root, since
  rules that run a plugin script get no `CLAUDE_PLUGIN_ROOT`. It prints
  nothing else when the setup is complete. In a
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
  The project check skips a checkout of this repo, including one that is a
  submodule or a linked worktree of a submodule.
  `guardian-session-start.sh` tells a `<domain name>_guardian` session that
  comes back by resume, `/clear`, or fork to re-run its Starting steps. It
  passes on the saved domain, so a complete one is reused without asking.
  `standards-on-demand.py` forgets which docs it named once the session
  compacts or clears. See `PreToolUse` below.
- `UserPromptSubmit` runs `name-guardian.sh`. When the prompt is `/guardian`
  with a domain name as its first argument, it names the session
  `<domain name>_guardian`, replacing any custom title.
- `SessionEnd` runs `guardian-session-end.sh`. When the session was a
  guardian that ran its start hooks, it runs that guardian's stop hooks,
  detached. See "Hooks" in `project-management/guardian.md`.
- `PreToolUse` on `Bash`, `cg_run`, and `cg_run_many` runs `block-broad-find.sh`, `block-rm-rf.sh`,
  `block-gcloud-project-number.sh`, and `block-private-terms.sh`. `rules/shell-discipline.md` sends agents through the
  cg tools, so a guard that read only `Bash` would miss most of what an agent runs. A cg call carries an argv list, or
  a list of them, in place of a shell string. A shell wrapper such as `["bash", "-c", "rm -rf x"]` is read like the
  same command in `Bash`. Each guard denies through the same `hookSpecificOutput` for all three tools.
- `block-broad-find.sh` denies a `find` on `/`, the directory that holds the home directory, the home directory, or
  `~/projects`. A directory below those passes.
- `block-rm-rf.sh` denies an `rm` that has both a recursive and a force flag, in any spelling. It sees inside
  `sh -c`, `eval`, subshells, and command substitutions. It reads a shell's script past the shell's options, as in
  `bash -O extglob -c '...'`. Text that only mentions the command passes: a quoted string, a comment, or a heredoc body
  that no shell reads. `rm-rf.py` does the work. Its reason checks each operand on disk, from the cg call's `cwd` when
  it has one, and from both directories when a cg call has none. See `toolcalls.py` below. It suggests `unlink` for a
  file or symlink and `rmdir` for an empty directory. A non-empty directory must be emptied first, or deleted by the
  user. It catches accidents and is no sandbox. It does not follow `ssh`, `su -c`, or variables. A quoted `rm` after a
  wrapper word, as in `sudo 'rm' -rf x`, is read as text, since a quoted word runs only in command position.
  The shell wrapper has no prefilter on the command text. The scanner joins quoted pieces, so `r''m -rf x` is an `rm`,
  and no glob over the raw payload lets it by safely. Python starts for every call, at about 35 ms. A call the hook
  cannot read is denied when its text may spell `rm`. An error never exits 1, because an exit of 1 does not block.
- `block-gcloud-project-number.sh` denies a `gcloud` call that names its project by number, in `--project`,
  `gcloud config set project`, or `CLOUDSDK_CORE_PROJECT`. Its reason gives the `gcloud projects describe` command that
  resolves the number to an ID. See `practices/gcloud.md`. `block-private-terms.sh` is covered under "Private Terms"
  below.
- `toolcalls.py` is the one place that turns a `Bash`, `cg_run`, or `cg_run_many` payload into shell text and a
  starting directory. `rm-rf.py` and `private-terms.py` import it. A cg argv is joined with shell quoting. The
  payload's `cwd` follows the Bash tool's persisted `cd`. The cg server keeps the directory it started in, which is
  normally `$CLAUDE_PROJECT_DIR`. A cg call with no `cwd`, or a relative one, runs from the server's directory, so both
  guards read it from both. Each command appears once for each directory that differs. An absolute `cwd` needs neither.
  A `GIT_` variable in a cg call's `env` leads the text as an inline assignment, since `GIT_DIR` and `GIT_INDEX_FILE`
  move a commit. NUL bytes are dropped, as bash drops them from a script. A payload in the wrong shape, such as a
  non-string `command`, raises an error. Each guard turns that error into a denial when the call mentions its command.
  The module also holds the shell-option parsing the guards share. It finds the script after `-c` past options such as
  `-O extglob`, `+o pipefail`, and `--rcfile f`. The two shell guards without a Python half, `block-broad-find.sh` and
  `block-gcloud-project-number.sh`, join the argv with `jq`, since a regex over the words needs no quoting.
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
reports each change through the `work_queue_status` tool it registers.

The mod also counts each subagent's tool calls on its own. It stays out of sight
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
  also catches text that arrived through Bash. It greps the whole tree and every
  checked-out submodule, so clean up existing references before wiring it, or
  every stop fails. It exempts `spec/` and `.claude/` at any depth, as the Edit
  and Write hook does. Both hooks take their pattern from `lib-pm-refs.sh`.
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
`private-terms.py` does the work. It reads the `Bash` tool and the `cg_run` and `cg_run_many` tools,
through `toolcalls.py`. A cg call's argv becomes one shell string, so `["bash", "-c", "cd x && git commit"]`
reads like the same command in `Bash`.

- Terms live in `~/.config/coding_agent_standards/private-terms.txt`, one per line. Blank lines
  and `#` comments are ignored. You maintain the file by hand. Sessions may write only the `*.json`
  preference files beside it, through the Write and Edit tools. Changing this list needs your
  approval.
- Without the file, the hook allows everything. Other users of this plugin see nothing.
- A term matches as a whole word, case-insensitively. The hook checks the added lines of the
  commit, the paths it changes, and the commit command's text, which holds an inline message. A path
  counts on both sides of a rename and when it is deleted. A commit by path or with `-a` is checked
  against the working tree, since that is what it commits. In a repo with no commit yet, the tree
  is compared with the empty tree.
- The hook reads a commit's options as git does. A long option may be a prefix that fits one option, a
  short one may sit in a cluster, and a value may be the next word or part of the word. `-p` and
  `--patch` commit working-tree hunks that nothing staged, so the hook reads the whole working-tree
  diff. `--interactive` may add any file, so it also reads the untracked files that the ignore rules
  leave in view, and denies one too large to read. An option the hook does not know gets the same
  full read, since it may take anything. A prefix that fits two options is no option in git, so it
  gets the full read as well.
- The text of a message file is checked too. `-F`, `--file`, `-t`, and `--template` name a file, read
  from the directory the commit runs in, and it may lie outside the repo. The operand must be a
  literal path to a regular file that exists when the command is checked. Standard input, as in
  `-F -` or `-F /dev/stdin`, reads no file, and its text is in the command. Anything else is denied in a public or
  unknown repo, and the reason says to write the message in an earlier command.
- `GIT_INDEX_FILE` names another index, as an inline assignment, an `export`, `env`, or the `env`
  of a cg call. The hook diffs against that index when the path is literal and the file exists. A
  relative path is read from the top of the work tree, as git reads it. Any other value is denied
  in a public or unknown repo.
- The hook checks the repo the commit goes to, not the repo of the working directory. Each `cd` before
  the commit moves the directory, relative to the one before it, with `~` expanded. `git -C` then
  applies from there. `GIT_DIR` and `GIT_WORK_TREE` name the repo too, as an inline assignment, an
  `export`, a `--git-dir` or `--work-tree` flag, or the `env` of a cg call. `env -C`, `env --chdir`,
  `sudo -D`, and `sudo --chdir` change the directory for the command they run. `env -u` and `env -i`
  clear the variables, and `env -S` runs its string as a command. A `cd`, an `export`, or a
  `GIT_` variable inside a subshell, a `$(...)`, a pair of backticks, or a pipeline does not carry past
  it. A command with several `git commit`s is checked once for each. Pathspecs, as in
  `git commit -- f.txt`, are read from that directory and not from the repo's top. The body of a
  heredoc is text, unless the command that reads it is a shell.
- A commit the hook cannot place is denied. The reason says to rerun it as `git -C <path> commit ...`
  with the repo's literal path. The hook cannot place a commit when:
  - a `cd`, `pushd`, `popd`, or `git -C` takes `"$X"`, `-`, a glob, or any word the shell must expand
  - a `cd` goes to a directory that does not exist, and a `||`, a `;`, or a newline follows it, since
    the commit may run there or here. The same holds after an `&&` chain that began with such a `cd`
  - `GIT_DIR`, `GIT_WORK_TREE`, `--git-dir`, or `--work-tree` takes a word the shell must expand
  - `env -C`, `env --chdir`, `sudo -D`, or `sudo --chdir` takes a word the shell must expand
  - the command word is a variable or a substitution that is followed by the word `commit`, as in
    `G=git; $G commit` and `$(which git) commit`
- A `cd` to a directory that does not exist, followed by `&&`, may be preceded by a step that makes
  it, as in `mkdir x && cd x && git commit`. The commands in that chain are checked against the repo
  of the nearest directory that exists. That check is harmless when the `cd` fails and no commit runs.
- `--pathspec-from-file` is read when its operand is a literal path to a file inside the repo, with
  plain entries. Stdin, an expansion, a missing file, a file outside the repo, and a quoted entry are
  denied, and the reason says to name the paths on the command line.
- These denials apply only when the term file exists, and only to a command that has a commit in it.
  A commit the hook cannot place is denied whatever any repo's visibility, since the hook cannot tell
  which repo it is. A pathspec file, a message file, or an index it cannot read is denied only in a
  public or unknown repo.
- A call the hook cannot read is denied when the user keeps terms and the call may spell a commit. That
  covers a `command` that is not a string, a payload that is not an object, and an error inside the hook.
  The check reads the raw payload through quotes and backslashes, so `com''mit` counts. A call that does
  not mention a commit passes. The hook never exits 1, because an exit of 1 does not block the call.
- NUL bytes are dropped from the command and the paths, as bash drops them from a script.
- The hook cannot see a commit that no word in the command spells. A git alias such as `git ci`,
  `make commit`, and a script that commits inside are invisible to it, and so is a directory that an
  earlier step of the same command creates. The git hooks below catch what these commit, once
  installed, since git runs them whatever the command was, and the pre-commit hook reads the index
  the commit uses. A git hook can be skipped with `--no-verify`, and each repo must install them.
- The hook does not read a message that comes from somewhere other than the command and a file.
  That covers `-C`, `-c`, `--fixup`, and `--squash`, which reuse a commit's message, a message that
  a command substitution builds, and one typed in an editor. It does not read `GIT_` variables
  other than `GIT_DIR`, `GIT_WORK_TREE`, and `GIT_INDEX_FILE`, nor `git -c core.worktree=...`. The
  git hooks catch these too. A command substitution inside an unquoted heredoc body is read as text.
- The hook runs git in a directory the command names, outside the sandbox, so every git call turns
  off what the repo can configure. It passes `core.fsmonitor=false` and `--no-pager`. The diffs get
  `--no-textconv`, `--no-ext-diff`, and `--ignore-submodules=all`. Each filter driver in the repo's
  config, from any file it includes, gets an empty `clean` and `process` and `required=false`, as
  `git -c` arguments, which every git version reads. A driver whose name holds `=` cannot be spelled
  that way. The hook then denies every commit to that repo, and the reason names the driver. Git that
  cannot be run is denied the same way. `core.hooksPath` is left alone. `git diff`
  runs no hook. `safe.directory` is left as the user set it, so git refuses a repo that another
  user owns, as the commit itself will. The system config is not ignored: it is not the repo's, and
  the visibility lookup may read it. Git's output is decoded with replacement, since a file in
  another encoding would otherwise raise and let the commit through.
- The shell wrapper has no prefilter on the command text. The tokenizer joins quoted pieces and drops
  backslashes, so `g''it com\mit` is a commit, and no glob over the raw payload lets it by safely.
  Python starts for every `Bash` and cg call when the term file exists. That takes about 35 ms, where
  a glob would take about 5 ms. A user with no term file pays only the shell.
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
- Reading each entry's visibility from the `domain.json` that the guardian start hooks save beside
  the ledger. The file records it so a restarted guardian can reuse it, but the commit-time guard
  reads the repo's own visibility instead.

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
