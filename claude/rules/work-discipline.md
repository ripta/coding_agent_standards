# Work Discipline

## Before Implementing

- Write out what the "after" code looks like before changing anything
- Validate that the solution actually solves the stated problem, not just that it's technically possible
- Verify existing code is actually wrong before "fixing" it; trace through the logic to confirm the bug rather than shuffling code around

## During Implementation

- Do not ignore compilation or build failures
- Confirm with the user before moving on to a new milestone or task
- Read and maintain implementation plans before and after every milestone

## Refactoring

Refactoring existing code is in scope by default, not a separate concern requiring special permission. Adding new code on top of a structure that should change is itself a design decision.

- Evaluate whether existing code needs restructuring to support the change cleanly; do not pile new features onto code that has outgrown its shape
- When a feature would be substantially cleaner after refactoring nearby code first, surface that in the plan rather than working around it
- Treat structural improvements with the same weight as feature additions when scoping work
- Do not defer refactoring to a hypothetical "future cleanup" pass when it is the right tool for the current task

Refactoring still follows the decision-making rules: propose the refactor and its scope before doing it, and do not silently expand a feature task into a sweeping rewrite.

## Output Style

- Avoid emojis in output
- Do not include references to phase or milestone numbers in code or comments; those are project management artifacts
- Preserve the tone, wording, and style of existing comments that are not being changed; keep user voice exactly as written
- Separate logical blocks of code with blank lines; let the code breathe. Do not squash statements together to save vertical space. When a run of statements shifts from one logical step to the next, put a blank line between them. Newlines cost nothing. This applies in every language, not just one construct or syntax

## Comments

- Never narrate the code with comments. Do not label lines or blocks with what they do next, such as `// Finished line`, `// Last line:`, `// loop over items`, or `// return the result`. This applies to every language. The reader can see what the code does; a comment that only restates the next statement is pure noise. Delete these on sight, and never add them
- Do not add comments that restate what the code already says; if variable names and control flow make the intent clear, a comment is noise
- Only add comments where the logic is non-obvious or the "why" is not evident from the code
- Do not use parenthesized asides in comments; rewrite as natural prose that flows as part of the sentence
- Good comments document design facts that are hard to recover from local code:
  invariants, ownership or lifecycle boundaries, wire formats, ABI/layout
  contracts, concurrency ordering, policy decisions, external specifications, and
  language/runtime phase boundaries
- Keep comments concise and local to the decision they justify. Prefer one short
  design comment over a running narration of each line or intermediate value
- When a comment carries more than one idea, separate the ideas with a blank
  comment line into short paragraphs. This applies to every comment kind, not
  only doc comments. Do not pack multiple ideas into one dense block
- Wrap comment lines to the same width as the surrounding code, not to a narrow
  prose width. The target is roughly 100 characters. A bit over or under is fine;
  wrapping around 72 or 80 is too narrow and is a recurring correction. Do not
  default to short lines. When editing an existing comment, match the code's line
  width; do not reflow untouched comments
- Remove or avoid comment patterns that usually become noise: step-by-step
  restatements of implementation, repeated stack/state breadcrumbs, section
  dividers that do not add structure, test comments that paraphrase the
  assertion below, and repeated taxonomies already documented nearby
