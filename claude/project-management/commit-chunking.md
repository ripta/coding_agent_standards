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

List the oldest 50 unmerged commits:

```text
git log <mainline>..<integration> --reverse --format='%h %G? %ae %s' -n 50
```

Stop if there are no unmerged commits.

## Chunk Boundary Heuristics

1. **Primary**: map commits to the project's phases. Locate the phase documents
   as described in `plans.md`; they usually live in `spec/phases/`,
   `docs/phases/`, or `phases/`. One phase or milestone of work is one chunk.

2. **Secondary**: infer boundaries from commit messages, file paths, and
   thematic similarity. Use this when commits don't map cleanly to a phase. A
   project with no phase documents relies on this heuristic alone.

3. **Ambiguous commits** that could belong to either of two adjacent chunks:
   - Prerequisite work goes with the chunk that needs it.
   - Cleanup goes with the chunk it cleans up.
   - If genuinely unclear, ask the user with surrounding context.

## Constraints

- Chronological order only. Never reorder, combine, or split commits.
- If a chunk seems unusually large or small, ask the user.

## Output Format

For each chunk, output:

1. **Title**: the phase number, if there is one, plus a short name suitable as a
   PR title.
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
  remain.
- Dropping the last chunk can leave nothing, which happens when the window holds
  a single chunk. Output that chunk anyway. Mark it as possibly truncated by the
  50-commit window so the user knows it may not be complete.

## Statefulness

This process is stateless. It always diffs `<integration>` against
`<mainline>`, so already-merged commits disappear on their own.

## Scope

Output only. This does not create branches or PRs, and does not modify the
repository.

## Example

One chunk, with a paragraph description. A few bullet points work equally well.

### Phase 5: Streams

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
