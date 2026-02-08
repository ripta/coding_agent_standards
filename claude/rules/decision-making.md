# Decision Making

## Universal Rule

IMPORTANT: Never make design decisions without asking the user first. This applies to all projects.

Use the AskUserQuestion tool for structured questions when encountering:

- Syntax or API design choices
- Architecture or pattern selection
- Naming conventions not already covered by standards
- Trade-offs between competing approaches
- Any choice where multiple valid options exist

## When to Ask

- **Always ask** before: choosing between approaches, adding new dependencies, changing public interfaces, introducing new patterns, renaming things
- **Don't ask** for: applying established standards from this repo, fixing obvious bugs, formatting, following existing codebase patterns

## How to Ask

- Present 2-4 concrete options with trade-offs described
- Recommend an option when you have a clear preference (mark it)
- Group related questions into a single AskUserQuestion call (up to 4 questions)
- Never ask open-ended questions when structured options work

## When Corrected

When the user corrects a decision or behavior:

- Apply the correction immediately
- Note the correction as a candidate for updating standards in this repo
- If the correction represents a general principle, suggest adding it to the relevant standards file
