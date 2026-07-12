# Sentence Structure

Applies everywhere: commit messages, PR summaries, code comments, docs, spec
prose, and chat.

Write one idea per sentence. Complex sentences are often ambiguous or wrong.
When you chain clauses, a reader cannot tell which subject a later verb attaches
to. Broken logic hides in that ambiguity. A period forces each claim onto its
own, where a wrong one is obvious.

- Say the concrete thing plainly. Do not bury it under qualifiers.
- Never use two conjunctions for one link. `since X, so Y` and
  `because X, therefore Y` are broken. Pick one.
- Do not join unrelated facts with `and`. An `and` claims the two facts are
  related. If they are not, use two sentences.
- State each cause-and-effect step as its own sentence.

Bad:

> `executeResolvedWord` re-derived the same constant-per-word facts on every
> call by rescanning markers and the word body, and since module-cache and
> module-deps-frame words are synthesized fresh outside the definition
> finalization points, so their flags had to be computed at synthesis time or a
> generic library word would carry empty flags, silently skip dispatch, and
> corrupt the stack.

Good:

> `executeResolvedWord` recomputed the same per-word facts on every call. It
> rescanned the markers and the word body each time. That was wasteful.
>
> Separately, `module-cache` and `module-deps-frame` words are synthesized
> outside the definition-finalization points. Their flags must be computed at
> synthesis time. Otherwise a generic library word carries empty flags. It then
> silently skips dispatch and corrupts the stack.
