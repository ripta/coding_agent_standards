# Testing Practices

A test is a proof. It shows that a contract holds and names the regression it would catch. These principles say what a
test must prove and what it may cost. Commands and runner flags belong in the language docs and profiles.

## What a Test Proves

- Prove a caller-visible contract through its production owner. Test the code that owns the behavior, through the
  boundary its callers use.
- Fix external I/O with fixtures: recorded responses, files, and fake servers. Never fix internal decisions with mocks.
  A mock of an internal collaborator proves only that the code calls it.
- Compute expected values independently. An expected value derived from the code under test proves nothing.
- Prefer focused integration tests and independent unit contracts. Avoid mocked internal decisions and whole-product
  boots.
- Name the credible regression the test catches, and what it cannot prove. The test's name or doc comment carries both.
- Use synthetic content in fixtures and captures. Keep credentials, tokens, and real user data out of them.
- Reaching for many private controls in tests is a sign of fragmented ownership. Fix the ownership. Do not add
  test-only exports.
- For requests, paid calls, recovery paths, defaults, and performance claims, read the scenario contracts first. These
  are the tests and documents that state the expected behavior. Read them before changing the code or its proof.

## The Value Gate

Before adding a test, answer four questions:

1. What protected behavior, invariant, or independent contract does it cover?
2. What credible regression makes it fail?
3. Why do the existing tests miss that regression?
4. Which test is the primary owner of this contract? Each contract has one, at the strongest boundary that can prove it.

A new test is not always the best answer:

- When the new test covers what an older one proves, retire the older one.
- A second layer for the same contract earns its place only with a distinct transport or lifecycle.
- Prefer tables and shared fixtures to near-copies of one test. Consolidate repeated setup.
- Duplication is acceptable when it buys isolation. Say what it isolates.
- When the idiom for tables or fixtures is unclear in a language, document it in that language's doc or the project's.

The more a test costs, the higher its value bar. Cost is never a reason by itself to refuse a test. A test that takes
seconds must prove a contract that no cheaper layer can. Record that value in or beside the test. A test of a
concurrency mechanism can earn its cost. Exhaustively running every concurrency option is closer to a benchmark, and
belongs with the benchmarks.

## Working in Slices

- Work in vertical slices: failing behavior, then a coherent repair, then a passing proof.
- A regression test must fail on the original defect. See "Before Implementing" in `claude/rules/work-discipline.md`.
- Refactor only under green tests.
- When consolidating coverage, keep every distinct contract. Merging two tests must not drop what either proved.

## Cost

These rules apply to every project:

- Inject clocks. Do not add real timers, real sleeps, or long polls.
- Fix shared state. Do not serialize tests or pin them to workers to hide it.
- When tests need ports, document which tests claim which ports, so two tests never overlap.
- Build long end-to-end compositions in a release tier. Slow debug builds inflate their cost.

### Per-File Budgets

A per-file budget is opt-in. Adopt it once the suite's cost matters: runs take minutes, the suite has thousands of test
files, or a run saturates the machine's cores. A small project does not need one.

A project that adopts it:

- Declares a default target time per test file.
- Lets a carve-out shorten or lengthen that default for one file. The project picks the carve-out's form: a config
  file, a sidecar file, or a comment or directive in the test. Its tooling must be able to parse it.
- Gives each lengthening carve-out the contract it proves and why no cheaper layer can prove it.
- Measures every new or changed test file alone, with no parallelism. It records wall time, and CPU time and peak
  memory where available. Only those files run alone. The full suite keeps its parallelism.

The `make test-cost` target implements this. See "Measuring Changed Tests" in `practices/makefile.md`.

The measurements track trends. No single number needs to be accurate. Record them where the work is reported: during
milestone work, that is the session report. Any form works, such as a table, a chart, a log file, or a benchmark run.

Match the depth to the work. A garbage collector benefits from committed benchmarks and sample numbers. An API
project's tests may need only the enforced budget. Record justified net growth in cost separately, with its reason.

## Failures

A failing test is a defect. "Test Failures" in `claude/rules/work-discipline.md` sets when a failure blocks the work.

- Make a bounded attempt to reproduce it, in the original shard order first.
- Identify its owner. Fix the product, fixture, shared-state, or ordering bug.
- A proven repair adds a regression test. When another owner already fixed the cause, cite that fix.
- A passing rerun does not prove a fix.
- Never hide a failure with retries, longer timeouts, weaker assertions, broader mocks, or changed baselines.

## Flaky Tests

- Reproduce the failure in the original shard order before running the test alone. A failure that appears only in
  order usually means an earlier test file leaked shared state.
- Classify the cause: fixture state, a missing completion signal, or a product race. Repair whatever produces it.
- When removing something turned the suite red, read the accepted tradeoffs in the PR that removed it before restoring
  it.
- Choose a repeat count for the failure mode you reproduced. A fixed quota of clean runs proves little.

## Auditing

An audit weighs coverage against cost. Coverage means testing every permutation of state or input. Cost means suite
runtime and the upkeep of more tests. An audit removes low-value proofs as a coherent batch, and keeps one owner for
each contract.

An audit never chases a deletion count. Its point is to understand that tradeoff, not to delete tests. Run one with
`/test-audit`.

## Golden File Tests

- Store expected output alongside test input: `*.stdout.golden`, `*.stderr.golden`
- Provide an update mechanism: `update-golden` build step or flag
- Validate golden files don't contain failure markers (e.g., `FAIL:`)
- Support per-test configuration via sidecar files (`.flags`, `.stdin`, `.exitcode`)

## Testability Patterns

- Use dependency injection; never call global state directly in tested code
- Return release/cleanup callbacks from setup functions

## Organization

- Unit tests live next to the code they test (same file in Zig/Rust, `_test.go` in Go)
- Integration tests in a dedicated `tests/` directory
- Test helpers grouped in a shared test utility (not duplicated across test files)

## Running the App by Hand

A test runner owns the process it starts, so it sees a crash. Launching the app by hand to check a change gives no such
guarantee. A crash in a detached process goes unnoticed.

- Start the app so the shell owns it. Run it in the foreground, or in the background with stdout and stderr sent to a
  log file and the PID saved.
- Avoid launchers that detach the process and drop its output, such as macOS `open`.
- After interacting with the app, check that the process is still alive. If it exited, read its exit status and the log.
- Scan the log for crash output: Go `panic:` or `fatal error:`, Rust `panicked at`, Python `Traceback`.
- A crash during a manual check is a failure. Report it with the trace. Do not report the change as verified.

## What to Test

- Public API behavior, not internal implementation details
- Error paths and edge cases
- Concurrency mechanisms, such as tracking in-flight operations and verifying cleanup. The value gate's cost bar
  applies
- Run tests before completing any work: `make test lint`
