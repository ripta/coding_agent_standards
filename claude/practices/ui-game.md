# Game UI Practices

These add the game specifics to `practices/ui-design.md`. They cover HUDs, menus, and in-game text, whatever the
renderer. A game draws to a canvas, so the platform gives it none of the accessibility a standard control has. The
game has to build it.

## Settings Are Not Simulation State

- Accessibility and display settings change how the game renders and reads input. They never change the simulation.
  See "Simulation and Render Split" in `practices/game-simulation.md`.
- A difficulty or assist option that does change the simulation, such as slower game speed, is a game rule. Record it
  in the replay and the save, like any other input.
- Settings persist per player, apart from save files. Open them from the title screen and from pause.

## HUD and Text

- Size text relative to the viewport height, not in fixed pixels. Check it at the smallest supported resolution and
  on a TV at couch distance.
- Offer a text-size setting that covers HUD, menus, and subtitles
- Text over a moving scene needs a backing plate, or an outline or shadow strong enough to hold 4.5:1 against any
  frame. Test it over the brightest and the busiest scenes.
- Render text at the device pixel ratio, so it stays sharp on high-density screens
- Keep HUD elements inside a safe area inset from the screen edges. TVs and notched phones crop the edge.
- Put the information a player needs in the moment near where they are looking. Push the rest to the edges or to a
  pause screen.
- The HUD does not change layout while the player is acting. Numbers that tick use tabular figures.

## Signals

- Never signal with color alone. Pair team, rarity, and danger colors with a shape, an icon, or a pattern.
- Offer color-blind presets, or let the player pick the key colors
- Every important sound has a visual cue, such as a damage-direction indicator or an on-screen marker
- Subtitles and captions are on by default or offered at first launch. Name the speaker, and caption important
  non-speech sounds.
- Haptics and rumble reinforce a signal. They never carry one alone.

## Motion and Flashing

- Offer separate toggles or sliders for screen shake, camera bob, motion blur, and flashing effects
- Nothing flashes more than three times a second. A full-screen flash counts.
- Read the platform's reduced-motion setting as the initial value of the motion settings

## Input

- Every action is remappable, on keyboard and on controller
- Offer a toggle for every hold action, and an alternative to rapid button mashing
- Menus work with keyboard, controller, and pointer. Focus is always visible, and starts on a sensible default.
- Prompts show the glyphs of the device the player last used
- The game pauses anywhere, and pauses itself when the window loses focus or a controller disconnects

## Menus and Screen Readers

- A screen reader cannot see into a canvas. Build menus, settings, and dialogs as DOM elements over the canvas, so the
  rules in `practices/ui-web.md` apply to them.
- When the menus must live in the canvas, mirror each focused item into a visually hidden live region. That gives
  screen readers its name and state.
- Narrate key game state on request, such as health and objective, when the game supports a screen-reader mode
