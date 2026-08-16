---
name: expand-lore-wiki
description: |
  Expand one or more source documents into a cohesive in-world lore wiki by
  identifying page-worthy people, factions, events, dates, places, artifacts,
  technologies, and concepts; writing compatible Markdown pages; cross-linking
  mentions in existing and new prose; and reconciling contradictions without
  inventing false certainty. Use when Codex is asked to grow fictional setting
  material, turn lore documents into wiki-style pages, build a linked world
  bible, or add style-matched lore illustrations from user-provided reference
  images under an explicit maximum-new-images budget.
---

# Expand Lore Wiki

Turn source documents into an interconnected body of lore while preserving
their voice, facts, uncertainties, and visual language.

## Non-negotiable rules

- Treat explicit statements in the supplied documents as canon.
- Treat supplied images as evidence only for what they visibly depict. A poster,
  painting, or propaganda artifact may support claims about imagery and rhetoric,
  but not necessarily about historical reality.
- Preserve gaps. Never invent an exact name, date, duration, outcome, identity,
  formula, boundary, or provenance merely to make a page feel complete.
- Phrase direct deductions as qualified reconstructions: `may`, `appears`,
  `likely`, `the present record does not establish`, or equivalent language that
  matches the source voice.
- If sources conflict, first check whether they describe different periods,
  viewpoints, aliases, or levels of certainty. If the conflict remains, present
  it as a disputed account. Do not silently choose a version.
- Preserve unrelated user changes and existing repository conventions.
- Put contextual links in prose. A `See also` list may supplement inline links,
  but never substitute for them.

## Image gate and budget

Generate images only when both conditions are true:

1. The user supplied at least one starting image.
2. The user supplied an explicit nonnegative integer maximum for **new** images.

Interpret phrases such as `maximum 5 new images`, `up to 3 generated images`, or
`image budget: 4` as a hard global cap. Do not infer a number from vague phrases
such as `a few`.

- If images are requested but the maximum is missing or ambiguous, request a
  numeric maximum before making any generation call. Text work may continue if
  it is independently authorized.
- If no starting image is supplied, perform a text-only expansion even when a
  budget is stated, unless the user separately asks to establish a new visual
  style.
- Count every image-generation call that returns an image against the budget,
  including discarded variants and retries. Never exceed the cap.
- Starting images and pre-existing project images do not consume the budget.
- Generate at most two new images for any one page. Zero is often correct.
- Do not spend the whole budget merely because it is available.

Before generating, read and follow the `imagegen` skill completely. Label each
input image's role in the prompt: `canonical visual evidence`, `style reference`,
`edit target`, or another precise role. Prefer a supplied image as a style
reference rather than copying its composition. Use one generation call per
distinct asset.

## Workflow

### 1. Inventory the material

Read all source documents completely. Inspect relevant repository instructions,
nearby files, naming conventions, link style, and existing image assets. When a
starting image exists only as a local file and has not been displayed, inspect
it before using it.

Determine:

- source document paths and intended output directory;
- the setting's narrative voice and document type;
- explicit chronology, aliases, geography, factions, objects, and relationships;
- which claims come only from an image or an in-world unreliable source;
- the numeric image budget and a running count starting at zero.

Default to placing new pages beside the source documents unless the user or
repository specifies another structure.

### 2. Build a private canon ledger

Before writing, make an internal ledger of claims with these fields:

- subject;
- claim;
- source document or image;
- status: `explicit`, `direct inference`, `disputed`, or `unknown`;
- aliases and related subjects.

Use the ledger to detect contradictions. Do not create a ledger file unless the
user asks for one.

### 3. Select page-worthy subjects

Consider people, groups, events, eras and dates, places, artifacts, resources,
technologies, institutions, doctrines, slogans, and primary-source objects.
Create a page when the subject has enough evidence for a useful lede and at least
one of these is true:

- it is central to the source's conflict or setting;
- it recurs or connects several other subjects;
- explaining it resolves otherwise confusing context;
- it is a distinctive named entity readers are likely to follow;
- it provides a useful chronology or geographic anchor.

Do not create a page for every capitalized noun. Prefer a smaller, meaningful
network over thin stubs. Merge aliases into one canonical page and record the
aliases in its lede. Gaps and red links are acceptable only if they match the
repository's established practice; otherwise leave uncreated subjects as plain
text.

### 4. Write compatible pages

Match the source voice and Markdown conventions. Use lowercase hyphenated
filenames unless the repository establishes another pattern.

A typical page contains:

1. one H1 title;
2. a concise lede defining the subject, time, place, and importance;
3. two to four descriptive sections chosen for the subject;
4. an explicit evidence, uncertainty, or historical-limits section when needed;
5. a short `See also` list only when it adds navigation not already supplied by
   the prose.

Do not force the template onto short pages. Avoid repeating identical background
paragraphs across several pages. Distinguish current fact from retrospective
interpretation and in-world propaganda.

### 5. Build the wiki link graph

After pages exist, update both original and newly created documents.

- Link the first meaningful prose mention of each created subject.
- Use relative Markdown links.
- Prefer linking the noun phrase, excluding adjacent commas and periods.
- Do not link every repeated mention, headings merely for decoration, or text
  inside code blocks.
- Add reciprocal links where they improve reading, not mechanically everywhere.
- Ensure each new page has at least one inbound and one outbound lore link when
  the source material supports them.
- Retain a compact related-pages index on a natural hub page when useful.

### 6. Allocate and generate images

Skip this step unless the image gate is satisfied.

Rank candidate images by:

1. centrality of the page;
2. whether the image explains something prose cannot show efficiently;
3. strength of support in the source material;
4. distinctness from existing images;
5. risk of falsely concretizing an unknown person, event, or outcome.

Favor architecture, geography, artifacts, processes, and well-attested scenes.
Avoid redundant portraits, decorative filler, and depictions that imply unknown
outcomes. An image of an uncertain individual should preserve that ambiguity.

For every generation:

- state the supplied image's role and request a new scene rather than a copied
  composition when appropriate;
- carry forward the reference's medium, palette, lighting, texture, and level of
  realism without inventing unrelated motifs;
- prohibit readable text unless exact text is necessary and supplied;
- prohibit watermarks and unsupported modern objects;
- inspect the result for subject accuracy, unwanted text, contradictions, and
  style continuity;
- copy the accepted asset into the project under a semantic, lowercase,
  hyphenated filename without overwriting existing files;
- insert it immediately after the paragraph it illustrates, using relative paths,
  descriptive alt text, and an italic caption beginning `Artist’s reconstruction`
  when the image is not itself canonical evidence.

If an output is unsuitable, count it against the budget. Retry only when budget
remains and one targeted prompt change is likely to fix the problem.

### 7. Reconcile and validate

Read the completed set as one work, not as independent pages. Check:

- names, aliases, capitalization, and faction relationships;
- exact versus approximate dates and calendar systems;
- geography and containment relationships;
- event sequence, objectives, and unknown outcomes;
- artifact origin versus later symbolism;
- claims derived from propaganda or artistic reconstruction;
- duplicate explanations and accidental escalation of inference into fact;
- image captions, paths, and budget usage.

Run the bundled validator. `<skill-dir>` is this skill's own directory, resolved
at runtime. It cannot be written literally. A plugin install places the skill
under `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/skills/`, and
that path changes with the plugin version. Do not invoke the script by a
project-relative path.

```bash
python3 <skill-dir>/scripts/validate_lore_wiki.py <lore-directory>
```

When images were generated, list every newly generated project-relative path and
the maximum:

```bash
python3 <skill-dir>/scripts/validate_lore_wiki.py <lore-directory> \
  --max-new-images 5 \
  --new-image images/example-one.png \
  --new-image images/example-two.png
```

Fix every reported error. Review warnings and either fix them or confirm they are
intentional. Also run any repository-specific Markdown checks.

### 8. Report the result

Summarize:

- pages created and source documents updated;
- image count used versus the maximum;
- saved paths for generated assets and a concise summary of the prompt set;
- validation results;
- important gaps deliberately left unresolved.

Do not claim that the lore is conflict-free merely because links resolve; report
the actual consistency review performed.

## Bundled resource

- `scripts/validate_lore_wiki.py`: check Markdown titles, local links and images,
  isolated pages, unreferenced generated assets, and the hard image budget.
