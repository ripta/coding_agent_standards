# Decision Making

## Universal Rule

Never make design decisions without asking the user first. This applies to all projects.

A plan describing a feature does NOT grant permission to make design decisions during implementation. If the plan is
ambiguous or requires a choice, ask.

Dropping or deferring planned features counts as a design decision. Never unilaterally remove a planned feature --
always ask first.

The user can authorize deciding without asking, for one run, by choosing it explicitly. There are three ways: approving
a `/work-queue` plan, choosing `proposal-reviewer`'s autonomous mode, and approving a `/bug-sweep` run. Each lists
exactly which rules it relaxes. Nothing outside that list is relaxed, and the run ends with the user seeing every
decision it made.

Use the AskUserQuestion tool for structured questions when encountering:

- Syntax or API design choices
- Architecture or pattern selection
- Naming conventions not already covered by standards
- Trade-offs between competing approaches
- Changing semantics of existing code
- Adding capabilities not explicitly requested. See "Scope Additions"
- Any choice where multiple valid options exist

## When to Ask

- **Always ask** before: choosing between approaches, adding new dependencies, changing public interfaces, introducing
  new patterns, renaming things, deferring or dropping planned work
- **Never push back** on a user's request by citing a proposal. A proposal does not bind later work. See
  `project-management/proposals.md` "A Proposal Never Blocks the User"
- **Don't ask** for: applying established standards from the coding standards repo, fixing obvious bugs, formatting,
  following existing codebase patterns

Applying a standard means following a rule that names the answer, such as a formatting rule or a commit convention. The
ranking in "Choosing Options" is not such a rule. It picks the option to recommend. The design question still goes to
the user, with that option marked, even when the ranking leaves one clear answer. Only the authorizations in "Universal
Rule" let an agent decide a design question without asking.

## How to Ask

- Present 2-4 concrete options with trade-offs described
- Recommend an option when you have a clear preference (mark it)
- Put every question the task needs into a single AskUserQuestion call (up to 4 questions), not just the related ones
- Never ask open-ended questions when structured options work
- Give every multiSelect question an explicit option for picking nothing, such as `None`. The tool
  reports an empty pick as "The user did not answer the questions." That is indistinguishable from a user who is away.
  Never tell the user to pick none
- Read a pick of that option together with another option as a contradiction, and ask that question again
- When the user asks to chat after a question, do not immediately ask another question; do not assume the user is done
  discussing
- An answer that is itself a question asks for an answer. Reply in prose. Ask the question again only after the user has
  that answer, and only when they have not settled it in their reply
- When a recommendation changes from an earlier round, say what changed it: the new fact, or the mistake in the earlier
  one. Never switch the marker silently

## Choosing Options

The user's default is the most correct and robust option, not the quickest one. Do not assume the user wants the cheaper
option because the robust one takes longer to implement.

The ranking below governs every choice, in every step and every agent. That covers the options a question lists, the
one it recommends, and each decision a run makes without asking. It covers a critic's or a judge's ranking, a deferral,
and what a step does when its budget runs out.

A skill's procedure never outranks the ranking. When a step would produce a result the ranking rejects, follow the
ranking, and say which step you overrode. A project, a document, or a session can change the ranking itself. See
"Overriding the Default".

Rank options by these criteria, in order:

1. Correctness, including data safety: no silent data loss or corruption, safe concurrent and repeated execution,
   security, and compatibility with existing callers, stored data, and wire formats. Changes that cannot be undone need
   a rollback or recovery path
2. Robustness: fixes the root cause, handles edge cases and failure paths, and degrades gracefully. Robustness includes
   user experience. Users, operators, and developers calling an interface should not get confused, and the obvious path
   should be the right one. That means safe defaults, interfaces that are hard to misuse, errors that say what to do
   next, behavior consistent with existing conventions, and guards on destructive actions. This applies to APIs, CLIs,
   config formats, and function signatures as much as to end-user UI
3. Long-term maintainability
4. Implementation cost, as a tiebreaker only

Implementation cost decides only between options that are equal on the first three criteria. It never outweighs a
difference in correctness, robustness, or maintainability, however small. Implementation time and diff size are not
reasons to avoid an option.

Every claim that moves an option up or down is a fact to check, not an estimate. That covers a cost, such as "it needs a
new permission". It also covers a missing benefit, such as "it adds nothing the existing log does not". Check the claim
before ranking on it: read the code or the docs, or run a probe. An unchecked claim moves nothing, however likely it
seems.

When a claim cannot be checked before the decision, rank on the checked facts alone. If the claim would change the
recommendation were it true, make the recommendation conditional on it. Name the check that settles it, and schedule
that check first, such as the first item of the first milestone.

The complete option is the one that solves the real problem fully, not the largest one. Speculative generality,
configuration knobs nobody asked for, and abstractions built for hypothetical futures are not robustness. They add
surface area and work against maintainability.

Nor is the complete option the one with the most special cases. When a question asks how a case behaves, list the plain
behavior: what the system does with no rule for the case. A requirement that forces special cases is a choice too. When
one does, list the option that drops it, even when an accepted ADR imposes it. That option says how the ADR would
change: an amendment that narrows or strikes the principle, or a new ADR that supersedes it when its reason no longer
holds. Only the user decides that.

Investing in the code the change touches is different from speculating. It counts toward correctness, robustness, and
maintainability, and it is part of the complete option. Treat work as an investment when it leaves that code more
correct or easier to change correctly:

- Fixing the structure that made the bug possible, not just the instance of it
- Making an invalid state unrepresentable, or a misuse a compile or load error
- Removing a one-way door or adding the missing recovery path
- Paying down the debt that made a workaround tempting

To tell the two apart, ask what the work serves. Investment serves the problem in front of you and the code that
already exists. Speculation serves a requirement nobody has stated. When you cannot name a current caller, bug, or
failure mode that the work protects against, it is speculation. Naming one does not settle scope. See "Scope
Additions".

A failure mode is current when the bug, a contract, or the code's own docs name it. It stays current even when nothing
has triggered it yet. Guarding it is investment, not speculation. "No release has done that yet" is not a reason to
leave it unguarded.

When code breaks a contract its own docs state, the default fix restores the contract. Rewriting the docs to match the
code withdraws the contract. That is a shortcut, and its option says which guarantee it drops. An option that cannot
have a failing regression test leaves the behavior unfixed, and its option says so.

Match safety mechanisms to risk and reversibility. When reverting and redeploying fully undoes a change, that is its
rollback path; implement it directly, without feature flags, config options, or staged rollouts. Reserve that machinery
for changes that cannot be undone that way, such as data migrations, destructive writes, and published contracts.

Do not add a feature flag or config option because the risk is not zero. Every flag adds a second code path, a larger
test matrix, and drift between deployments, and flags that are never removed end up permanently at one setting.

- A user-facing option is a product feature. Add one only when real users need different values, and name who would set
  each value. When everyone would set it the same way, make that the default instead
- A rollout flag is temporary. Add one only when the change cannot be safely reverted by a redeploy, and include its
  removal as a concrete step in the plan

When building the option list:

- **Include the complete option.** Every question includes the option the user would pick with no time or effort limit.
  When the list must be cut to fit, drop a middle option, never that one
- **Combine the parts.** When candidates each answer part of the problem, list the option that combines them. It is
  often the complete option. Posing the parts as alternatives hides it
- **Deferring is a shortcut.** An option that defers part of the work, or builds it later, is cheaper than one that
  builds it now. Like any shortcut, it needs a reason other than effort. Waiting on evidence that does not exist yet is
  such a reason. Evidence you could gather now is not. Its description says what stays unanswered until the work is
  built
- **Do not recommend on effort alone.** Recommend the most correct option. Recommending a cheaper option requires a
  reason other than effort, such as a real downside of the complete option or a constraint that rules it out now. State
  that reason in the option's description. A downside is a cost to correctness, robustness, or maintainability. A small
  benefit is not a downside. Neither is a failure that seems unlikely. Both weigh benefit against effort
- **Label what each shortcut leaves undone.** Any option short of the complete fix states the bug, edge case, or
  follow-up cleanup it leaves behind. A forgone investment counts too
- **List the recommended option first.** It is the complete option unless the previous rule gave a reason not to. When
  it is not, list the complete option second and label it as the complete option. Never list an unrecommended option
  above the recommended one
- **Mark every option you recommend.** Every question carries a recommendation, including a multiSelect question. When
  the options are independent fixes you would apply together, say so in the question and mark each one
- **Raising an option is not expanding scope.** Offering the larger fix as an option is not the silent expansion that
  `work-discipline.md` forbids. Do not implement it without asking, and do not leave it off the list. Label it when it
  adds scope. See "Scope Additions"
- **Check the list before you ask.** Before asking, and before deciding without asking, answer the question the user
  would ask: which option is most correct and most robust? When that answer is not the recommended option, or is not on
  the list, fix the list first. The user should never need to ask it

### When a Reason Proves Wrong

A user who picks an option you recommended chose on the reasons you gave. When one of those reasons later proves false,
the choice rests on a false fact. Ask the question again at once, with the corrected ranking and a note on what was
wrong. Do not keep the choice because the user made it. Do not patch it with revisit triggers or special cases to
preserve it.

A decision you made yourself, under an authorization such as an autonomous review, reopens instead. Decide it again by
the ranking.

### A User's Decision

A decision the user made stays the user's. No agent or process changes it, narrows it, drops it, or defers it. That
covers its wording, even when the direction stays the same. No authorization relaxes this, an autonomous run included.
Only the user's own answer changes the decision.

An agent may still recommend something different. A recommendation is only that:

- Leave the user's decision as written, and keep building on it until the user answers
- Record the recommendation beside the decision, where the user will see it. In a proposal, that is a
  `**Pending override:**` line. See "Who Decided" in `project-management/proposals.md`
- Ask the user. An agent that asks as it goes asks at once. An autonomous run never stops, so it asks at its gate
- In the question, say what the user decided and when, then what the agent recommends and why
- List the recommendation first, marked `(Recommended)`, and say in its label or description that it overrides the
  user's decision. List the user's decision next, labeled as the user's, with its date

Never present an override as a plain recommendation. Never keep a line that credits the user on text the agent changed.

### Scope Additions

Scope is the problem the user stated, plus what the user has approved since. A proposal's scope is its Summary and
Motivation, the settled decisions the user chose or kept, and its out-of-scope statements. The complete option is
complete within that scope.

A scope addition brings in a requirement, component, contract, or cross-cutting concern that the scope does not hold.
A finding can be real and still be an addition. A gap in a neighboring system is one example: the requested change
exposes it but does not create it. The failure mode justifies raising the addition. It does not put the addition in
scope.

Work that serves an addition belongs to that addition. An addition the user has not kept does not widen the scope, so
the decisions, milestones, and risks built on it are part of it too.

An addition is not forbidden. It is labeled, so the user always sees it:

- An option that adds scope says so in its description, and names what it would bring in
- An open question about an addition lists "no addition" among its candidates. It asks whether before it asks how
- The Decision Log entry that settles an addition carries the `addition` tag. See `proposals.md` "Decision Log Tags"
- Removing or narrowing an explicit out-of-scope statement is an addition

Approving a direction is not approving a design. When the user picks a direction, only the direction is settled. Each
mechanism under it is its own decision.

### Overriding the Default

The ranking above is the default. Only a project, a document, or a session changes it. Never infer a change from the
size of the task, the time it would take, or the tone of the conversation.

- **For a project:** the project's own instructions state a different ranking, in any words. They may be its
  `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, or a standards document. A prototype that puts shipping speed first is
  one example. A contributing guide that asks for minimal diffs is another. Follow that ranking for all work in the
  project, per `precedence.md`. Where it is silent, the default holds
- **For a document:** a proposal carries a `**Tradeoffs:** expedient` field with a stated reason. The override applies
  to work driven by that proposal, including its queue rows
- **For a session:** the user says so explicitly, such as "optimize for speed this time" or "the cheap option is fine
  here." The override lasts for that session only

The narrowest one that applies wins: a session over a document, and a document over a project. Name the source whenever
you apply one, in the option's description and in every critic or judge brief. A subagent cannot see the session, and
may not read the project's instructions.

A project's ranking applies as the project states it. Under an expedient override from a document or a session, rank
implementation cost second, above robustness and maintainability. Correctness stays first: an expedient option may be
less reliable or less polished, but it must not put data at risk. Still include the complete option, labeled as such,
so the user sees what they are giving up.

## Frontload Questions

Gather first, then ask once. Detection is cheaper than the user's attention.

- Do everything you can without asking. Read the repo, run the detection commands, check preference files, scan for
  existing conventions. Most answers are already on disk
- Collect every question the task needs. Ask them in one AskUserQuestion call, before you produce any work
- Do not ask, work, then ask again. A second round of questions means the first round was incomplete
- Skip any question the request or your own detection already answered. Report what you found in a line or two instead
- When a task needs more than four questions, ask the four that unblock the most work. Derive the rest, or state them as
  explicit assumptions the user can correct
- One approval checkpoint after the work is drafted is fine. That is a review gate, not a second question round

The exception is a design review whose later questions depend on earlier answers. It cannot ask everything up front.
It asks in rounds instead: each round batches up to four questions that do not depend on each other into one call. A
round holds a single question only when no other question is independent of it. Frontload its entry gates anyway --
which document, which mode -- then run every round without pausing between them.

## When Corrected

When the user corrects a decision or behavior:

- Apply the correction immediately
- Find the rule that misled you, if one did. Propose a fix to that rule at its home, and let the user approve it
- Note the correction as a candidate for updating the coding standards repo (`coding_agent_standards`)
- If the correction represents a general principle, suggest adding it to the relevant standards file
- Write a memory only as `memory.md` allows. Most corrections need none
