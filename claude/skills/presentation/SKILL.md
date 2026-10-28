---
name: presentation
description: |
  Use this skill to build a terminal slide deck for presenterm from existing source
  material: research, proposals, ADRs, ARCHITECTURE.md, design docs, implementation
  reports, or code. It inventories how much detail the sources hold, asks how much the
  main deck and the appendix should carry, then writes slides.md with speaker notes, and
  d2 diagrams only where a shape carries the claim. Triggers: "/presentation <topic>", "make a deck/slides/talk about X",
  "presenterm deck for X". DO NOT trigger for a .pptx or Google Slides deck, an HTML
  explainer page (walkthrough), or a written report (session-report).
model: opus
allowed-tools: Agent, AskUserQuestion, Bash, Read, Write, Edit, Glob, Grep
---

You build one presenterm deck from material that already exists. You do not research the topic. You decide what
matters in the sources, cut the rest, and lay what remains out as slides a person can present.

The deck runs top-down. The main slides carry the answer and the evidence at the depth the user picks. The appendix
carries the detail behind them, for questions.

## Bundled files

Read these before writing any slide. They live in this skill's directory (`${CLAUDE_SKILL_DIR}`, or beside this file if
that variable is unset).

- `style.md`: the spine, the detail tiers, the density limits, the slide types, and the speaker-note styles. It is the
  authority on what a slide may hold
- `presenterm.md`: the presenterm syntax this skill writes, for presenterm 0.15.0 and later
- `check.py`: static checks on a written deck. presenterm cannot render from a non-interactive shell, so this is the
  only check you can run yourself

## Workflow

### Step 1: Detect, without asking

No question belongs in this step.

1. Run `presenterm --version`. Below 0.15.0, stop and tell the user to upgrade, with `brew upgrade presenterm` on
   macOS. That release added d2 rendering
2. Run `command -v d2` and `command -v mmdc`. Record which exist. Neither is a reason to stop yet
3. Read `TERM_PROGRAM` and `TERM`. Only kitty honors `font_size`
4. Read the preference file. See "Preferences"
5. Resolve the topic to source files. See "Finding sources"

### Step 2: Inventory the sources

Read the primary sources yourself. They are the material the deck is built from, and a summary of them is not enough.
When there are more than five long documents, or the sources include code, fan out up to four `Explore` subagents in
one message. Give each a set of files and this brief:

> You are inventorying source material for a slide deck about `<topic>`. This is read-only. Do not modify any file.
> Return a list of topics. For each, give a one-line statement of the finding, the exact `file:line` it comes from,
> every number, date, and name it rests on, and whether it is a structure, a flow, a sequence, a comparison, a
> quantity, or a decision. For a structure, flow, or sequence, give how many parts and links it has, and whether one
> sentence states it. Mark anything you infer as a guess.

Then build the inventory. Each row is one topic with:

- The finding, as a claim a slide title could carry
- Its tier, headline, supporting, or deep, by the definitions in `style.md`
- Its source, as `file:line`
- The best visual for it: none, a key number, a table, a code excerpt, or a d2 diagram. None is the default. A diagram
  must pass the test in `style.md` "Diagrams"

Write the spine: the one sentence the audience should believe or do when the deck ends. The headline topics are the
ones the spine rests on.

Stop when the sources are too thin. They are too thin when there are fewer than three headline topics, or when a
headline has no source behind it. Tell the user what is missing, and name the skill that would fill it:
`deep-research` for an external question, `architecture-exploration` for how a codebase works, `rca` for why something
failed, or `session-report` to write up work done in a session. Do not fill the gap yourself.

### Step 3: Ask once, up front

Make one AskUserQuestion call. Build its options from the inventory's counts, never from abstract labels.

1. Main-deck depth. Offer headlines only, with supporting detail in speaker notes, and headlines plus supporting
   slides. Give each option its slide count and a rough talk length, at one to two minutes per main slide
2. Appendix depth. Offer none, supporting, and supporting plus deep, each with its slide count
3. Speaker-note style, `checklist` or `script`, when the preference file has none and the request did not say. See
   `style.md` "Speaker notes"
4. The output directory, when the preference file has none or it no longer exists

When there are still free slots, add the unresolved source questions from Step 1, such as two subsystems matching the
topic. When more than four questions remain, ask the four that unblock the most work. State the rest as assumptions in
the Step 4 outline.

Write the preference file when the answers set a value it lacked.

### Step 4: Outline, then wait for approval

Write the outline in chat. It is the review gate. Wait for the user to approve or change it before writing the deck.

- The spine, in one sentence
- Every slide in order: its number, its slide type from `style.md`, its claim title, and its visual
- For each diagram, the shape it shows that a sentence cannot, such as "two paths merge at the queue"
- The appendix slides, each with the main slide it backs
- What the inventory cut, in one line per topic, so the user can pull one back in
- Any assumptions from Step 3
- Any diagram the deck needs that cannot render, and the install that fixes it: `brew install d2` for d2, or
  `npm install -g @mermaid-js/mermaid-cli` for a Mermaid-only chart

When the user changes the outline, revise it and show it again. Do not start writing until it is approved.

### Step 5: Write the deck

Create `<dir>/YYYYMMDD-<slug>/`, with today's date and a kebab-case slug naming the subject, not the activity. On a
collision, extend the slug. Never overwrite an existing deck.

Write `slides.md` in that directory. Copy every local image the deck shows into `assets/` beside it. presenterm cannot
load remote images.

- Front matter sets `title`, `sub_title`, `author`, `date`, and `theme`. Use the preference file's `theme` as
  `theme: { name: <theme> }` when it is set. Otherwise write the `light`/`dark` pair from `presenterm.md`
- Follow the slide types, density limits, and diagram rules in `style.md`. The outline's slide types decide each
  slide's layout
- Every number, date, and name on a slide comes from the inventory, with its source in the speaker note or on the
  `Sources` slide. Never round or restate a number differently from its source
- Write every main slide's speaker note in the chosen style
- Start the appendix with a divider slide titled `Appendix`. `check.py` relaxes the density limits from there on
- Emit `font_size` only when Step 1 found kitty

### Step 6: Check

```sh
python3 "${CLAUDE_SKILL_DIR}/check.py" <deck>/slides.md --notes <checklist|script>
```

Fix every error. Fix each warning by splitting the slide or demoting content to the notes or the appendix, as `style.md`
says. Fix a thin-diagram warning by replacing the diagram with the sentence it says. Do not raise a limit to silence a
warning. A warning that is right to keep, such as a five-column comparison table the claim needs, stays. Say why in the
report.

Re-run until no errors remain.

An error that `d2` or `mmdc` is not installed is the user's to fix. Leave the diagram in place. Stop, and give the
install command in the report. Do not delete a diagram, or turn it into a table, to clear the error. The exception is a
Mermaid-only chart when the user declines to install `mmdc`, which `style.md` turns into a table.

### Step 7: Report

Give the user:

- The absolute path to `slides.md`
- The spine
- The slide count, split into main and appendix
- Any warnings left, with the reason for keeping each
- The commands to run it, with absolute paths:
  - `presenterm --validate-overflows <path>` to catch a slide too tall for the terminal
  - `presenterm <path>` to rehearse, with reload on save
  - `presenterm --publish-speaker-notes <path>`, and in a second terminal
    `presenterm --listen-speaker-notes <path>`, to see the notes beside the deck

You cannot see the rendered deck. Say so, and ask the user to report any slide that looks wrong. A correction that is a
style rule belongs in `style.md`, so later decks get it too.

## Preferences

Preference file: `~/.config/coding_agent_standards/presentation.json`. It is machine-local state. Never edit it into
this skill, and never commit it.

```json
{
  "default_dir": "/abs/path/to/decks",
  "theme": "light",
  "speaker_notes": "checklist"
}
```

- `default_dir`: where deck directories are created
- `theme`: a presenterm theme name that pins every deck to one theme. When it is absent, decks use the `light`/`dark`
  pair, which follows the terminal's background
- `speaker_notes`: `checklist` or `script`

Precedence, for each key:

1. A value in the user's request applies to this deck only. Update the file only when the user says to make it the
   default
2. Otherwise the file's value
3. Otherwise ask in Step 3, then write the answer to the file. `theme` is never asked. Leave it absent until the user
   names one

Validate what the file holds. When `default_dir` no longer exists, or a value is outside its allowed set, treat that
key as missing.

## Finding sources

1. Paths in the request are the sources. Read them, and the documents they link to that the topic needs
2. Otherwise search the current project for the topic. Look in `spec/`, `docs/`, `research/`, `ARCHITECTURE.md`,
   `README.md`, ADR and proposal directories, and the session-report directory from
   `~/.config/coding_agent_standards/session-report.json`
3. Search with the topic's distinctive words and their synonyms. "AWS cost" also matches `billing`, `spend`, `CUR`, and
   `Cost Explorer`
4. When the topic names code, find its entry points, its tests, and the proposal or ADR that introduced it

More than one plausible set of sources is an ambiguity for Step 3. Finding nothing is the thin-sources stop in Step 2.

## Rules

- Detect everything in Step 1 before asking. Ask once, in Step 3. The outline in Step 4 is a review gate, not a second
  question round. Do not write the deck until the outline is approved
- Build the deck only from the sources. Do not research the topic. When the sources are too thin, stop and name the
  skill that fills the gap
- Every number, date, and name on a slide traces to a source line in the inventory. Do not round it, restate it, or
  invent it
- `style.md` sets the density limits. Split or demote content to meet them. Never shrink content, and never raise a
  limit to pass `check.py`
- Draw a diagram only when its shape is the claim, per `style.md`. Draw it in d2. Use Mermaid only for the chart kinds
  `style.md` lists, and only when `mmdc` exists
- Write only inside the new deck directory, plus the preference file. Never overwrite an existing deck. Do not commit
  the deck unless the user asks, or the project's rules allow commits on the user's behalf. Never push
- Run `check.py` and fix its errors before reporting. A missing `d2` or `mmdc` is the exception: report the install
  command and keep the diagram. Hand the user the commands to see the deck, since you cannot render it yourself
