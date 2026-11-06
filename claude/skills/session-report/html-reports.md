# HTML Reports

An HTML report is usually written for someone other than the session's user. It might be for teammates, another
team, or engineering as a whole. Each audience calls for a different depth of evidence and a different tone. The team
that owns the system needs less background than a reader from across the company. Choose depth and tone for the
reader.

The principles below hold for every audience. They are not a template, so lay the page out to fit its content.

Everything in section 4 of `SKILL.md` still holds. When the target follows the wiki standard, the HTML page is a
second rendering of a Markdown entry. Put it beside that entry, as "HTML renderings" in
`${CLAUDE_PLUGIN_ROOT}/knowledge/wiki.md` says.

## Lead with the Verdict

- The verdict or conclusion opens the page, directly under the header, in a visually distinct box.
- When the findings fall into categories, the box says so in a sentence or two and lists each category with its status.
- A TL;DR is one or two sentences. When the verdict box already summarizes, drop the separate TL;DR.

## Keep the Header Short

The line under the title holds the date, the environment, and a link to whatever prompted the report, such as a
ticket, an alert, or a dashboard. Nothing else goes there. Put the access method, the query window, and the
prerequisites in the evidence.

## Make Each Finding Scannable

- Each finding is a unit of its own: a number, a title, and a status chip on one line. Its size or rate goes on the next
  line by itself, with the scope it covers. The explanation follows.
- The number carries through the page. The verdict box, the evidence steps, and any table that splits the data
  refer to a finding by its number.
- Keep confirmed findings, hypotheses, and open questions in separate sections. Never put a hypothesis in a finding's
  explanation as if it were settled.

## Format Evidence as Code

- Commands, config excerpts, and log samples go in real code blocks, each with a caption. The caption says what the
  block is: the file and lines, the log and its window, or what the command shows.
- Give each step one command and its own output block. Do not merge several commands into one block.
- Inline code is for identifiers only: a file name, a label, a flag, a host.
- Prerequisites are a list, not a sentence.
- Shorten a long excerpt and mark it as abridged. Do not change what remains.

## Add Graphs Only When They Carry the Claim

Draw a chart when a trend or a comparison is the point, and follow the `data-visualization` skill. When a single
number or a small table says it, use that instead. Diagrams follow `${CLAUDE_PLUGIN_ROOT}/practices/diagrams.md`.

## Link Everything a Reader Would Follow

- Every ticket links to its tracker. Every PR and commit links to its forge.
- Source references are permalinks pinned to a commit, with line anchors. Show the path and lines as the link text.
- External documentation URLs are anchors, even inside a log excerpt.
- Hosts that only scripts or `curl` can use stay plain text, since a browser cannot open them.

## Check the Page

Check the page in a browser, in light and dark, as "Checking a Rendered Page" in
`${CLAUDE_PLUGIN_ROOT}/practices/diagrams.md` says.
