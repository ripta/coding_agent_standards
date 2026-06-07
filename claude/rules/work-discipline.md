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

## Comments

- Do not add comments that restate what the code already says; if variable names and control flow make the intent clear, a comment is noise
- Only add comments where the logic is non-obvious or the "why" is not evident from the code
- Do not use parenthesized asides in comments; rewrite as natural prose that flows as part of the sentence
