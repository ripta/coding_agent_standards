# The format hook reformats the session's repo, not the edited file's

**Status:** fixed

**Component:** this repo's plugin. The `PostToolUse` hook on `Edit|Write` in `claude/hooks/hooks.json`, added in
b938b61.

**Reproduces on:** Claude Code 2.1.310, plugin from this repo at 9b877ae.

## Observed behavior

The hook runs `if make -n fmt >/dev/null 2>&1; then make fmt; fi`. It ignores which file the tool wrote. It runs
`make fmt` in the session's working directory, so four things go wrong:

1. An edit outside the working directory's repo still formats that repo. Here, `spec/` is an untracked symlink into
   another checkout. Editing a file under it ran `make fmt` in `coding_agent_standards`, which the edit never touched.
2. `make fmt` here is `rumdl/lint-markdown --all --fix`, which rewrites the whole tree. One edit to one file reformatted
   6 unrelated tracked files: `README.md`, `claude/commands/guardian.md`, `claude/knowledge/wiki.md`,
   `claude/project-management/design.md`, `claude/skills/conversation-handoff/SKILL.md`, and
   `claude/skills/rca/SKILL.md`. The session did not write them, so their diff mixes into its work, or into another
   session's work in the same checkout. The model is told they "changed on disk", and treats the change as deliberate.
3. The rewrites are not all safe. Its rewrap of `claude/commands/guardian.md` joined two lines without a space,
   leaving "Commits follow`${CLAUDE_PLUGIN_ROOT}/...`". It also edits text inside fenced example blocks, which are
   templates that show an exact format. It narrowed a tree drawing in `claude/skills/rca/SKILL.md` from `│  └─` to
   `│ └─`. It added blank lines and angle brackets inside the templates in `design.md`, `conversation-handoff/SKILL.md`,
   and `knowledge/wiki.md`. All 6 files were reverted.
4. `rumdl check` exits 1 whenever a finding it cannot fix remains. Two exist now, MD033 in
   `claude/commands/work-on.md:3` and `claude/commands/work-queue.md:3`. So every `Edit` or `Write` reports this to the
   model:

   ```text
   PostToolUse:Edit hook blocking error from command: "if make -n fmt >/dev/null 2>&1; then make fmt; fi":
   [if make -n fmt >/dev/null 2>&1; then make fmt; fi]: make: *** [fmt] Error 1
   ```

## First seen

On 2026-10-27, in a session in `coding_agent_standards` that edited a script through the `spec` symlink. The working
tree was clean except for `spec` before that edit, and held the 6 reformatted files after it. The session wrote its
remaining files through Bash, to keep the hook from firing again.

## Repro

1. In a checkout of this repo with a clean tree, make sure some tracked markdown file has a finding that
   `rumdl check --fix` rewrites, such as a heading with no blank line after it.
2. Start a session there with the plugin installed. Use `Edit` on any file outside the repo, such as a file in the
   scratchpad.
3. Run `git status --short`.

**Still broken:** the markdown file from step 1 shows as modified, and the `Edit` reported `make: *** [fmt] Error 1`
while an unfixable finding exists.

**Fixed:** the tree stays clean. An edit inside a repo with a `fmt` target formats in that repo only, and a failing
format step does not report a blocking error.

## Fix

`claude/hooks/format-edited-file.sh` replaces the inline command. It resolves the edited file's directory with
`pwd -P`, finds that repo's root, and runs `make fmt-select FILES=<path>` there. It does nothing when the file is in no
repo, or the repo has no `fmt-select` target. It always exits 0, and shows a failed format to the agent as context.
`practices/makefile.md` "Formatting Edited Files" defines the target. `claude/hooks/test_format_edited_file.py` runs the
command `hooks.json` wires against each case above.

This repo defines no `fmt-select`, so the hook leaves its markdown alone. rumdl's fix mode is not safe to run
unattended here yet. See `20261027-rumdl-fix-rewrites-unflagged-text.md`.

A session keeps running the hook from its installed plugin. Until the plugin updates, writing through Bash instead of
`Edit` or `Write` avoids the old hook.
