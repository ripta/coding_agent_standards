# Embedding a Lisp

Rules for running a Lisp interpreter inside a host program. They hold for any embedded dialect. Janet is the chosen
dialect for Rust, Zig, and Swift hosts. Its specifics are in "Embedding" in [`janet.md`](./janet.md). The Go host is
undecided. See "Go" below.

## Ownership

- The host owns the interpreter's lifecycle. One host object creates it, configures it, and tears it down
- Bind each interpreter to one thread, or to one owner that serializes access. Never share one across threads without
  the runtime's documented support
- Load scripts through one host function that sets up the environment, applies the sandbox, and reports errors. Do not
  scatter direct `eval` calls through the host

## The Host API

- Expose a small, named set of host functions to scripts. Treat it as a public API with a version
- Put the host functions in their own module or prelude, so a script's dependencies are visible in one place
- A host function validates its arguments and returns an error to the script for bad input. It never crashes the host

## Marshalling

- Convert values at the boundary. Host code works with host types, and script code works with script types
- Copy data across the boundary by default. Share a reference only when the copy is measured to be too expensive, and
  document who owns it
- Root any script value the host keeps between calls. See the dialect file for how

## Errors

- Catch every script error at the boundary and turn it into the host's error type. Include the script name, line, and
  message
- Never let a runtime's non-local exit, such as `longjmp`, cross host frames. Rust, Swift, Zig, and Go cannot unwind
  through it safely
- A script error is the script's failure, not the host's. Report it and keep the host running unless the host cannot
  continue

## Sandboxing and Limits

- Deny by default. Grant file, network, process, and FFI access to a script only when its job needs it
- Bound CPU time. Use the runtime's interrupt hook from a watchdog. When the runtime has none, run untrusted scripts in
  a separate process
- Bound memory. Use the runtime's limits when it has them, or a separate process when it does not
- Treat scripts from users or the network as untrusted input, even when they look like configuration

## Testing

- Test host functions through the interpreter, the way a script calls them
- Keep a directory of script fixtures that exercise the host API, including error cases. Run them in the host's normal
  test suite
- Test the sandbox. A fixture that tries a denied operation must fail with the expected error

## Rust

- Use the `janetrs` crate with its default `amalgation` feature, which compiles the vendored runtime into the crate.
  The feature name is spelled that way. The crate warns that breaking changes may happen and has no MSRV, so pin an
  exact version
- Follow [`rust-unsafe.md`](./rust-unsafe.md) for any raw C API call the crate does not wrap

## Zig

- Add `janet.c` to the build as a C source with `-std=c99`. Import `janet.h` with `@cImport`, or with the translate-c
  build step on Zig versions that moved C translation out of the compiler
- Zig's C translation drops some function-like macros. Wrap any you need in a small C shim compiled with `janet.c`
- Convert Janet signals to Zig error sets at the boundary. See [`zig.md`](./zig.md)

## Swift

- Wrap the vendored sources in a SwiftPM C target with a module map. See "Integrating Go/C Libraries" in
  [`swift.md`](./swift.md)
- Swift cannot call C variadic functions or import function-like macros. Wrap the ones you need in a C shim
- C callbacks must be `@convention(c)` and cannot capture context. Pass a `void *` userdata pointer, and recover the
  Swift object with `Unmanaged`
- Translate Janet signals into thrown Swift errors at the boundary

## Go

Undecided. No Go profile exists yet. Choose when a Go project first needs an embedded Lisp, and record the choice here.
The two candidates:

- Janet through cgo. Same dialect as the other hosts. It brings in [`cgo.md`](./cgo.md), loses easy cross-compilation,
  and needs care with threads. Janet's VM is thread-local, but goroutines move between OS threads. The VM must live on
  one goroutine that calls `runtime.LockOSThread`, and other goroutines send it work over a channel
- A pure-Go Lisp, such as `zygomys`, `glojure`, or `let-go`. No cgo, and goroutine-friendly. The cost is a second
  dialect with its own semantics, and these projects are less mature than Janet
