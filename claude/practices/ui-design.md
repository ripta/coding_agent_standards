# UI Design Practices

These apply to any interface a person looks at: web pages, native apps, and game menus and HUDs. Platform docs add
what one platform needs on top of this one:

- `practices/ui-web.md` for HTML pages and web apps. `languages/css.md` holds the CSS mechanics.
- `practices/ui-macos.md` for SwiftUI and AppKit apps on macOS
- `practices/ui-game.md` for games, whatever the renderer
- `practices/terminal-ui.md` for CLI output and TUIs. It stands alone, since CLI profiles do not import this file.

## Baseline

- The accessibility baseline is WCAG 2.2 level AA. A project or a contract may raise it. Nothing here lowers it.
- Accessibility is part of correctness, not polish. A control a keyboard cannot reach is a bug, the same as a control
  that crashes.
- When a platform's own guidelines are stricter than WCAG, such as Apple's Human Interface Guidelines on target size,
  follow the platform.

## Hierarchy and Layout

- Each screen has one primary action. Give it the most visual weight. Secondary actions get less, and destructive
  actions never look primary.
- Build hierarchy from size, weight, and spacing first. Color comes last, and is never the only signal.
- Group related things by proximity. Space between groups is larger than space within a group.
- Align to a shared grid or set of edges. Every extra alignment line is something the eye has to resolve.
- Keep the reading order and the visual order the same. Assistive tech and keyboard focus follow the reading order.
- Content reflows to a narrow width without horizontal scrolling. Tables, code, and diagrams may scroll inside their
  own container.

## Density

- Match density to the task. A tool people use all day can be dense. A flow someone sees once should be sparse.
- Dense is not cramped. Keep spacing consistent, and keep the type scale legible at the dense setting.
- Show the information a decision needs on the screen that asks for the decision. Do not send the user elsewhere to
  look it up.
- Progressive disclosure hides detail until it is asked for. It never hides what most users need on most visits.

## Typography

- Body text runs 45 to 75 characters per line. `languages/css.md` sets prose to `65ch`.
- Body line height is about 1.5. Headings run tighter, about 1.1 to 1.3.
- Size text in the platform's scalable units, so the user's text size and zoom settings apply. Text must survive a
  200% increase without clipping or overlap.
- Use at most two typefaces. One is usually enough. Use the platform's system font unless the product has a reason.
- Weight and size carry hierarchy. Do not set body text in all caps, and do not use italic for long passages.
- Text never sits on a busy image without a backing that holds contrast.

### Numbers

- Right-align numbers in columns. Use tabular figures wherever digits line up or change in place, such as counters,
  timers, and tables.
- Keep the same precision down a column. Do not mix `1.5` and `1.50`.
- Format numbers, dates, and currencies for the user's locale with the platform's formatter, never by hand.
- Always show a unit. Put it in the column header when every row shares it.
- Show a relative time, such as "3 minutes ago", with the absolute time available on hover or focus.

## Color and Contrast

- Body text needs 4.5:1 contrast against its background. Large text, icons that carry meaning, and control boundaries
  need 3:1. Check both light and dark schemes.
- Never use color alone to carry meaning. Pair it with text, an icon, a pattern, or position. Red and green are the
  pair color-blind users most often cannot tell apart.
- Name colors by role, such as text, muted text, surface, accent, danger. The platform docs say how.
- Disabled controls may fall below 3:1, but the reason they are disabled must still be discoverable.

## Controls and Affordances

- A control looks like what it does. Something clickable looks clickable at rest, not only on hover. Touch screens
  have no hover.
- Use the platform's standard controls before building custom ones. A standard control brings keyboard, focus, and
  assistive-tech support for free.
- Label actions with a verb that names the result: "Delete project", not "OK". Icon-only buttons need an accessible
  name and a visible tooltip.
- Every control shows its states: rest, hover where there is a pointer, focus, pressed, disabled, and selected or
  checked where they apply.
- Targets are at least 24 by 24 CSS pixels, or have enough spacing that a 24-pixel circle around each does not
  overlap a neighbor. Primary touch targets should reach 44 by 44.
- Guard destructive actions. Prefer undo over a confirmation dialog. When an action cannot be undone, the confirmation
  names what will be lost, and its button repeats the verb.

## Forms

- Every field has a visible label. A placeholder is not a label: it disappears on input and usually fails contrast.
- Put the label above the field, or beside it for short forms with short labels.
- Mark the optional fields, or the required ones, whichever is fewer. Say which convention the form uses.
- Ask only for what the task needs. Every field costs completion.
- Use the field type and autocomplete hints the platform offers, such as email, phone, and one-time code.
- Validate when the user leaves a field or submits, not on every keystroke. Do not report an error on a field the user
  has not finished.
- An error message sits next to its field. It says what is wrong and what to do: "Enter a date after today", not
  "Invalid input".
- On a failed submit, keep everything the user entered. Move focus to the first error, or to a summary that links to
  each one.
- Do not make the user retype or transcribe a value to authenticate. Allow paste and password managers.

## States

Every view that shows data has more than one state. Design each one before calling the view done.

- **Empty:** say why it is empty, and offer the action that fills it. A first-use empty state differs from a "no
  results" empty state. Both differ from "you have deleted everything".
- **Loading:** respond within 100 ms, even if only by marking the control pressed. Past about one second, show
  progress. Use a determinate bar when the total is known. A skeleton that matches the final layout beats a spinner.
- **Error:** say what failed, why if known, and what the user can do. Offer retry when retry can work. Keep any data
  that did load visible.
- **Partial:** some items load and some fail, or the result is truncated. Say so, and say how many.
- **Success:** confirm actions whose result is not visible. Do not interrupt for actions whose result is.
- **Stale:** when data may be out of date, show when it was last updated.

Layout does not jump when a state changes. Reserve space for content that arrives late.

## Feedback and Motion

- Every action gets feedback where the user is looking. A status change far from the control goes unseen.
- Transient messages, such as toasts, stay long enough to read and can be dismissed. Anything the user must act on
  stays until they act.
- Motion explains a change: where something came from or went. Keep transitions short, around 150 to 300 ms.
- Honor the platform's reduced-motion setting. Replace movement with a fade or an instant change. Do not remove the
  feedback.
- Nothing flashes more than three times a second.
- Do not auto-advance or auto-dismiss content the user may still be reading, unless they can pause or extend it.

## Keyboard and Focus

- Every action works from the keyboard. Test by putting the pointer away.
- Focus is always visible, and never fully hidden behind a sticky header, footer, or overlay.
- Focus order follows the reading order.
- Opening a dialog or panel moves focus into it. Closing it returns focus to the control that opened it.
- A modal traps focus until it closes. Nothing else may trap focus. Escape closes a dialog or menu.
- Offer shortcuts for frequent actions, and make them discoverable in menus or tooltips. A single-key shortcut needs a
  way to turn it off or remap it.

## Assistive Technology

- Every control exposes a name, a role, and its current value or state. Standard controls do this already. A custom
  control must do it explicitly.
- Images that carry information get a text alternative that says what the image shows. Decorative images are hidden
  from assistive tech.
- Announce changes the user did not move focus to, such as a toast, a validation error, or a result count.
  Do not announce every small update.
- Group a composite element, such as a card, so a screen reader reads it as one item, not as each fragment.

## Writing

- Use the user's words, not the system's. "Couldn't save the file", not "Write failed: EACCES".
- Keep the same term for the same thing everywhere. A button labeled "Archive" leads to the "Archive", not to
  "Storage".
- Use sentence case for labels and headings, unless the platform's convention is title case. Pick one per product.
- Lead with the point. Put the detail after it, or behind a link.

## Checking a UI

Check a change in the running app before reporting it done. See "Running the App by Hand" in `practices/testing.md`.

1. Walk through every state above, including empty, error, and the longest realistic content
2. Use it with the keyboard alone
3. Check the light and dark schemes, and the platform's increased-contrast setting where there is one
4. Raise the text size to 200%, and narrow the window to the smallest supported width
5. Turn on reduced motion
6. Run the platform's automated accessibility check. It catches only part of the problems, so it does not replace the
   steps above
7. For a new screen or a custom control, use it with the platform's screen reader
