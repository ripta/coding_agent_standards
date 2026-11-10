# Web UI Practices

These add the web specifics to `practices/ui-design.md`. CSS mechanics, such as the reset, color tokens, the fluid
type scale, and `:focus-visible`, live in `languages/css.md`.

## Semantic HTML

- Use the element that means the thing. A `<button>` performs an action. An `<a href>` goes somewhere. Never put a
  click handler on a `<div>` or `<span>`.
- Set `lang` on `<html>`, and on any passage in another language
- Give every page a unique, descriptive `<title>`. In a single-page app, update it on every route change.
- Use landmarks: one `<main>`, plus `<header>`, `<nav>`, `<footer>`, and `<aside>` where they apply. Give two
  landmarks of the same kind distinct `aria-label`s.
- Headings form an outline. One `<h1>` per page, and no skipped levels. Pick the level by structure, then style it.
- Use `<ul>` and `<ol>` for lists, and `<table>` with `<th scope>` and a `<caption>` for tabular data. Never use a
  table for layout.
- Use `<dialog>` with `showModal()` for modals. It makes the rest of the page inert, closes on Escape, and returns
  focus to the opener when it closes. Tab does not wrap inside it: focus moves on to the browser's own controls, which
  is the intended platform behavior. Do not add a scripted focus trap to a native dialog.
- Use `<details>` and `<summary>` for a simple disclosure before building one

## ARIA

- Do not use ARIA when a native element or attribute does the job. A wrong ARIA attribute is worse than none.
- When a custom widget is unavoidable, follow its pattern in the WAI-ARIA Authoring Practices Guide, including the
  keyboard behavior. A `role` alone does not add the behavior it promises.
- `aria-label` replaces the visible name. Prefer `aria-labelledby` pointing at visible text, so both stay the same.
  When `aria-label` is unavoidable, it contains the visible label text, ideally at the start.
- Keep state attributes such as `aria-expanded`, `aria-selected`, and `aria-current` in sync with the UI. CSS styles
  state from them. See "Selectors and Naming" in `languages/css.md`.
- Hide decoration with `aria-hidden="true"`. Never put it on something focusable.

## Forms

- Tie every input to a `<label for>`. Group radios and related checkboxes in a `<fieldset>` with a `<legend>`.
- Link hints and errors to their input with `aria-describedby`. Mark an invalid field with `aria-invalid="true"`.
- Use the matching `type` and `autocomplete` value, such as `type="email"`, `autocomplete="one-time-code"`, and
  `inputmode="numeric"` for digits that are not a number
- Let the browser submit the form, so Enter works. Handle `submit` on the `<form>`, not `click` on the button.

## Images and Media

- Every `<img>` has `alt`. Decorative images get `alt=""`. An icon inside a labeled button is decorative.
- An inline `<svg>` that carries meaning gets `role="img"` and a `<title>`, or an `aria-label`
- Video has captions. Audio-only content has a transcript.
- Nothing plays sound automatically. Autoplaying video starts muted and has a visible pause control.

## Dynamic Content

- Announce async results with a live region that already exists in the DOM before its text changes.
  `role="status"` is polite. `role="alert"` interrupts, so keep it for errors that block the user.
- On a client-side route change, move focus to the new page's `<h1>` or `<main>`, and update the `<title>`
- Add a skip link to `<main>` as the first focusable element on pages with repeated navigation
- Mark a region that is loading with `aria-busy="true"`, and clear it when the content arrives

## Responsive Layout

- The page works at a 320 CSS pixel width with no horizontal page scroll. Test at that width and at 200% zoom.
- Never disable zoom. Do not set `maximum-scale` or `user-scalable=no` in the viewport meta.
- Users may override text spacing: line height, paragraph spacing, letter spacing, word spacing. Do not give text
  containers fixed heights that clip when spacing grows.
- Pointer and hover are not universal. Check `@media (hover: hover)` before relying on hover, and size targets for
  `(pointer: coarse)`.

## Svelte

- Treat the Svelte compiler's a11y warnings as errors. Run `svelte-check --fail-on-warnings` in CI.
- Do not silence an a11y warning with `svelte-ignore` unless the comment says why the rule does not apply, as in
  `<!-- svelte-ignore a11y_autofocus (reason) -->`

## Checking a Page

These are the web versions of the steps in "Checking a UI" in `practices/ui-design.md`:

- Run axe, or Lighthouse's accessibility audit, against every page and every state. In tests, `@axe-core/playwright`
  runs axe from Playwright.
- Tab through the page, then use it with VoiceOver on macOS or NVDA on Windows
- Emulate `prefers-reduced-motion`, `prefers-color-scheme`, and `forced-colors` in the browser's dev tools
- Check the page in a real browser. See "Checking a Rendered Page" in `practices/diagrams.md`.
