# presenterm Reference

The subset of presenterm syntax this skill writes. The floor is presenterm 0.15.0, the release that added d2 rendering
and `include`. Upstream docs: <https://mfontanini.github.io/presenterm/>.

## Front matter

```yaml
---
title: "Cutting the _AWS_ bill"
sub_title: What we found and what we propose
author: Name
date: 2026-10-21
theme:
  light: light
  dark: dark
---
```

- `title`, `sub_title`, `author` (or `authors:` as a list), `date`, `event`, and `location` feed the intro slide and the
  footer template. The intro slide exists only when `title`, `sub_title`, or an author is set.
- `theme` takes either a `light`/`dark` pair or `name: <theme>`. The pair picks by the terminal's background color.
  Detection is off inside tmux, so a pinned `name` is safer there.
- Built-in light themes: `light`, `catppuccin-latte`, `tokyonight-day`, `terminal-light`. Dark themes: `dark`,
  `catppuccin-frappe`, `catppuccin-macchiato`, `catppuccin-mocha`, `gruvbox-dark`, `tokyonight-moon`,
  `tokyonight-night`, `tokyonight-storm`, `terminal-dark`. The light themes already set a light d2 theme.
- `theme.override` patches individual theme keys inline, such as `override: { footer: { style: empty } }`.

Leave `options:` alone. This skill writes explicit `<!-- end_slide -->` separators, so none of the separator shorthands
are needed.

## Slides and titles

- Slides are separated by `<!-- end_slide -->` on its own line.
- A slide title is a setext heading: the title text, then a line of `===`.
- `#` through `######` headings inside a slide are styled per level by the theme. They are not slide titles.

```markdown
Spend is 70% compute
===

Body.

<!-- end_slide -->
```

## Comment commands

A single-line HTML comment is a command. An unknown command is an error when the deck loads.
`presenterm --list-comment-commands` prints the full list.

| Command | Effect |
|---------|--------|
| `<!-- pause -->` | Reveal what follows on the next keypress |
| `<!-- end_slide -->` | End the slide |
| `<!-- jump_to_middle -->` | Move the cursor to the vertical middle. Used for divider and single-statement slides |
| `<!-- column_layout: [3, 2] -->` | Split into proportional columns, here 60% and 40% |
| `<!-- column: 0 -->` | Write into column 0 |
| `<!-- reset_layout -->` | Return to full width |
| `<!-- new_lines: 2 -->` | Insert blank lines. `<!-- new_line -->` inserts one |
| `<!-- incremental_lists: true -->` | Reveal list items one at a time |
| `<!-- list_item_newlines: 2 -->` | Space list items apart |
| `<!-- alignment: center -->` | Align the following text: `left`, `center`, or `right` |
| `<!-- font_size: 2 -->` | Scale text, 1 to 7. Only kitty 0.40.0 and later honor it |
| `<!-- no_footer -->` | Hide the footer on this slide |
| `<!-- skip_slide -->` | Keep the slide in the file but skip it when presenting |
| `<!-- include: other.md -->` | Splice in another markdown file |
| `<!-- speaker_note: text -->` | A speaker note |
| `<!-- // text -->` | An author comment, ignored when rendering |

Multi-line speaker notes use a multi-line comment with a YAML block:

```markdown
<!--
speaker_note: |
  - spend is 70% compute
  - name the three accounts
-->
```

## Columns

```markdown
<!-- column_layout: [7, 3] -->

<!-- column: 0 -->

Text on the left.

<!-- column: 1 -->

A table or figure on the right.

<!-- reset_layout -->
```

`[1, 3, 1]` with only column 1 filled centers a block, such as a diagram or a key number.

## Text

- Bold, italics, strikethrough with `~text~`, inline code, links, block quotes, and tables are standard markdown.
- Colored text uses `<span style="color: #d20f39">text</span>`, or `<span class="name">` with a class from the theme's
  `palette.classes`. Other HTML tags are not supported.
- GitHub alerts render as styled call-outs:

```markdown
> [!important]
> Reserved instances lapse on 2026-12-01.
```

Alert kinds are `note`, `tip`, `important`, `warning`, and `caution`.

## Code

- A fenced block with a language is highlighted.
- `+line_numbers` shows line numbers. `+no_background` drops the code background.
- `{1,3,5-7}` highlights those lines. `{1-3|5-7|all}` steps through highlight frames, one per keypress.
- In most languages, a line starting with `///` and a space is hidden on the slide but still runs. In Rust, the
  prefix is `#` and a space.
- `+exec` runs the block on `<c-e>`, but only when presenterm starts with `-x`. Use it only when the user asks for live
  demos.
- A `file` block shows part of a file on disk:

````markdown
```file +line_numbers
path: ../src/billing.go
language: go
start_line: 40
end_line: 52
```
````

## Diagrams

d2 blocks render to images when tagged `+render`. This needs the `d2` binary on `PATH`.

````markdown
```d2 +render +width:80%
direction: right
payer: Payer account
prod: Production {
  ec2: EC2
  rds: RDS
}
payer -> prod: consolidated bill
```
````

- `+width:N%` scales the rendered image.
- The theme's `d2.theme` picks the d2 palette. The built-in light themes set one already.
- Mermaid works the same way with `` ```mermaid +render ``, but needs `mmdc` from `@mermaid-js/mermaid-cli`.

## Images

- `![](assets/chart.png)` with a path relative to the deck file. Remote URLs are not supported.
- `![image:width:50%](assets/chart.png)` scales by width and keeps the aspect ratio.
- kitty, iTerm2, WezTerm, Ghostty, and foot show real images. Other terminals fall back to ASCII blocks.
- Under tmux, images need `set -g allow-passthrough on`.

## Running a deck

- `presenterm slides.md` opens the deck. It reloads on save.
- `presenterm --present slides.md` turns off reloading for the real talk.
- `presenterm --validate-overflows slides.md` fails on any slide that does not fit the terminal.
- `presenterm --publish-speaker-notes slides.md`, and in a second terminal
  `presenterm --listen-speaker-notes slides.md`, shows the notes beside the deck.
- `presenterm --export-html slides.md` writes a self-contained HTML copy. `--export-pdf` needs weasyprint.
- presenterm queries the terminal when it starts. It cannot render or export from a non-interactive shell, so an agent
  cannot run any of these commands to check its own work.

Keys: `l`, `j`, or the arrow keys move forward. `gg` and `G` jump to the first and last slide. `<n>G` jumps to slide n.
`<c-p>` opens the slide index, `T` shows the layout grid, and `?` lists every binding.
