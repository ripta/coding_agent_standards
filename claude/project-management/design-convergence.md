# Design Convergence

How a coordinator iterates a design with the `design-critic` until it settles. When critique keeps moving between
acceptable options, the `design-judge` agent rules. Under the plugin the agents are named
`coding-standards:design-critic` and `coding-standards:design-judge`.

`proposal-reviewer` uses this protocol in its autonomous and converge modes. `/converge-design` uses the question loop
for a design question that has no proposal yet.

The protocol decides what to recommend. It does not decide whether the user is asked. The caller says that.

There are two loops. The question loop picks an option for one open question. The proposal loop checks the settled
design as a whole, and the fixes made to it, until a pass finds nothing that changes behavior.

## Keeping the Critic Independent

A critic that agrees is worth something only when it could have disagreed. A critic given the coordinator's gathered
facts and option order tends to refine the first, most-described option instead of ranking the list. Its value then
comes only from missing options and from objections it traces through the code. So:

- Spawn a fresh critic for every pass. Never send it an earlier pass's ranking, your recommendation, or your pros and
  cons
- Describe every option to the same depth. Do not list the option you favor first. Do not add a "facts gathered"
  section. A fact the critic needs goes into the description of the option it bears on
- Do not seed suspected gaps or objections for it to confirm. Let it find them

A re-check pass in the proposal loop is the one exception. It gets the list of changes and the finding each one answers,
since a fix cannot be verified without knowing what it fixes. It still gets no rankings, recommendation, or suspected
findings.

## The Question Loop

Run the loop per question. When several independent questions share a round, one critic spawn covers every question
still in the loop. A question leaves the loop as soon as it converges or goes to the judge. The others keep going.

Before the first pass, pick your own recommendation by the ranking in the "Choosing Options" section of
`rules/decision-making.md`. Keep it to yourself.

Each pass:

1. **Critique.** Spawn the critic with the proposal path or a description, the question, the current option list, and
   any session override.
2. **Reconcile.** Check each objection against the proposal and the code. When one holds, fold it into that option's
   description as a neutral fact, such as a failure scenario or a `Leaves undone` line. Do not say who raised it. Add
   each missing option that holds, and research it like the others. Change your recommendation only for a reason under
   the ranking.
3. **Push back.** When an objection does not hold, reject it with a one-line reason tied to the proposal or the code.
   Restating your preference is not pushback. A rejected objection stays out of the next pass's descriptions.
4. **Log the pass** in the question's ledger.
5. **Test for convergence.** Stop, send the question to the judge, or run the next pass.

Between passes, only verified facts and new options change the option list. Do not reword a description to see whether
the ranking moves.

### Convergence

The question **converges** when all of these hold after a pass:

- Your recommendation and the critic's top option are the same
- The critic's verdict on it is `SOUND`, or `SOUND WITH CAVEATS` where every caveat is folded in or rejected with a
  reason
- No objection to it that you kept was new this pass
- No option joined the list after the critic ranked it. An option the critic itself proposed counts as ranked

Most questions converge on the first pass. Run a second pass only when something changed that the critic has not seen:
an option added after it ranked, or a kept objection that changed the recommendation.

The question goes to the **judge** when any of these holds:

- **Oscillation**: the critic's top option, or your recommendation, returns to one it held in an earlier pass
- **Stalemate**: two passes in a row end with the same disagreement and no new kept objection or option
- **Budget**: three passes have run without convergence

`UNSOUND` from the critic does not end the loop. No listed candidate holds, so add the missing option it names and run
the next pass. An `UNSOUND` on the third pass goes to the judge like any other non-convergence.

## The Proposal Loop

Run it once every open question is settled. It replaces the single whole-proposal review.

1. **Full pass.** Spawn the critic on the proposal path for a whole-proposal review. List each decision the user kept
   against the critic's dissent.
2. **Fix.** Act on each finding that holds. A fix is a change to the design, so check it against the code before the
   next pass, the same as an option. A fix made on a wrong premise is how a coordinator starts a flip on its own.
3. **Re-check pass.** Spawn a fresh critic in re-check mode. Give it the proposal path and the list of changes since the
   last pass: each changed decision or section, and the finding it answers. It verifies each change and reports only
   `CONFIRMED` defects that change behavior or a verdict, in the changed text or caused by it. It labels any finding
   that would reverse a recorded decision `REVERSAL`, and ends with `CONVERGED` or `NOT CONVERGED`.
4. Repeat 2 and 3 until it converges.

The proposal **converges** when a re-check pass ends `CONVERGED`, or reports only findings that change no behavior or
verdict, such as wording or format. Fix those without another pass.

Never declare convergence over an open finding that changes behavior. The proposal loop runs at most three passes, the
full pass included. When the third pass still has such a finding, fix it, and tell the user the fix was not
re-checked.

A `REVERSAL` with new evidence from the code is a finding like any other. A `REVERSAL` without new evidence goes to the
judge. The finalists are the recorded decision and the reversal.

## The Ledger

Keep one ledger per question, and one for the proposal loop, in your own context. Each pass adds an entry:

- The critic's top option and its verdict, or `CONVERGED` / `NOT CONVERGED` for a re-check
- Your recommendation after reconciling
- Findings kept and rejected, each with its one-line reason
- Options added, descriptions changed by a verified fact, and fixes made

The judge reads the ledger. The caller summarizes it for the user. Never give it to the critic.

## The Judge

Spawn one `design-judge` per question that needs it. Give it the question, the proposal path or description, the
finalists, the ledger, and any override. In the question loop, the finalists are every option that was the critic's top
or your recommendation in any pass, plus the complete option.

Check each claim the judge marks `CONFIRMED` that you had not already checked. Then take the ruling:

- **An option**: that is the recommendation. Its record line carries the reason
- **`USER'S CALL`**: the standard does not decide it. The caller asks the user. Where the caller decides without asking,
  it may proceed on the judge's lean as a provisional decision, and must show it to the user before the run ends
- **`NONE`**: add the option the judge describes, and run one more critic pass with it on the list. If that pass does
  not converge, the question is a user's call, with the judge's described option as the lean

The judge rules once per question. Do not run the loop again on a question the judge settled, unless the user reopens
it.

## Models

Use the deep model where the work is tracing a failure through code, and a cheaper one where it is lookup.

- **`design-critic` and `design-judge`: Opus**, as their frontmatter sets. Re-check passes stay on Opus too. Finding a
  defect in changed text, or one a fix caused elsewhere, takes the same tracing as the first pass
- **Codebase scans and inventories: Sonnet.** Spawn `Explore` with `model: sonnet` for questions like "where is X
  produced" or "map every caller of Y"
- **File:line citations: `citation-verifier`** (Haiku), for citations in the proposal and in critic output you are about
  to rely on. Do not spend a critic pass checking citations
- **Proposal format**: check it yourself against `proposals.md`. It is not a critique

## Output

For each question:

- The recommendation, or `USER'S CALL` with a lean
- How it was reached: `converged in N passes`, or `judge after N passes` with the trigger (oscillation, stalemate,
  budget, or reversal)
- Any dissent left standing: the critic's reason for its top option when that is not the recommendation, and your
  one-line answer to it
- A record line: one sentence naming the winner and the reason

For the proposal loop: the passes run, the fixes made, and any fix left un-checked.

The caller shows the dissent to the user. It never hides it.

## Rules

- Every critic pass is a fresh spawn. Never send it history, rankings, your recommendation, or suspected findings. A
  re-check pass gets only the change list and the finding each change answers
- Only verified facts and new options change the option list between passes
- Check your own fixes against the code before the next pass
- At most three passes per question before the judge, plus one after a `NONE` ruling. At most three passes in the
  proposal loop
- Never declare convergence over an open finding that changes behavior
- One judge per question. Its ruling stands until the user reopens the question
