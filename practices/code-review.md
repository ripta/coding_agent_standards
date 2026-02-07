# Code Review Practices

## Review Priority

1. Security issues
2. Stability concerns (nil pointers, resource leaks, panics)
3. Correctness issues
4. Consistency with existing codebase patterns
5. Performance
6. Style and idioms

## Standards

- No `//nolint` or equivalent suppression without explicit justification
- Fix root causes; don't suppress linter warnings
- No temporary files or debug artifacts in commits
- Generated code must be regenerated, not hand-edited

## Before Submitting

- Run `make test lint` (or equivalent) and verify it passes
- Review your own diff before requesting review
- Keep PRs focused on one concern; split unrelated changes
