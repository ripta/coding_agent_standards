# Swift Standards

## Project Structure (macOS App)

```
Sources/
  <AppName>/
    App.swift                # @main entry point
    ContentView.swift        # Root view
    Views/                   # SwiftUI views, grouped by feature
    Models/                  # Data models and state
    Services/                # Business logic, API clients, system integration
    Extensions/              # Type extensions
    Resources/               # Assets, localization
Tests/
  <AppName>Tests/            # Unit tests
  <AppName>UITests/          # UI tests
Package.swift                # SPM manifest (if using SPM structure)
Makefile                     # Build targets wrapping xcodebuild / swift build
```

## Naming

- Types: PascalCase (`FeedListView`, `NetworkService`)
- Functions/methods: camelCase (`fetchData()`, `handleError(_:)`)
- Properties: camelCase (`isLoading`, `currentUser`)
- Constants: camelCase (`let maxRetries = 3`)
- Protocols: PascalCase, often `-able`/`-ible` or `-Protocol` suffix (`Configurable`, `DataProvider`)
- Enum cases: camelCase (`case loading`, `case error(String)`)

## SwiftUI Patterns

- Keep views small and composable; extract subviews when a body exceeds ~40 lines
- Use `@State` for view-local state, `@Binding` for parent-owned state, `@Observable` for shared model objects
- Prefer `@Observable` (Swift 5.9+) over `ObservableObject` + `@Published` for new code
- Use `@Environment` for dependency injection of services and settings
- Extract complex view logic into a separate model/viewmodel type, not into the view body

## State Management

- `@State` for simple, view-private state
- `@Binding` for child views that modify parent state
- `@Observable` classes for shared domain state (replaces the older ObservableObject pattern)
- `@Environment(\.key)` for injecting dependencies (custom `EnvironmentKey` types)
- Avoid deeply nested state; prefer flat model objects with computed properties

## Error Handling

- Use Swift's `throws` / `try` / `catch` for recoverable errors
- Define domain-specific error enums conforming to `Error` (and `LocalizedError` for user-facing messages)
- In SwiftUI, surface errors via an `@State var errorMessage: String?` and an `.alert` modifier
- For async operations: use `Task { }` with `do/catch` inside the closure

## Async Patterns

- Use `async` / `await` for all asynchronous work (no completion handlers in new code)
- Use `Task { }` in SwiftUI to launch async work from synchronous contexts (button actions, onAppear)
- Use `TaskGroup` for concurrent operations
- Cancel tasks properly: store `Task` handles and call `.cancel()` on view disappear when appropriate

## Dependencies (Swift Package Manager)

- Define dependencies in `Package.swift`
- For wrapping C/Go libraries: create a binary target or system library target in the package manifest
- Pin dependency versions to exact or range (`from: "1.0.0"`)
- Prefer SPM packages over CocoaPods or Carthage

## Integrating Go/C Libraries

- Wrap the `.a` archive or `.xcframework` as an SPM binary target:
  ```swift
  .binaryTarget(name: "MyLib", path: "Frameworks/MyLib.xcframework")
  ```
- Or as a system library target with a module map for `.a` + `.h`:
  ```swift
  .systemLibrary(name: "CMyLib", path: "Sources/CMyLib")
  ```
  with a `module.modulemap` that exposes the C header
- Import in Swift code: `import MyLib` or `import CMyLib`
- C functions appear as global Swift functions; call them directly
- Mind memory: C strings returned from Go must be freed (call `free()` from Swift)

## Testing

- Unit tests: `XCTestCase` subclasses in `Tests/`
- Use `@testable import <ModuleName>` to access internal symbols
- Async test methods: `func testFoo() async throws { ... }`
- UI tests: `XCUIApplication` for integration / E2E testing
- Run via Makefile: `make test` wrapping `swift test` or `xcodebuild test`

## Build

- Use Makefile targets wrapping `swift build`, `swift test`, `xcodebuild`
- Archive for distribution: `xcodebuild archive` with an export options plist
- Code signing: handle via Xcode project settings, not in Makefile

## Formatting & Linting

- Use `swift-format` (Apple's official formatter) for consistent style
- Configure via `.swift-format` file at project root
- Lint with `swiftlint` if additional rules are desired
- Makefile targets: `make fmt`, `make lint`

## Comments

- Use `///` doc comments for public types, methods, and properties
- Use `//` for inline implementation notes
- Mark incomplete work with `// TODO:` and known issues with `// FIXME:`
