# Diagram families and interactive elements

The catalog the `walkthrough` skill draws from. Every snippet works against
`template.html` as shipped. The CSS classes and the JS hooks (`data-swap`,
`data-stepper`, `registerChart`, `data-mk`) are already wired.

Libraries load in `<head>`, and the app script runs last, at the end of
`<body>`. A widget's own `<script>` goes inline beside its markup, anywhere in
the body.

## How to choose

Pick **two or three diagram families** and reuse them across the whole page. A
page with six visual styles reads as six pages stapled together.

Pick **two or three interactive elements**. Each must teach something a static
figure cannot. A slider that changes a number nobody was wondering about is
noise.

Ask of every figure: *what should the reader notice?* If you cannot answer that
in one sentence, the figure is decoration. Cut it, or replace it with a
sentence.

---

## Diagram families

### 1. Data flow

The default. Components as boxes, data as labelled edges. **Put a sample
payload on the edge.** `{"id": 42}` teaches more than `request`.

```html
<figure>
  <div class="mermaid">
flowchart LR
  C["Client"] -- "POST /orders" --> G["Gateway"]
  G -- "{qty: 2, userId: 7}" --> S["Order service"]
  S --> DB[("orders")]
  S -. "on failure {code: 429}" .-> C
  </div>
  <figcaption><b>Figure 1.</b> The retry hint rides on the error
    response, not a separate call.</figcaption>
</figure>
```

Use `-.->` for the exceptional path, so the happy path stays the visual spine.
Subgraphs group by ownership: `subgraph edge["Edge tier"] ... end`.

### 2. Sequence

For anything where *order* is the point: handshakes, retries, races, lock
acquisition. Use `Note over` for the invariant that holds at a moment.

```html
<div class="mermaid">
sequenceDiagram
  autonumber
  participant W as Worker
  participant B as Broker
  W->>B: lease(job=88, ttl=30s)
  B-->>W: granted until t+30s
  Note over W,B: Only one worker holds a lease
  W--xB: crash
  B->>B: lease expires at t+30s
</div>
```

### 3. State machine

For lifecycles and status fields. Cheaper to read than the enum plus its
transition table.

```html
<div class="mermaid">
stateDiagram-v2
  [*] --> Pending
  Pending --> Running: claim()
  Running --> Done: ack()
  Running --> Pending: lease expires
  Running --> Dead: attempts > 5
  Dead --> [*]
</div>
```

### 4. Before / after

Two diagrams of the same family, side by side, in one figure. The reader's eye
does the diffing. Keep node names identical across the pair so the delta
stands out.

```html
<figure>
  <div class="side-by-side">
    <div>
      <p class="small"><b>Before</b></p>
      <div class="mermaid">flowchart TD
  A --> B --> C</div>
    </div>
    <div>
      <p class="small"><b>After</b></p>
      <div class="mermaid">flowchart TD
  A --> B
  A --> C</div>
    </div>
  </div>
  <figcaption><b>Figure 2.</b> C no longer waits on B.</figcaption>
</figure>
```

### 5. Simplified UI

For interface changes, and better than a screenshot. It stays legible in both
themes, costs nothing to keep current, and shows only what changed.

```html
<div class="ui-mock">
  <div class="chrome"><i></i><i></i><i></i> Settings &rsaquo; Alerts</div>
  <div class="body">
    <div class="ui-row">
      <span>Email digest</span><span class="ui-pill">Daily</span>
    </div>
    <div class="ui-row">
      <span>Mentions</span><span class="ui-pill new">Instant &larr; new</span>
    </div>
  </div>
</div>
```

### 6. Hand-authored SVG

For layered architectures, timelines, and memory layouts — anything Mermaid
lays out badly. Use the template's utility classes (`.fill-accent`,
`.stroke-border`, `svg text.dim`) so the figure re-themes for free. **Never
hardcode a hex color in an SVG.**

```html
<figure>
  <svg viewBox="0 0 420 90" role="img" aria-label="Three-stage pipeline">
    <rect class="fill-surface stroke-border"
          x="8" y="20" width="110" height="46" rx="6"/>
    <rect class="fill-surface stroke-border"
          x="155" y="20" width="110" height="46" rx="6"/>
    <rect class="fill-surface stroke-border"
          x="302" y="20" width="110" height="46" rx="6"/>
    <text x="63" y="48" text-anchor="middle">parse</text>
    <text x="210" y="48" text-anchor="middle">plan</text>
    <text x="357" y="48" text-anchor="middle">execute</text>
    <text x="136" y="48" text-anchor="middle" class="dim">&rarr;</text>
    <text x="283" y="48" text-anchor="middle" class="dim">&rarr;</text>
  </svg>
  <figcaption><b>Figure 3.</b> Planning moved out of parse, so a
    parse error now costs nothing.</figcaption>
</figure>
```

D3 follows the same rule: set `fill: var(--accent)` through a class, never
`.attr('fill', '#2f6feb')`. Reach for D3 only when the figure is data-bound or
needs layout math — force graphs, trees, custom scales. A static shape is
cheaper as handwritten SVG.

---

## Interactive elements

### 1. Before / after swap

The workhorse. One control flips every tagged block on the page between two
worlds: code, diagram, and prose all at once.

```html
<div class="seg" data-swap="impl">
  <button data-swap-to="before" aria-pressed="false">Before</button>
  <button data-swap-to="after" aria-pressed="true">After</button>
</div>

<div data-swap-group="impl" data-swap-case="before" hidden>old</div>
<div data-swap-group="impl" data-swap-case="after">new</div>
```

Any number of blocks can share a group, anywhere on the page.

### 2. Stepper

Walks one process a beat at a time. Pair it with a diagram: each step
highlights a different node, so the reader watches the data move.

```html
<div data-stepper>
  <div class="stepper">
    <button class="icon-btn" data-step="prev">&larr;</button>
    <span class="small" data-step-label></span>
    <div class="dots"></div>
    <button class="icon-btn" data-step="next">&rarr;</button>
  </div>
  <div class="step"><p>The worker claims a lease.</p></div>
  <div class="step"><p>The broker records the holder.</p></div>
</div>
```

Leave `.dots` empty. The script fills it with one marker per step.

### 3. Annotated code with markers

Numbered badges in a gutter, cross-linked to notes below. Hovering either end
lights both. Better than line numbers, which force the reader to count.

```html
<pre><code><span class="ln"><span class="mk" data-mk="1">1</span></span>if ok {
<span class="ln"></span>    return retry(req)
<span class="ln"><span class="mk" data-mk="2">2</span></span>}
</code></pre>
<ol class="marker-notes">
  <li data-mk-note="1">The budget is checked before the attempt, not
    after the failure.</li>
  <li data-mk-note="2">Falling through here is the point: no budget,
    no retry.</li>
</ol>
```

Every line inside a marked `<pre>` needs an `.ln` gutter, including the
unmarked ones, or the columns drift. Never break a `<pre>` line to fit a
margin; the newline shows up on the page. Layer the `.k`/`.s`/`.f` coloring
spans on top once the gutters are in place.

### 4. Parameter sliders driving a chart

For anything with a knob: backoff curves, cache hit rates, budget ratios, batch
sizes. The reader discovers the shape of the tradeoff instead of being told it.

```html
<div class="controls">
  <label class="control">Base delay
    <input type="range" id="base" min="10" max="500" value="100" step="10">
    <output id="base-out">100</output>ms
  </label>
</div>
<figure>
  <div class="chart-box"><canvas id="backoff"></canvas></div>
  <figcaption><b>Figure 4.</b> Illustrative. The curve is computed
    here, not measured.</figcaption>
</figure>
<script>
  var chart = registerChart(new Chart(
    document.getElementById('backoff'),
    {
      type: 'line',
      data: {
        labels: [1, 2, 3, 4, 5, 6],
        datasets: [{ label: 'delay (ms)', data: [], tension: .3 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } }
      }
    }
  ));
  function recompute() {
    var base = +document.getElementById('base').value;
    document.getElementById('base-out').value = base;
    chart.data.datasets[0].data = chart.data.labels.map(function (n) {
      return base * Math.pow(2, n - 1);
    });
    chart.update();
  }
  document.getElementById('base').addEventListener('input', recompute);
  recompute();
</script>
```

`registerChart` is required. It keeps the chart in sync with the theme toggle,
and it resizes the chart when its tab is first opened.

### 5. Live input to output

A tiny pure function the reader can feed. Ideal for parsers, encoders, slug
generators, validators — anything where "just show me" beats a paragraph.

```html
<div class="controls">
  <label class="control">Input
    <input id="raw" value="Hello World!" size="24">
  </label>
  <span class="control">&rarr; <output id="slug"></output></span>
</div>
<script>
  var raw = document.getElementById('raw');
  function run() {
    document.getElementById('slug').textContent = raw.value
      .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }
  raw.addEventListener('input', run);
  run();
</script>
```

Reimplement the real logic in a few lines of JS. Say so in the caption, and
link the source. A demo that silently diverges from the code is worse than no
demo.

### 6. Collapsed beginner aside

Inline background an expert skips without scrolling past it.

```html
<details class="callout definition">
  <summary>What is a lease?</summary>
  <p>A lease is a lock that expires on its own.</p>
</details>
```

The Background tab carries the long form. These are the in-line reminders.

### 7. Glossary term

For a word the page uses forty times and defines once.

```html
<span class="term" title="A lock that expires if the holder dies.">lease</span>
```

### 8. Grouped change table

The map of the diff. Sort rows by idea, not by path.

```html
<table>
  <thead>
    <tr><th>File</th><th>Group</th><th>What changed</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><a class="src-link" href="...">broker/lease.go</a></td>
      <td>Expiry</td>
      <td>TTL moved server-side</td>
    </tr>
  </tbody>
</table>
```

### 9. Self-check

One question with a `<details>` reveal, at the end of a section. It turns
reading into recall, and it exposes the misunderstanding you were worried
about.

```html
<details class="callout concept">
  <summary>Check yourself: what if the worker's clock is fast?</summary>
  <p>Nothing happens. The broker owns expiry, so the worker's clock
    never enters the decision.</p>
</details>
```

### 10. Scrollytelling

A sticky diagram that advances as prose scrolls past it. Powerful for a long
pipeline, and expensive to get right. Use it once per page at most, and only
when a stepper is genuinely weaker. Drive it with `IntersectionObserver` on the
prose blocks, toggling a class on the pinned figure.

### 11. Filterable list

For a change touching thirty files. An input that filters table rows beats
thirty bullets. Keep it to an `input` plus a `rows.filter`. No library.

---

## Callouts

Six kinds. Do not put ordinary prose in a callout. A page of boxes has no
emphasis left.

| Class | Use for |
| --- | --- |
| `definition` | Introducing a term the reader will need again |
| `concept` | The load-bearing idea of a section |
| `intuition` | Analogy and framing: your reading, not a fact |
| `edge` | The case that breaks the simple story |
| `warning` | A footgun, a breaking change, a migration hazard |
| `reading` | Links out to source, docs, ADRs, proposals, issues |

```html
<div class="callout warning">
  <p class="co-title">Breaking change</p>
  <p>Clients pinned below v2.3 will retry forever.</p>
</div>
```

---

## Code presentation

- `<pre><code>` only. Hand-color with `.k .s .n .c .f .t .o .a`. No
  highlighting library for a handful of lines.
- Show the lines carrying the idea. Never paste a whole file. Elide with a
  `<span class="c">// ...</span>` line and link to the full source.
- Diffs use `<span class="add">` and `<span class="del">` per line. They are
  block elements and already carry the gutter bar.
- Above ten lines, add markers. Do not expect the reader to find the point.
- Every block gets a source link nearby: a permalink pinned to the sha, so it
  stays correct after the branch moves.

---

## Anti-patterns

- **ASCII diagrams.** Never, in any context.
- **A diagram of the file tree.** It reads as a list, so make it a list.
- **Six diagram families on one page.** Pick two or three and reuse them.
- **A slider with no question behind it.** Motion is not insight.
- **Unlabelled invented numbers.** Mock data is fine and useful. Presenting it
  as a measurement is not.
- **A wall of pasted diff.** If the page shows more code than prose, it is a
  diff viewer with extra steps.
- **Hardcoded colors in SVG, D3, or Chart.js.** They survive exactly one theme.
