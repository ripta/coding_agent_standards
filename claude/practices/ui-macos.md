# macOS UI Practices

These add the macOS specifics to `practices/ui-design.md`, for SwiftUI apps and the AppKit they bridge to. SwiftUI
code structure lives in `languages/swift.md`. Where this file and Apple's Human Interface Guidelines disagree, follow
the guidelines.

## Platform Conventions

- A Mac app is driven by its menu bar. Every command is in a menu, with a keyboard shortcut for the frequent ones.
  Toolbar buttons and context menus are shortcuts to menu commands, not the only route.
- Declare commands with `.commands { CommandMenu(...) }` and `CommandGroup`, and shortcuts with `.keyboardShortcut`.
  Do not reassign the standard shortcuts, such as Command-Q, Command-W, Command-Z, and Command-comma.
- Put preferences in a `Settings` scene. It provides the Settings menu item and Command-comma.
- Support multiple windows when documents or items are independent. Windows restore their size, position, and state
  on relaunch.
- Selection-based UI follows the platform: Command-click and Shift-click extend a selection, and Delete acts on it.
- Prefer undo to confirmation. Register undo with the `UndoManager` from `\.undoManager`. It is `nil` where the
  context does not support undo.
- Use system controls and SF Symbols before custom ones. They follow accent color, vibrancy, and accessibility
  settings without extra work.

## Text and Color

- Use semantic text styles such as `.body`, `.headline`, and `.caption`. Do not set fixed point sizes.
- Use semantic colors such as `.primary`, `.secondary`, and the system colors. They adapt to light and dark mode,
  accent color, and Increase Contrast.
- Define custom colors in the asset catalog with light, dark, and high-contrast variants. Do not branch on
  `colorScheme` in view code to pick colors.
- Read `\.colorSchemeContrast` when a custom drawing must thicken lines or remove translucency under Increase Contrast.
  Read `\.accessibilityReduceTransparency` for the same reason.

## Keyboard and Focus

- The app works with Keyboard navigation turned on in System Settings > Keyboard. Tab reaches every control.
  A custom view needs `.focusable()` before Tab reaches it.
- Manage focus with `@FocusState` and `.focused`. Set the initial focus of a sheet or window to its first field.
- Custom controls that act on keys use `.focusable()` and `.onKeyPress`
- The default button of a sheet takes `.keyboardShortcut(.defaultAction)`. Cancel takes `.cancelAction`.

## Accessibility

- Give icon-only buttons a title, as in `Button("Delete", systemImage: "trash")` with `.labelStyle(.iconOnly)`.
  VoiceOver reads the title. Otherwise add `.accessibilityLabel`. Do not rely on the symbol name.
- Combine a row's parts into one element with `.accessibilityElement(children: .combine)`. Hide decoration with
  `.accessibilityHidden(true)`.
- Expose a custom control's value with `.accessibilityValue`, and its actions with `.accessibilityAction`
- Read `\.accessibilityReduceMotion`, and replace movement with a fade or an instant change when it is set
- Post an announcement for a change that happens away from focus, such as a finished background task. Use
  `AccessibilityNotification.Announcement("...").post()`, which needs macOS 14 or later.

## Checking an App

These are the macOS versions of the steps in "Checking a UI" in `practices/ui-design.md`:

- Inspect each new screen with Accessibility Inspector, and run its audit
- Call `try XCUIApplication().performAccessibilityAudit()` in a UI test for each main screen. It throws when the
  audit finds an issue, and needs Xcode 15 and macOS 14 or later. Pass an issue handler that returns `true` only to
  ignore a known issue.
- Use each new screen with VoiceOver, toggled with Command-F5, or by holding Command and pressing Touch ID three times
- Check under Increase Contrast, Reduce Transparency, Reduce Motion, and both appearances. On macOS 26, Liquid Glass
  changes under the first two, so check custom glass effects there too.
