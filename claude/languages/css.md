# CSS Standards

These apply to plain stylesheets, Svelte `<style>` blocks, and the custom CSS in a Tailwind project. See [With
Tailwind](#with-tailwind) for how the pieces map onto Tailwind's layers.

## Browser Support

- Target Baseline "widely available" for anything a page needs to work
- Newer features are fine as progressive enhancement when they degrade to a no-op
- Every line in the reset below follows that rule. An engine that lacks a property ignores it.

## Structure

Declare the layer order once, at the top of the entry stylesheet:

```css
@layer reset, tokens, base, layouts, components, utilities;
```

- `reset`: the reset below. Element selectors only.
- `tokens`: custom properties on `:root`. No selectors beyond `:root` and its theme variants.
- `base`: element defaults such as `body` colors, links, focus rings, and prose.
- `layouts`: layout primitives that know nothing about content (content grid, sidebar, stack).
- `components`: one block per component.
- `utilities`: single-purpose classes. The only layer allowed `!important` for normal styling.

Later layers win regardless of specificity, so a selector never needs to out-score another layer. Unlayered styles beat
every layer. Keep nothing unlayered except third-party CSS you cannot wrap.

## Selectors and Naming

- Style with classes. Never style an ID.
- Class names are kebab-case. Name the component, then the part: `.card`, `.card-title`, `.card-actions`.
- Express state with the attribute that already carries it: `[aria-expanded="true"]`, `[aria-current="page"]`,
  `:disabled`. Use `[data-state]` when no ARIA attribute fits. Do not add `.is-open` classes.
- Use native nesting for states, pseudo-elements, and media or container queries inside a component
- Do not nest more than two levels. Do not nest to build class names.
- Wrap shared defaults in `:where()` so they carry zero specificity and any component can override them
- Comments go before the property or rule they explain, as in the Go and Proto standards. Say why, not what.

## Units

- `rem` for type and space, through the tokens below
- `em` for padding that should track the element's own font size, such as a button
- `ch` for line length. Prose measure is `max-inline-size: 65ch`.
- `px` only for hairline borders and the 16px form-control floor
- `svh` for full-height layouts. Never `vh`, which ignores mobile browser toolbars.
- Unitless `line-height`

## Reset

Use this reset in every project. It goes in `@layer reset`.

```css
@layer reset {
  *,
  *::before,
  *::after {
    box-sizing: border-box;
    min-width: 0;
  }

  :root {
    interpolate-size: allow-keywords;
    scrollbar-gutter: stable;
    text-wrap: pretty;
    overflow-wrap: break-word;
    font-synthesis: none;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    -webkit-text-size-adjust: 100%;
    text-size-adjust: 100%;
    -webkit-tap-highlight-color: transparent;
  }

  body {
    margin: 0;
    min-height: 100svh;
  }

  h1, h2, h3, h4 { text-wrap: balance; }

  img, svg, video {
    display: block;
    max-width: 100%;
    height: auto;
  }

  input, button, textarea, select { font: inherit; }

  /* Must follow font: inherit, which would otherwise reset it. */
  input, textarea, select { font-size: max(16px, 1rem); }

  button, a, [role="button"] { touch-action: manipulation; }

  button, [role="button"] {
    user-select: none;
    -webkit-user-select: none;
  }

  @media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
}
```

Why each line is there:

- `min-width: 0` lets flex and grid items shrink below their content. Their default is `min-width: auto`, which is why a
  long word or a wide child overflows a grid.
- That cuts both ways. An icon or button in a flex row can now shrink too. Give those `flex-shrink: 0`.
- `interpolate-size: allow-keywords` turns on transitions to and from `auto`. An accordion that animates its height
  depends on it. Not every engine has it yet. Where it is missing, the accordion snaps open.
- `scrollbar-gutter: stable` reserves the scrollbar's space. The page does not shift sideways when a modal locks
  scrolling or when content grows past one screen.
- `text-wrap: pretty` spends more effort on line breaks. It avoids a last line that holds one short word. It inherits,
  so `:root` reaches every element.
- `overflow-wrap: break-word` breaks a word that cannot fit, such as a URL. It inherits too.
- `font-synthesis: none` stops the browser from faking a bold or italic that the font file lacks.
- The two smoothing rules render text thinner on macOS. It then matches the weight shown in design tools. Other systems
  ignore them.
- `text-size-adjust: 100%` stops iOS from inflating text in landscape.
- `-webkit-tap-highlight-color: transparent` removes the gray flash mobile browsers paint over a tapped element. The
  element must then show its own `:active` and `:focus-visible` states, or a tap gives no feedback.
- `min-height: 100svh` is the viewport height with the mobile toolbars showing, so the page never sits behind them.
  `100dvh` changes as the toolbar moves and re-lays out the page each time.
- `text-wrap: balance` gives headings lines of similar length.
- Block media with `max-width: 100%` never overflows its container and never leaves a gap below for the text descender.
- Form controls do not inherit the page font by default. `font: inherit` fixes that.
- Inputs at 16px or more stop iOS Safari from zooming the page on focus. It does not zoom back out.
- `touch-action: manipulation` turns off double-tap zoom on controls. Browsers already skip the tap delay on pages with
  a `width=device-width` viewport. Keep the rule as insurance for pages that lack one.
- `user-select: none` on controls stops a long press from selecting a button's label
- The reduced-motion block shortens every animation and transition to near zero. `!important` in the first layer beats
  normal declarations in every later layer, so components cannot override it by accident.

## Logical Properties

Write sides as start and end, not left and right. The layout then follows the writing direction for free.

```css
.card {
  position: relative;
  padding-inline: 1.5rem;
  margin-block-end: 2rem;
  border-inline-start: 4px solid;
  text-align: start;
}

.card .close {
  position: absolute;
  inset-block-start: 1rem;
  inset-inline-end: 1rem;
}
```

- Use logical forms for margin, padding, border, inset, `text-align`, and float
- Use `inline-size` and `max-inline-size` for widths that are really a measure of text
- `transform`, `box-shadow` offsets, and `background-position` have no logical forms. Flip them under `:dir(rtl)` when
  the direction matters.
- Use physical properties when the intent is physical, such as a light source that casts a shadow down and right

## Color

Write every color in OKLCH. The three channels are lightness, chroma, and hue.

- Lightness is perceptual. Two colors with the same L look equally light whatever their hue. Scales and contrast become
  predictable.
- Mixing in OKLCH keeps the hue of the base color. Mixing in sRGB drifts toward gray.
- One base value drives the whole family. Change the base and the hover and subtle versions follow.
- High chroma can fall outside sRGB. The browser then maps it back and the color shifts. Keep chroma at or below about
  0.15 at mid lightness unless you have checked the hue.
- Derive variants with `color-mix(in oklch, ...)` or relative color syntax: `oklch(from var(--x) l c h)`.
  Never hand-pick a second hex value for a hover state.

## Color Tokens and Schemes

Components use semantic tokens only. They never use a raw color or a primitive.

```css
@layer tokens {
  :root {
    color-scheme: light dark;

    /* The one raw value the accent family derives from. */
    --accent-base: oklch(0.55 0.15 255);

    --color-bg: light-dark(oklch(0.99 0.005 255), oklch(0.18 0.01 255));
    --color-surface: light-dark(oklch(0.96 0.01 255), oklch(0.23 0.015 255));
    --color-text: light-dark(oklch(0.22 0.02 255), oklch(0.93 0.01 255));
    --color-text-muted: light-dark(oklch(0.45 0.02 255), oklch(0.72 0.02 255));
    --color-border: light-dark(oklch(0.88 0.01 255), oklch(0.32 0.015 255));
    --color-accent: light-dark(var(--accent-base), oklch(from var(--accent-base) 0.72 c h));

    /* Moves toward the text color: darker in light mode, lighter in dark mode. */
    --color-accent-hover: color-mix(in oklch, var(--color-accent), var(--color-text) 15%);
    --color-accent-subtle: color-mix(in oklch, var(--color-accent) 15%, var(--color-bg));
  }

  :root[data-theme="light"] { color-scheme: light; }
  :root[data-theme="dark"] { color-scheme: dark; }
}
```

- `color-scheme` picks the branch of every `light-dark()`. It also themes scrollbars and form controls.
- The default follows the OS. A `data-theme` attribute on `:root` lets the user override it.
- Name tokens by role (`--color-text-muted`), never by appearance (`--gray-600`)
- Each scheme gets its own lightness values. Do not invert one scheme to get the other.
- Check contrast in both schemes. Body text needs 4.5:1. Large text and UI boundaries need 3:1.
- `body` sets `background` and `color` from the tokens explicitly in `base`

## Fluid Sizes with `clamp()`

`clamp(min, preferred, max)` draws a straight line between two points and holds it flat past either end.

To grow from 1rem at a 20rem viewport to 1.5rem at a 77.5rem viewport:

- Slope: `(1.5 - 1) / (77.5 - 20)` is 0.008696. Times 100 gives `0.8696vw`.
- Intercept: `1 - 20 × 0.008696` is `0.8261rem`
- Result: `clamp(1rem, 0.8261rem + 0.8696vw, 1.5rem)`

Rules:

- Write both bounds in `rem`
- The preferred value must contain a `rem` term. Pure `vw` does not grow when the user zooms, which fails WCAG 1.4.4.
- Keep the max no more than 2.5 times the min for text. Zoom to 200% then still doubles the size at every width.
- Prefer the fluid scale below to hand-written `clamp()` calls. Write one by hand only for a one-off.

## Fluid Type and Space Scale

One set of tokens drives every font size and every gap. It is the `clamp()` line above, generalized.

```css
@layer tokens {
  :root {
    /* Widths and sizes in rem, as plain numbers. 20 is 320px. 77.5 is 1240px. */
    --narrow-width: 20;
    --wide-width: 77.5;
    /* Body text: 18px at the narrow width, 20px at the wide one. */
    --narrow-size: 1.125;
    --wide-size: 1.25;
    /* Each heading step is this many times the last. */
    --narrow-ratio: 1.2;
    --wide-ratio: 1.25;

    /* 0 at the narrow width, 1rem at the wide width, a straight line between. */
    --fluid: clamp(
      0rem,
      (100vw - var(--narrow-width) * 1rem) / (var(--wide-width) - var(--narrow-width)),
      1rem
    );
    --at-narrow: calc(var(--narrow-size) * (1rem - var(--fluid)));
    --at-wide: calc(var(--wide-size) * var(--fluid));

    --step--1: calc(
      var(--at-narrow) * pow(var(--narrow-ratio), -1) + var(--at-wide) * pow(var(--wide-ratio), -1)
    );
    --step-0: calc(var(--at-narrow) + var(--at-wide));
    --step-1: calc(
      var(--at-narrow) * pow(var(--narrow-ratio), 1) + var(--at-wide) * pow(var(--wide-ratio), 1)
    );
    --step-2: calc(
      var(--at-narrow) * pow(var(--narrow-ratio), 2) + var(--at-wide) * pow(var(--wide-ratio), 2)
    );
    --step-3: calc(
      var(--at-narrow) * pow(var(--narrow-ratio), 3) + var(--at-wide) * pow(var(--wide-ratio), 3)
    );
    --step-4: calc(
      var(--at-narrow) * pow(var(--narrow-ratio), 4) + var(--at-wide) * pow(var(--wide-ratio), 4)
    );

    --space-3xs: calc(var(--step-0) * 0.25);
    --space-2xs: calc(var(--step-0) * 0.5);
    --space-xs: calc(var(--step-0) * 0.75);
    --space-s: var(--step-0);
    --space-m: calc(var(--step-0) * 1.5);
    --space-l: calc(var(--step-0) * 2);
    --space-xl: calc(var(--step-0) * 3);
    --space-2xl: calc(var(--step-0) * 4);

    /* Small on the phone, large on the desktop: 18px to 40px. */
    --space-s-l: calc(var(--at-narrow) * 1 + var(--at-wide) * 2);
  }
}
```

- The first six properties are the whole design decision. Change only those to retune the scale.
- `--fluid` holds the only `clamp()`. That one bounds every token.
- `--at-narrow` and `--at-wide` are the two base sizes, each weighted by how close the viewport is to its width. Their
  sum is step 0.
- `pow()` raises each ratio to the step number. A step is the narrow scale's size times one weight plus the wide
  scale's size times the other. That is the line from the previous section, drawn between two points.
- Step 1 runs from 21.6px to 25px. Step 4 runs from 37.3px to 48.8px.
- The weights stay lengths. Dividing a length by a length to get a plain number is not yet supported everywhere.
- Every result is a multiple of `rem`, so the whole scale grows when the user zooms
- A space token is a multiple of step 0, so it grows as much as body text does
- A pair such as `--space-s-l` gives the two terms different multipliers. Use pairs for page gutters and section gaps
  that should open up on a wide screen.
- Use these tokens for every `font-size`, `gap`, `padding`, and `margin`. A raw `rem` value outside the tokens layer
  needs a reason.

## Layout

Reach for these patterns before writing media queries.

### Content grid with breakouts

Prose sits in a readable column. Any child can break out to a wider column or to the full width.

```css
.content-grid {
  --gutter: var(--space-s-l);
  --content: min(65ch, 100% - var(--gutter) * 2);
  --breakout: minmax(0, 8rem);

  display: grid;
  grid-template-columns:
    [full-start] minmax(var(--gutter), 1fr)
    [breakout-start] var(--breakout)
    [content-start] var(--content) [content-end]
    var(--breakout) [breakout-end]
    minmax(var(--gutter), 1fr) [full-end];
}

.content-grid > * { grid-column: content; }
.content-grid > .breakout { grid-column: breakout; }
.content-grid > .full { grid-column: full; }
```

A full-width child that is itself a `.content-grid` keeps its own contents aligned with the page column.

### Intrinsic grid

As many columns as fit, with no breakpoints.

```css
.auto-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
  gap: var(--space-m);
}
```

The `min(100%, ...)` stops a single column from overflowing a container narrower than 16rem.

### Subgrid rows

Cards in a row line up their titles, bodies, and footers, whatever each one's content.

```css
.card {
  display: grid;
  grid-row: span 3;
  grid-template-rows: subgrid;
}
```

The card's parent is the grid. The card takes three of its rows and lays its own children into them.

### Sidebar

A sidebar beside the main content that drops below it when the main content would get too narrow.

```css
.with-sidebar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-m);
}

.with-sidebar > :first-child {
  flex-basis: 16rem;
  flex-grow: 1;
}

/* Wraps once it would fall under half the width. */
.with-sidebar > :last-child {
  flex-basis: 0;
  flex-grow: 999;
  min-inline-size: 50%;
}
```

### Container queries and container units

A component adapts to the space it is given, not to the viewport.

```css
.card-slot { container-type: inline-size; }

.card {
  & h3 { font-size: clamp(var(--step-0), 0.5rem + 4cqi, var(--step-2)); }

  @container (inline-size >= 30rem) {
    grid-template-columns: 10rem 1fr;
  }
}
```

- Use container queries for components. Keep media queries for page-level layout and user preferences.
- `container-type: inline-size` makes the element's width ignore its contents. Put it on a wrapper whose width comes
  from its parent, never on a shrink-to-fit element.
- `cqi` is 1% of the container's inline size. Use it inside `clamp()` with a `rem` term, as with `vw`.
- Write media and container queries in range syntax: `(width >= 48rem)`

### Stacked layers with grid

Overlap children without absolute positioning.

```css
.layers { display: grid; }
.layers > * { grid-area: 1 / 1; }
```

The container sizes to its tallest layer. Absolute positioning would take the layers out of flow and collapse it.

### Safe alignment

```css
.dialog-body {
  display: flex;
  flex-direction: column;
  justify-content: safe center;
}
```

`safe` centers when the content fits. When it overflows, it falls back to `start`. Plain `center` pushes the overflow
off both ends, and the part above the top cannot be scrolled to.

### Overflow: clip over hidden

- Use `overflow: clip` to cut off content that spills out
- `overflow: hidden` makes the element a scroll container. A `position: sticky` descendant then sticks to it instead of
  the page. Script and focus can still scroll it.
- Use `hidden` only when you want a scroll container with no scrollbar
- `overflow-clip-margin` lets a shadow or focus ring extend past a clipped edge

## Accessibility

- Never remove a focus outline without replacing it. Style `:focus-visible`, not `:focus`.
- Hide content visually with a `.visually-hidden` utility, not `display: none`, when a screen reader should still reach
  it
- Respect `prefers-reduced-motion` (the reset does) and `prefers-color-scheme` (the tokens do)
- Check the page under `@media (forced-colors: active)`. Borders that carry meaning must not be drawn with a background
  color alone.

## With Tailwind

Tailwind v4 has its own layers: `theme`, `base`, `components`, `utilities`. Map onto them instead of declaring the
order above.

- Preflight already covers `box-sizing`, `margin: 0`, block media, `font: inherit` on controls, text-size adjust, and
  the tap highlight. Add the rest of the reset in `@layer base`.
- Put color and scale tokens in `@theme` under Tailwind's namespaces (`--color-*`, `--text-*`, `--spacing-*`). The
  utilities then use them. Keep `--fluid`, `--at-narrow`, and `--at-wide` as plain `:root` properties.
- Layout primitives go in `@layer components`
- Reach for a utility first. Write a component class when the same utility list appears three times.

## Tooling

- Format with the project's formatter: Biome for plain TypeScript projects, Prettier for Svelte
- Lint with Stylelint and `stylelint-config-standard` when a project has more than a few hand-written stylesheets
- Enable `stylelint-use-logical` to catch physical properties
