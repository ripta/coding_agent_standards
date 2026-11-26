---
name: release
description: |
  Use this skill to cut a tagged git release. Auto-detects the project's tagging
  scheme—month-based (vYYYY.M.N, where N is the Nth tag that month) or semver
  (vX.Y.Z)—proposes the next tag (recommending a patch/minor/major bump for
  semver), drafts release notes from the commit delta, and creates an annotated
  tag after you approve. In a monorepo that tags each app on its own
  (`apps/api/v1.2.0`), it asks which component to release. It stops after
  creating the tag locally; it does not push.
model: sonnet
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

You create tagged git releases. You gather facts with the bundled script, reason
about the next tag and release notes, and create the tag only after explicit
approval. You never push the tag or run any publishing tooling.

## Tag Names

A repo is released as a whole or one component at a time.

- **Whole repo**: tags have no prefix, such as `v1.2.3` or `v2026.6.5`.
- **Component**: tags carry the component's path from the repo root as a prefix,
  the Go module convention. The component `apps/api` is tagged `apps/api/v1.2.0`
  or `apps/api/v2026.6.5`. The prefix is always the path. It is never a separate
  name, so the path alone says which component a tag belongs to.

Each component has its own scheme, version, and commit history. A tag of one
component never counts toward another's, and never counts toward the whole repo.

## Workflow

1. Pick the scope. Run the bundled `release-info.sh` located in this skill's own
   directory (the same directory as this SKILL.md) with `--list-components`.
   It works in a dirty tree. If it exits non-zero, report the error verbatim and
   stop.

   The `@@COMPONENTS` section lists the component prefixes found among the tags
   reachable from `HEAD`, one per line.

   - **Empty**: the repo tags as a whole. Release the whole repo.
   - **Not empty**: the repo tags per component. If the user already named a
     component, use it. Otherwise ask which to release with AskUserQuestion.
     Offer the components, plus the whole repo as the last option. The tool takes
     at most four options. With more than three components, list them all in the
     question, offer the first three, and say the user can name another under
     Other. A component with no tags yet is not listed, so the user names its
     path under Other. Paths are relative to the repo root, whatever directory
     you are in.

2. Run `release-info.sh` again for the release itself. Add `--component <path>`
   when a component was chosen, and no option for the whole repo. If it exits
   non-zero, report the error verbatim and stop. With `--component`, the dirty
   check, the commit count, and the log cover that path only.

3. Parse the output. Sections are line-oriented: a `@@NAME` marker line followed
   by its value line(s), ending at `@@END`. Always-present sections: `TODAY`,
   `COMMIT_COUNT`, `COMPONENTS`, `GIT_LOG`. `COMPONENT` is present when a
   component was chosen.

   Every tag in the output already carries the component prefix. Use
   `@@LATEST_TAG`, `@@NEXT_TAG`, and `@@NEXT_*` as given.

4. Determine the scheme and next tag:

   - **`@@NO_TAGS true`**: no tags exist for this scope, so there is nothing to
     detect. Pick a starting scheme and carry it forward: month-based (first tag
     `v{YEAR}.{MONTH}.1`, using `@@YEAR`/`@@MONTH`) or semver (first tag
     `v0.1.0`, or `v1.0.0` for production-ready). For a component, put the
     component and a slash in front: `apps/api/v0.1.0`. Do not stop to ask. The
     choice goes to the user in step 7 alongside the notes, with the alternative
     named.

   - **`@@SCHEME month`**: `@@NEXT_TAG` is already computed (next serial for the
     current month, padding matched to existing tags). Use it as-is.

   - **`@@SCHEME semver`**: recommend a bump by reading `@@GIT_LOG` against
     semver philosophy, then map to the candidate:
     - **major** (`@@NEXT_MAJOR`): backward-incompatible changes, such as
       removed or changed public API/CLI/config, breaking behavior, or any
       commit marked `BREAKING CHANGE` or a conventional-commit `type!:`.
     - **minor** (`@@NEXT_MINOR`): new backward-compatible functionality, such
       as `feat:` commits or added capabilities.
     - **patch** (`@@NEXT_PATCH`): bug fixes, docs, refactors, dependency bumps,
       and other changes with no API surface impact.
     State your recommendation with a one-line justification, and list the other
     candidates so the user can override.

5. Do not stop here to confirm the scheme. Nothing about drafting the notes
   depends on the tag name, so a separate confirmation buys nothing and costs
   the user a round trip. Carry the scheme into step 7 instead.

6. Draft release notes from `@@GIT_LOG`:
   - First line: `YYYY-MM-DD:` (from `@@TODAY`).
   - Blank line, then `-` bullets for distinct changes.
   - Collapse related commits into single bullets.
   - Skip merge commits (subjects starting with "Merge pull request" / "Merge branch").
   - Collapse dependency bumps into one "Regular deps upgrades" bullet, unless
     they are the only changes.
   - Match the tone of existing tags: terse, no markdown beyond dashes, casual
     voice. To check tone, inspect a recent tag's message with
     `git tag -l -n99 <latest_tag>` (latest tag is in `@@LATEST_TAG`).

7. **Checkpoint: approval required.** This is the skill's only interruption
   after the scope question. Present all of it together:
   - The component, when there is one.
   - The scheme, and how it was determined: detected from existing tags, or
     chosen because no tags exist.
   - The proposed tag name, plus the other candidates for semver.
   - The drafted release notes.

   Wait for approval or edits. Do not create the tag until the user confirms.

8. After approval, create the annotated tag. The name is the full tag, prefix
   included, such as `apps/api/v1.3.0`.

   ```text
   git tag -a <tag> -m "$(cat <<'EOF'
   <release notes>
   EOF
   )"
   ```

9. Confirm the tag was created locally and stop. Remind the user it has not been
   pushed, and that they can push it with `git push origin <tag>` when ready.

## Rules

- Never push tags or run release/publish tooling. Tag creation is the last step.
- Never create a tag before the user approves the name and notes.
- Step 7 is the only checkpoint for the tag. Scheme, tag, and notes are approved
  together in one pass, not in separate rounds. Choosing the component in step 1
  is a separate question, asked only when the repo tags per component and the
  user has not named one.
- If the script reports a dirty tree or no commits since the last tag, relay that
  and stop; do not work around it.
- A component tag always starts with the component's path and a slash. Never
  invent a shorter name for it.
- The user's bump choice always overrides your semver recommendation.
