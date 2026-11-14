# Commit Chunking

Rules for splitting unmerged commits on a long-running integration branch into
logical, PR-sized chunks for merging into the mainline branch.

This applies to projects that accumulate work on an integration branch and land
it in the mainline in reviewable batches. Trunk-based projects do not need it.

## Establishing the Branch Pair

Never assume branch names. Determine the pair before anything else:

1. Use the branch names the user gave, if they gave any.
2. Otherwise infer the mainline from the remote head:
   `git symbolic-ref refs/remotes/origin/HEAD`. Then look for a long-running
   branch that is ahead of it.
3. If the pair is still ambiguous, ask the user.

The rest of this document writes the pair as `<mainline>` and `<integration>`.

## Goal

Find the oldest unmerged commits on `<integration>` that should merge into
`<mainline>`. Output up to five chunks, then stop.

## Commit Discovery

Count the unmerged commits with `git rev-list --count <mainline>..<integration>`. Call it N. List the oldest 50:

```text
git log <mainline>..<integration> --reverse --skip=<N-50> --format='%h %G? %ae %s'
```

Use `--skip=0` when N is 50 or less. Do not use `-n 50`. Git applies the limit before `--reverse`, so it returns the
newest 50. `--skip` drops the newest N-50 instead.

Find the snip commits in the window, as "Snip Commits" in `rules/git-workflow.md` defines them. For each commit whose
subject starts with `8< --- snip ---`, run `git log -1 --format=%P <hash>` and
`git log -1 --format= --name-only <hash>`. It is a snip when the first prints one parent and the second prints nothing.
A merge, or a commit with such a subject and changes, is not a snip. It stays in the list. Flag it under "Flagging
Judgment Calls".

Stop if no commits other than snips remain.

## Chunk Boundary Heuristics

Snips come first. The user placed each one at the end of work that is ready to land. Every snip ends a chunk, and no
chunk spans a snip. The heuristics below only split the work between two snips into smaller chunks. They never join
work across a snip. A snip at the front of the window ends nothing, since the work it marked has already merged.
Skip it. A snip right after another snip ends nothing either. Treat a run of snips as one boundary.

1. **Primary**: map commits to the project's queue rows. Read `queue.md`,
   `history.md`, and the proposals they name, as described in `plans.md`.
   Merged work usually sits in `history.md`. These files usually live in
   `spec/proposals/` or `docs/proposals/`. Match each commit to a row by the
   milestone checks and As built blocks it fulfills. One queue row of work is
   one chunk.

2. **Secondary**: infer boundaries from commit messages, file paths, and
   thematic similarity. Use this when commits don't map cleanly to a row. A
   project with no queue relies on this heuristic alone.

3. **Ambiguous commits** that could belong to either of two adjacent chunks:
   - Prerequisite work goes with the chunk that needs it.
   - Cleanup goes with the chunk it cleans up.
   - If genuinely unclear, make the call and flag it. See "Flagging Judgment
     Calls" below.

## Constraints

- Chronological order only. Never reorder, combine, or split commits.
- Never put a snip commit in a chunk or its commit list. Snips never go into a PR.

## Flagging Judgment Calls

Never stop mid-analysis to ask. This process produces output, not changes, so a
wrong call costs the user one line of correction. Interrupting them five times
costs far more.

Work through all 50 commits, then surface every judgment call at once, after the
chunks. Keep it to one line each, naming the commit and the two chunks it sat
between, or the chunk whose size looks off. The user corrects what they care
about in a single reply.

## Output Format

For each chunk, output:

1. **Title**: the queue row's milestone range, if there is one, plus a short
   name suitable as a PR title.
2. **Description**: a short paragraph or a few bullet points suitable as a PR
   body. Follow the PR description rules in `rules/pr-style.md`, a sibling
   directory of this file.
3. **Commit list**: a code block using the git log format above
   (`%h %G? %ae %s`).

Output chunks in merge order, oldest first. Output at least one chunk and at
most five.

## Stopping Rules

Build up chunks one at a time from the 50-commit window:

- Stop and output when you have accumulated five complete chunks. All five are
  safe to include. The 5-chunk cap caused the stop, not the commit window.
- If you exhaust all 50 commits before reaching five chunks, drop the last
  chunk. The 50-commit window may have cut it short. Output the chunks that
  remain. A chunk that ends at a snip is complete, so never drop it. Drop the
  last chunk only when no snip ends it.
- Dropping the last chunk can leave nothing, which happens when the window holds
  a single chunk. Output that chunk anyway. Mark it as possibly truncated by the
  50-commit window so the user knows it may not be complete.

## Statefulness

This process is stateless. It always diffs `<integration>` against
`<mainline>`, so already-merged commits disappear on their own. Snips never
merge, so they stay until the user rebases. That is why a snip at the front of
the window is skipped.

## Scope

Output only. This does not create branches or PRs, and does not modify the
repository.

The `land-branch` skill reuses the boundary heuristics above to cut batches, and
then acts on its plan. It splits a range into independent streams first, and
the chronological constraint holds within each stream. This scope binds
`next-pr`, not that skill.

## Example

One chunk, with a paragraph description. A few bullet points work equally well.

### PROJ-005 M1-M3: Streams

Reading and writing external data needs a value type that survives across calls,
plus primitives to open, seek, and buffer it. This chunk adds the stream type
and the primitive set that operates on it.

```text
161c3d8 N author@example.com Implement stream-seeking primitives
f430001 N author@example.com Replace tempfile tests with fixtures
d67d75e N author@example.com Implement stream-read-* primitives
42b8132 N author@example.com Implement stream-write and stream-flush primitives
9f2cd2a N author@example.com Implement stream-open and stream-close native words
3d1b55b N author@example.com Add IO error types and organize error types in general
48fdcb5 N author@example.com Add stream value type
```
