# Decision Making

## Universal Rule

IMPORTANT: Never make design decisions without asking the user first. This applies to all projects.

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
- **Don't ask** for: applying established standards from this repo, fixing obvious bugs, formatting, following existing codebase patterns

## How to Ask

- Present 2-4 concrete options with trade-offs described
- Recommend an option when you have a clear preference (mark it)
- Group related questions into a single AskUserQuestion call (up to 4 questions)
- Never ask open-ended questions when structured options work
- When the user asks to chat after a question, do not immediately ask another question; do not assume the user is done discussing

## When Corrected

When the user corrects a decision or behavior:

- Apply the correction immediately
- Note the correction as a candidate for updating standards in this repo
- If the correction represents a general principle, suggest adding it to the relevant standards file
