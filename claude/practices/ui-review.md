# UI Review Practices

A review loop scores a rendered UI, fixes what the review found, and scores it again. The reviewer may be a person or
an agent. "Checking a UI" in `practices/ui-design.md` is the single pass before reporting a change done. This file is
the rubric a repeated, scored review runs against.

## Which Standards Apply

- A project that states its own UI standards overrides these, per `rules/precedence.md`. The rubric then scores
  against the project's values.
- A project standard is one the project wrote down, such as in its `CLAUDE.md` or its design system's docs. A value
  the code happens to use is not a standard. Score it against these rules until the project records it.
- When the project states nothing, the rules this file cites apply.
- The principle outranks the number. Typefaces differ in how they read at a given size and measure, so a project may
  set its own size, measure, or line height for its typeface. It records the value and the reason.
- A review report names every project standard it scored against in place of one of these rules.

## Gates

Gates are measured before any reviewer scores. Each one passes or fails. A failed gate is a finding to fix, not a low
score.

- **Contrast.** Text and UI boundaries meet their minimums in every scheme. This includes code comments, muted text,
  and diagram labels. See "Color and Contrast" in `practices/ui-design.md` and "Readability" in
  `practices/diagrams.md`.
- **Line length and line height.** Prose stays within the measure and line height in "Typography" in
  `practices/ui-design.md`.
- **Zoom and reflow.** At 200% text size, and at the narrowest supported width, nothing is clipped or lost. The page
  does not scroll sideways. Code, tables, and diagrams may scroll inside their own container. See "Hierarchy and
  Layout" in `practices/ui-design.md`, and "Responsive Layout" in `practices/ui-web.md` for the web widths.
- **Targets and focus.** Targets meet the minimum size, and focus is always visible. See "Controls and Affordances"
  and "Keyboard and Focus" in `practices/ui-design.md`.
- **Automated accessibility check.** The platform's checker reports no serious violations. For the web, see
  "Checking a Page" in `practices/ui-web.md`.
- **Diagrams.** Every diagram renders at its natural size. See "Readability" in `practices/diagrams.md`.

Measure each gate from the running page: computed styles, the DOM, or a keyboard run. A screenshot cannot show focus
order, zoom behavior, or an accessible name, so it never decides a gate. Phone-width captures need device emulation.
See "Checking a Rendered Page" in `practices/diagrams.md`.

## Dimensions

Each dimension scores 1 to 5. Every score cites at least one finding: the capture and the element it is about. A score
with no finding is discarded.

| Score | Meaning |
|---|---|
| 5 | Nothing to fix. A reader never notices this dimension. |
| 4 | Small issues that do not slow the reader or the task. |
| 3 | An issue that slows a reader or causes a misstep. |
| 2 | An issue that blocks some readers or some tasks. |
| 1 | The dimension fails for most readers. |

The dimensions, in the order a reviewer scores them:

- **Readability.** The type scale and heading hierarchy, vertical rhythm, line length as rendered, and how legible
  code and tables are. The page's chrome stays quiet next to the content.
- **Wayfinding.** The reader knows where they are, can move between pages, and can find a page.
- **Accessibility.** Judged from the page's structure, not from screenshots: landmarks, the heading outline,
  accessible names, and focus order. The gates cover what can be measured. This covers what needs judgment.
- **Consistency.** The page matches the host design system. Light, dark, and narrow layouts agree with each other.
  The same thing carries the same name everywhere.
- **Polish.** Judged against the product's stated design philosophy, or `practices/ui-design.md` when it states none.
  Every element earns its place.

## Overall and Stopping

- Overall is the lowest dimension score. Do not ask the reviewer for it. An average lets one weak dimension hide
  behind strong ones.
- Stop when every gate passes and every dimension scores at least 4. Also stop at the round cap the project sets.
- Do not wait for 5 everywhere. Near the top of the scale, a change of one point is mostly reviewer noise, so a loop
  that waits for 5 runs to its cap.
- A finding at 4 may still be fixed. It does not hold the loop open.

## Captures

- Components alone do not show reading. Capture a long prose page, and a page dense with both code and prose.
- Capture the long page at the narrowest width in both schemes, and at 200% text size.
- Capture every view in light, dark, and narrow layouts.
- Keep the set of captures fixed across rounds, so each round's scores compare with the last.

## Reviewer Drift

A fresh reviewer each round avoids anchoring on the last round's scores. It also makes a one-point change hard to tell
from noise.

- Include one anchor capture that no fix ever touches. Score it every round.
- When the anchor's score moves, the reviewer drifted. Discount an equal move elsewhere in that round.
- Treat a score change as real only when the finding it cites changed.
