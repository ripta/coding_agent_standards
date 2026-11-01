# Janet Standards

Builds on [`lisp.md`](./lisp.md). Janet has no community style guide. Its formatter, `janet-format`, sets the layout.
These standards use Janet mainly as an embedded language. See [`lisp-embedding.md`](./lisp-embedding.md) for the
host-side rules every embedded Lisp follows, and "Embedding" below for Janet's specifics.

## What Janet Is

- A small Lisp with its own semantics. It borrows syntax from Clojure, but it is not a Clojure dialect
- The whole runtime is one amalgamated C file plus two headers, with no dependencies beyond libc
- Its core includes PEGs for parsing, fibers for coroutines and error handling, an event loop, and a `sandbox` call
- It is a small project. Most work comes from one lead maintainer, and the library ecosystem is thin. Expect to write
  host bindings yourself instead of finding a package

## Data Types

Janet pairs each collection with a mutable and an immutable form. Choose deliberately:

| Immutable | Mutable | Literal |
|---|---|---|
| tuple | array | `[1 2]` and `@[1 2]` |
| struct | table | `{:a 1}` and `@{:a 1}` |
| string | buffer | `"abc"` and `@"abc"` |

- Default to the immutable form. Use the `@` form only when the code mutates it
- Use keywords for keys: `{:name "x"}`
- Structs and tuples compare by value. Tables and arrays compare by identity

## Naming and Comments

- Comments start with `#`. Use `#` for inline and own-line comments alike
- Predicates end in `?`: `empty?`
- Put the docstring before the argument tuple: `(defn area "Width times height." [w h] (* w h))`
- Use `def` for bindings that never change and `var` only when a binding is reassigned with `set`
- Name module-private definitions with `defn-` and `def-`

## Errors

- Raise with `error`, passing a struct when a handler needs data: `(error {:kind :not-found :id id})`
- Catch with `try`. Use `protect` when you want a `[ok? value]` tuple instead of a handler
- Clean up with `defer` or `with`. Do not rely on the garbage collector to close files or sockets

## Parsing

- Prefer `peg/match` to regular expressions or hand-rolled scanners. Define grammars with named rules so each rule
  can be tested alone

## Testing and Tooling

- Install spork, the official contrib library. It ships `janet-format` and the `spork/test` module
- The Janet docs call `jpm` the older, less frequently updated project manager and point to spork's `janet-pm` as its
  successor. Pick one per project and record it in the project's README
- Put test scripts in `test/`. A test script exits nonzero when an assertion fails
- Makefile targets: `fmt` and `fmt-select` call `janet-format`. `test` runs each script in `test/`

## Embedding

- Vendor the amalgamated `janet.c`, `janet.h`, and `janetconf.h` from one tagged release. Recent docs list them as
  `build/c/janet.c`, `src/include/janet.h`, and `src/conf/janetconf.h` after `make`. Check the paths for the version
  you vendor. Record the version next to the files
- Compile `janet.c` with `-std=c99`. Set build options in `janetconf.h`, not with ad hoc `-D` flags
- The VM state is thread-local. Call `janet_init` on each thread that runs Janet, and `janet_deinit` on that thread when
  done. Never touch Janet values from a thread that did not create them
- Start from `janet_core_env`. Register host functions into that environment before loading any script
- Call into Janet with `janet_pcall`, which catches Janet panics and returns a signal. Check that the signal is
  `JANET_SIGNAL_OK` before using the result
- Janet panics with `longjmp`. A host function that can panic must not hold host resources across the call, and a panic
  must never unwind through Rust, Swift, or Zig frames. Catch it in C or with `janet_pcall` first
- A Janet value held by host code across calls must be rooted with `janet_gcroot` and released with `janet_gcunroot`.
  An unrooted value can be collected while the host still points at it
- Restrict scripts with `sandbox` from Janet or `janet_sandbox` from C before running untrusted code. Read
  `(doc sandbox)` for the current list of capabilities. The list grows between releases
