---
name: test-audit
description: |
  Audit a scope of tests for value against cost. Finds low-value proofs, groups them into coherent batches that keep one owner per contract, asks which batches to apply, applies them, and reports cost before and after. Invoked as `/test-audit <path or package>`.
argument-hint: "<path or package>"
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Grep, Edit, Write, AskUserQuestion
---

# Test audit

An audit weighs coverage against cost. Coverage means testing every permutation of state or input. Cost means suite
runtime and the upkeep of more tests. The audit removes low-value proofs as coherent batches. It never chases a
deletion count. Its point is to understand that tradeoff, not to delete tests.

The rules come from `practices/testing.md` in the coding standards repo. When the project imports that file, it is the
authority.

## Step 1: Settle the scope

The scope is the argument: a directory, a package, or a set of test files. Without one, ask for it alone, since every
later step depends on it. Keep the scope small enough to read every test in it.

## Step 2: Detect, without asking

Ask nothing in this step.

1. Read the project's testing standards: `practices/testing.md` when imported, the language doc, and the project's
   `CLAUDE.md`. Note its runner commands, and whether it has a `test-cost` target and a carve-out form.
2. Run the scope's tests once, with the suite's normal parallelism. Record per-test or per-file durations from the
   runner's own report, such as `pytest --durations=0`, `go test -json`, or `vitest --reporter=verbose`. This is the
   baseline. It tracks a trend, so one run is enough. Do not run every file alone.
3. When the scope's tests fail, stop and report the failure. A baseline that does not pass cannot show what a batch
   removes.
4. For each test, write down:
   - The contract it proves, and the boundary it proves it through
   - The credible regression that makes it fail. When none exists, say so
   - Its owner: which test is the primary owner of that contract
   - Its cost: duration, plus setup the test alone needs
5. Find the low-value proofs:
   - Two or more tests own one contract at the same boundary
   - A test mocks an internal decision, so it proves only that the code calls a collaborator
   - An expected value is computed by the code under test
   - No credible regression would make the test fail
   - A test runs every permutation of an option where a few cases prove the contract. That belongs with the benchmarks
   - A costly test proves a contract that a cheaper layer already proves
   - Several tests repeat one setup that a table or a shared fixture would hold
   - A second layer repeats a contract with no distinct transport or lifecycle
6. Group the findings into batches. A batch is coherent: it covers one contract or one owner, and it applies on its
   own. After a batch, each contract it touches still has exactly one owner. A distinct contract is never merged away.
   For each batch, state:
   - The contracts it touches, and the test that stays their owner
   - Each test it retires, merges into a table, or moves to the benchmarks
   - The coverage given up, by name, or "none" when the kept owner proves all of it
   - The time saved, from the baseline, and the upkeep saved, such as fewer fixtures or near-copies
   - Duplication the batch keeps because it buys isolation, and what it isolates

## Step 3: Ask once

Present every batch in one AskUserQuestion call, with `multiSelect`, so the user picks which to apply. Each option's
description carries the coverage given up and the time and upkeep saved. When there are more batches than fit, offer
the batches with the most value, and list the rest in the report. A batch that gives up coverage says so first.

## Step 4: Apply

For each chosen batch, in turn:

1. Make the edits: retire, merge into tables, consolidate setup, or move to the benchmarks.
2. Run the scope's tests. They must pass. A failure means the batch removed a proof something still needed. Fix the
   batch by keeping the test that held that proof, and record it. Never weaken an assertion, add a retry, or lengthen
   a timeout to make it pass.
3. When the project has a `test-cost` target, run it on the files the batch changed.

## Step 5: Report

Rerun the scope the same way as the baseline. Report:

- Each batch applied, with its contracts, owners, and the coverage given up
- Cost before and after, per file and for the scope
- Each batch not applied, and why
- Findings with no batch, such as fragmented ownership that needs a code change rather than a test change

Commit only when the project's rules allow it, per `${CLAUDE_PLUGIN_ROOT}/rules/git-workflow.md`.

## Rules

- This skill runs only when the user types `/test-audit`. Its frontmatter sets `disable-model-invocation: true`. An
  audit needs the user's judgment, so no autonomous run, such as an approved `/work-queue` run or an autonomous
  `/proposal-reviewer` run, may start it and then pause on it. Keep that field.
- Never chase a deletion count. A batch that saves little and gives up nothing is fine to skip.
- Never retire the only owner of a contract.
- Retiring a test is a design decision. The user picks every batch.
