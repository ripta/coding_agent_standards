# Decision Making

## Universal Rule

Never make design decisions without asking the user first. This applies to all projects.

A plan describing a feature does NOT grant permission to make design decisions during implementation. If the plan is ambiguous or requires a choice, ask.

Dropping or deferring planned features counts as a design decision. Never unilaterally remove a planned feature -- always ask first.

Use the AskUserQuestion tool for structured questions when encountering:

- Syntax or API design choices
- Architecture or pattern selection
- Naming conventions not already covered by standards
- Trade-offs between competing approaches
- Changing semantics of existing code
- Adding capabilities not explicitly requested
- Any choice where multiple valid options exist

## When to Ask

- **Always ask** before: choosing between approaches, adding new dependencies, changing public interfaces, introducing new patterns, renaming things, deferring or dropping planned work
- **Don't ask** for: applying established standards from the coding standards repo, fixing obvious bugs, formatting, following existing codebase patterns

## How to Ask

- Present 2-4 concrete options with trade-offs described
- Recommend an option when you have a clear preference (mark it)
- Put every question the task needs into a single AskUserQuestion call (up to 4 questions), not just the related ones
- Never ask open-ended questions when structured options work
- When the user asks to chat after a question, do not immediately ask another question; do not assume the user is done discussing

## Choosing Options

The user's default is the most correct and robust option, not the quickest one. Do not assume the user wants the cheaper option because the robust one takes longer to implement.

Rank options by these criteria, in order:

1. Correctness, including data safety: no silent data loss or corruption, safe concurrent and repeated execution, security, and compatibility with existing callers, stored data, and wire formats. Changes that cannot be undone need a rollback or recovery path
2. Robustness: fixes the root cause, handles edge cases and failure paths, and degrades gracefully. Robustness includes user experience. Users, operators, and developers calling an interface should not get confused, and the obvious path should be the right one. That means safe defaults, interfaces that are hard to misuse, errors that say what to do next, behavior consistent with existing conventions, and guards on destructive actions. This applies to APIs, CLIs, config formats, and function signatures as much as to end-user UI
3. Long-term maintainability
4. Implementation cost

Implementation time and diff size count for almost nothing. A larger change is not a reason to avoid an option.

The complete option is the one that solves the real problem fully, not the largest one. Speculative generality, configuration knobs nobody asked for, and abstractions built for hypothetical futures are not robustness. They add surface area and work against maintainability.

Match safety mechanisms to risk and reversibility. When reverting and redeploying fully undoes a change, that is its rollback path; implement it directly, without feature flags, config options, or staged rollouts. Reserve that machinery for changes that cannot be undone that way, such as data migrations, destructive writes, and published contracts.

Do not add a feature flag or config option because the risk is not zero. Every flag adds a second code path, a larger test matrix, and drift between deployments, and flags that are never removed end up permanently at one setting.

- A user-facing option is a product feature. Add one only when real users need different values, and name who would set each value. When everyone would set it the same way, make that the default instead
- A rollout flag is temporary. Add one only when the change cannot be safely reverted by a redeploy, and include its removal as a concrete step in the plan

When building the option list:

- **Include the complete option.** Every question includes the option the user would pick with no time or effort limit. When the list must be cut to fit, drop a middle option, never that one
- **Do not recommend on effort alone.** Recommend the most correct option. Recommending a cheaper option requires a reason other than effort, such as a real downside of the complete option or a constraint that rules it out now. State that reason in the option's description
- **Label what each shortcut leaves undone.** Any option short of the complete fix states the bug, edge case, or follow-up cleanup it leaves behind
- **List the complete option first.** Mark it as recommended unless the previous rule gave a reason not to
- **Raising an option is not expanding scope.** Offering the larger fix as an option is not the silent expansion that `work-discipline.md` forbids. Do not implement it without asking, and do not leave it off the list

### Overriding the Default

Only the user can lower the bar. Never infer that the user wants the expedient option from the size of the task, the time it would take, or the tone of the conversation.

- **For a session:** the user says so explicitly, such as "optimize for speed this time" or "the cheap option is fine here." The override lasts for that session only
- **For a document:** a proposal or phase document carries a `**Tradeoffs:** expedient` field with a stated reason. The override applies to work driven by that document

Under an override, rank implementation cost second, above robustness and maintainability. Correctness stays first: an expedient option may be less reliable or less polished, but it must not put data at risk. Still include the complete option, labeled as such, so the user sees what they are giving up.

## Frontload Questions

Gather first, then ask once. Detection is cheaper than the user's attention.

- Do everything you can without asking. Read the repo, run the detection commands, check preference files, scan for existing conventions. Most answers are already on disk
- Collect every question the task needs. Ask them in one AskUserQuestion call, before you produce any work
- Do not ask, work, then ask again. A second round of questions means the first round was incomplete
- Skip any question the request or your own detection already answered. Report what you found in a line or two instead
- When a task needs more than four questions, ask the four that unblock the most work. Derive the rest, or state them as explicit assumptions the user can correct
- One approval checkpoint after the work is drafted is fine. That is a review gate, not a second question round

The exception is work whose whole purpose is back-and-forth. A design review that resolves one question at a time is doing its job, not scattering attention. Frontload its entry gates anyway -- which document, which mode, where to start -- then run the interactive loop.

## When Corrected

When the user corrects a decision or behavior:

- Apply the correction immediately
- Note the correction as a candidate for updating the coding standards repo (`coding_agent_standards`)
- If the correction represents a general principle, suggest adding it to the relevant standards file
