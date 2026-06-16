---
name: release
description: |
  Use this skill to cut a tagged git release. Auto-detects the project's tagging
  scheme — month-based (vYYYY.M.N, where N is the Nth tag that month) or semver
  (vX.Y.Z) — proposes the next tag (recommending a patch/minor/major bump for
  semver), drafts release notes from the commit delta, and creates an annotated
  tag after you approve. It stops after creating the tag locally; it does not push.
allowed-tools: Bash, Read, Glob, Grep
---

You create tagged git releases. You gather facts with the bundled script, reason
about the next tag and release notes, and create the tag only after explicit
approval. You never push the tag or run any publishing tooling.

## Workflow

1. Run the bundled `release-info.sh` located in this skill's own directory (the
   same directory as this SKILL.md). If it exits non-zero, report the error
   verbatim and stop.

2. Parse the output. Sections are line-oriented: a `@@NAME` marker line followed
   by its value line(s), ending at `@@END`. Always-present sections: `TODAY`,
   `COMMIT_COUNT`, `GIT_LOG`.

3. Determine the scheme and next tag:

   - **`@@NO_TAGS true`** — no tags exist. Ask the user which scheme to start:
     month-based (first tag `v{YEAR}.{MONTH}.1`) or semver (first tag `v0.1.0`,
     or `v1.0.0` if they consider it production-ready). Use `@@YEAR`/`@@MONTH`
     for the month-based default.

   - **`@@SCHEME month`** — `@@NEXT_TAG` is already computed (next serial for the
     current month, padding matched to existing tags). Use it as-is.

   - **`@@SCHEME semver`** — recommend a bump by reading `@@GIT_LOG` against
     semver philosophy, then map to the candidate:
     - **major** (`@@NEXT_MAJOR`): backward-incompatible changes — removed or
       changed public API/CLI/config, breaking behavior, or any commit marked
       `BREAKING CHANGE` or a conventional-commit `type!:`.
     - **minor** (`@@NEXT_MINOR`): new backward-compatible functionality —
       `feat:` commits or added capabilities.
     - **patch** (`@@NEXT_PATCH`): bug fixes, docs, refactors, dependency bumps,
       and other changes with no API surface impact.
     State your recommendation with a one-line justification, and list the other
     candidates so the user can override.

4. **Confirm the scheme.** Since the scheme is auto-detected, tell the user which
   scheme was detected (and, for semver, your recommended bump) before drafting
   notes. Let them correct it.

5. Draft release notes from `@@GIT_LOG`:
   - First line: `YYYY-MM-DD:` (from `@@TODAY`).
   - Blank line, then `- ` bullets for distinct changes.
   - Collapse related commits into single bullets.
   - Skip merge commits (subjects starting with "Merge pull request" / "Merge branch").
   - Collapse dependency bumps into one "Regular deps upgrades" bullet, unless
     they are the only changes.
   - Match the tone of existing tags: terse, no markdown beyond dashes, casual
     voice. To check tone, inspect a recent tag's message with
     `git tag -l -n99 <latest_tag>` (latest tag is in `@@LATEST_TAG`).

6. **Checkpoint — approval required.** Present the proposed tag name and the
   release notes. Wait for approval or edits. Do not create the tag until the
   user confirms.

7. After approval, create the annotated tag:
   ```
   git tag -a <tag> -m "$(cat <<'EOF'
   <release notes>
   EOF
   )"
   ```

8. Confirm the tag was created locally and stop. Remind the user it has not been
   pushed, and that they can push it with `git push origin <tag>` when ready.

## Rules

- Never push tags or run release/publish tooling — tag creation is the last step.
- Never create a tag before the user approves the name and notes.
- If the script reports a dirty tree or no commits since the last tag, relay that
  and stop; do not work around it.
- The user's bump choice always overrides your semver recommendation.
