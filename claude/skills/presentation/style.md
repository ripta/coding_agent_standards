# Slide Style

These rules govern what goes on a slide and how it looks. They are a starting point. Change them here when a real deck
shows a rule is wrong, so every later deck gets the fix.

## The spine

Every deck has one sentence that says what the audience should believe or do when it ends. Write it before the outline.
A slide that does not serve the spine is cut, or moved to the appendix.

The main deck runs top-down:

1. The answer: the spine, stated plainly, in the first two slides
2. Why it matters: the problem, with one number or one picture
3. How we know: the evidence, one claim per slide
4. What it means: the decision, the ask, or the next step
5. Appendix: the detail behind each claim, for questions

## Detail tiers

Each topic in the source material gets exactly one tier.

- Headline: it changes what the audience believes or decides. Removing it would change the spine.
- Supporting: it is the evidence or mechanism behind a headline. A skeptic asks for it.
- Deep: it is a specific a few people care about. Examples are a full cost table, an edge case, a rejected
  alternative, or an implementation detail.

The main deck carries the tiers the user picked. A tier below the main depth goes to speaker notes when a sentence
covers it. Otherwise it goes to an appendix slide. Nothing a slide shows exists only in the notes, and nothing the
presenter must say exists only in the appendix.

Every appendix slide names the main slide it backs, in a small line under its title: `Backs: Spend is 70% compute`.

## Density

A slide makes one claim. The audience should get it in about five seconds.

- The title is the claim, as a short sentence: "Compute is 70% of spend", not "Cost breakdown". A section divider is the
  only slide whose title is a label
- At most five bullets, each one line, under about 60 characters. Three is better
- No paragraphs. A slide never carries two sentences in a row of running prose
- About 40 words of body text at most, not counting code, tables, or diagrams
- At most six table rows and five columns in the main deck. A bigger table goes to the appendix, with its one important
  row pulled into the main slide
- At most 12 code lines on a slide. Use highlight frames, such as `{1-4|6-9}`, rather than a second slide
- At most one visual per slide: a diagram, a table, a code block, or a key number. Pair it with text in columns, not
  stacked. A slide needs no visual when its claim reads in one line

When a slide breaks these limits, split it or demote some of it. Do not shrink it to fit.

## Slide types

Pick from these before inventing a layout.

- Divider: `<!-- jump_to_middle -->`, then the section title. Use one before each part of a long deck, and one before
  the appendix
- Statement: `<!-- jump_to_middle -->` and `<!-- alignment: center -->`, then one sentence or one number. Use it for the
  spine and the ask
- Claim and evidence: a claim title, then one visual with up to three bullets beside it in a `[3, 2]` or `[7, 3]`
  layout
- Diagram: a claim title, then a d2 diagram centered in `[1, 6, 1]` or at full width. Only for a diagram that passes
  the test in "Diagrams"
- Comparison: two columns of equal width, each led by a `###` heading. Use it for before and after, or option A
  against option B
- Key number: a short claim title, then the number alone, centered, with one line of context under it
- Code: a claim title, then one block with highlight frames, and at most one line of text
- Takeaway: an `[!important]` alert for the one thing to remember from a section

Under kitty, `<!-- font_size: 3 -->` can enlarge a key number or a statement. Other terminals ignore it, so a slide
must read well without it.

## Diagrams

Most slides need no diagram. A claim about structure, flow, or sequence is not enough on its own. A diagram earns its
slide only when its shape is the claim, and a sentence cannot carry that shape. These shapes earn one:

- Paths that branch or merge
- A cycle or feedback loop
- Nested boundaries, such as which services run inside which account
- Fan-in or fan-out past three
- Several actors exchanging messages in order

These shapes do not:

- A straight chain. `A -> B -> C` is a sentence with arrows. Write the sentence
- A hub with a few spokes. That is a bullet list
- Three or four boxes with a line or two between them
- A diagram whose labels repeat the bullets beside it

Before drawing one, write the sentence the diagram says. When that sentence, or up to three bullets, carries
everything the picture shows, use the text. Prefer a table when the claim is a comparison of values.

`check.py` warns on a d2 diagram with fewer than five nodes, and on one that is a straight chain. Fix the warning by
replacing the diagram with the sentence it says. When the shape truly is the claim, keep it and say why in the report.

## Charts

A chart of data follows the `data-visualization` skill (`coding-standards:data-visualization` under the plugin). Read
it before writing an `xychart`, a `pie`, or an image of a chart. Its rules hold on a slide as anywhere else. The title
states the finding, and the axes carry labels and units. Bars start at zero, and any other baseline states its reason.
A slide title can serve as the chart's title.

- Use d2. It covers architecture, data flow, nested boundaries like accounts and VPCs, sequence diagrams, and ER and
  class diagrams
- Use Mermaid only for what d2 does not draw: `gantt`, `timeline`, `sankey`, `pie`, `xychart`, `quadrantChart`, and
  `gitGraph`. Those need `mmdc`. Without it, use a table and say which chart was dropped
- Rewrite a source document's Mermaid flowchart or sequence diagram in d2. Keep the diagram's labels, and cut the nodes
  the slide's claim does not need
- Label edges with what flows: `-> : invoices`, not a bare arrow
- Use `direction: right` for flows read left to right, and the default for hierarchies

## Reveals

- Use `<!-- pause -->` to reveal an answer after a question, or the next step in a sequence. Most slides need none
- Use `<!-- incremental_lists: true -->` only when each bullet deserves its own beat in the talk
- Never pause inside the appendix

## Speaker notes

Each main slide gets a note, written in the presenter's note style. Supporting detail lives in the note, not on the
slide. A note never repeats the slide's text.

- `checklist`: two to five keyword bullets, each a point to land, with no full sentences. Add any number, name, or date
  the presenter must not misquote. The presenter scans it to catch a point they skipped
- `script`: short spoken paragraphs, one per beat of the slide. When the slide has pauses, write one paragraph per
  pause. The presenter can read it aloud

Use the multi-line form for anything longer than one line.

## Visual consistency

- One theme for the whole deck, set in the front matter
- Text color only through a theme palette class, and only to mark the one word or number that carries a claim. Never
  color whole sentences
- Keep source citations off the slide face. Put them in the speaker notes, or in a `Sources` slide at the end of the
  appendix
- End the main deck with the statement slide for the ask or the decision, not with "Questions?"
