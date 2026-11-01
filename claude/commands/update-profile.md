---
description: Add or replace a project's coding-standards profile import, and fix imports of the old checkout paths
argument-hint: "<profile> [<profile> ...]"
---

Update this project's coding-standards imports for the profiles in `$ARGUMENTS`. A script makes every edit. This
command only asks the user and relays the result.

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/update_profile.py plan $ARGUMENTS`. When it exits 1, show its stderr to
   the user and stop. It refuses on an unknown profile. It also refuses when the
   `~/.claude/coding-standards-current` link is missing or dangling, or its plugin has no `profiles/`.

2. Show the user the plan: the target file, the existing profile imports, each old or plain-text path, and the edits of
   each variant. List the skipped imports with their reasons. List the prose lines it flagged, since the user may want
   to trim them by hand. Print any `notes` as they are.

3. Ask the questions the plan's `questions` object marks true, in one AskUserQuestion call. Skip a question the plan
   already answers, and skip the call when none is marked.

   - `target`: which file receives the import. Offer `target_candidates` and `default_target`, with the default first.
   - `mode`: replace the `different_profile_imports` with the requested profiles, or keep both.
   - `per_file`: collapse the per-file imports the profile already includes, or keep them all. Collapse is the
     recommended answer.

4. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/update_profile.py apply $ARGUMENTS` with `--target`, `--mode`, and
   `--per-file` set from the answers. Pass only the flags the user answered.

5. When `apply` exits 3, it wrote nothing. Its `unwritable` list names the files it could not write. Tell the user, and
   run the same `apply` again with the sandbox disabled, so the user approves the write at the permission prompt.

6. Report the files written, the edits, the skipped imports, the flagged prose lines, and the `notes`. Report
   `external_imports`. When `approved` is false, tell the user to start an interactive session in the project and
   accept the external imports prompt. Only the user can approve it. When it is null, say the approval is unknown.

Never commit. Never edit a settings file, and never grant external-import approval.
