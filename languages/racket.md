# Racket Standards

Builds on [`lisp.md`](./lisp.md). The baseline is the official style guide,
[How to Program Racket](https://docs.racket-lang.org/style/). This file and `lisp.md` win where they differ.

## Toolchain

- Target the current Racket 9 release on Chez Scheme
- Start every module with `#lang racket/base`. Require the extra libraries it needs, such as `racket/list` and
  `racket/string`. Use `#lang racket` only in throwaway scripts. It loads more at startup, and Resyntax only analyzes
  `racket/base` modules
- Declare the package in `info.rkt`, with `deps` and `build-deps` listed. Install it locally with
  `raco pkg install --auto`

## Project Layout

```text
info.rkt
main.rkt                 # the package's public entry module
private/<module>.rkt     # implementation modules, not part of the public API
scribblings/<pkg>.scrbl  # documentation, when the package is published
```

- Keep a module's tests in a `(module+ test ...)` submodule at the end of the same file
- Put larger integration tests in a separate `tests/` directory

## Modules and Contracts

- `provide` the public API explicitly. Never `(provide (all-defined-out))` from a library module
- Attach contracts at the module boundary with `contract-out`. Internal helpers do not need contracts
- Document public bindings in Scribble. A comment above a `define` is not documentation for callers

## Functions and Data

- Use `define` inside bodies instead of nested `let`, as the style guide recommends
- Use `struct` for records. Add `#:transparent` when instances should print and compare by value
- Use the `for` family for iteration: `for/list`, `for/fold`, `for/sum`, `for/first`
- Use `match` to destructure instead of chains of accessors
- Mutable state lives in boxes, parameters, or mutable structs. Name mutators with a `!` suffix
- Use parameters such as `current-output-port` for dynamic configuration. Bind them with `parameterize`

## Errors

- Raise structured exceptions. Define a struct that extends `exn:fail` and carries the data a handler needs
- Use `raise-argument-error` and its siblings to report bad arguments with the standard message format
- Catch with `with-handlers` and a predicate for the specific exception. Do not catch `exn?` outside a top-level
  handler
- Release resources with `dynamic-wind` or with `call-with-` functions such as `call-with-input-file`

## Macros

- Write macros with `syntax-parse`. Declare syntax classes for the parts, so bad uses get a clear error at expansion
  time
- Prefer `define-syntax-rule` for one-pattern macros that need no validation

## Testing

- Use `rackunit` inside `module+ test`
- Run all tests with `raco test -p <pkg>`, or `raco test <dir>` before the package is installed
- Group checks with `test-case`. Name each one for the behavior it proves

## Formatting and Linting

- Format with `raco fmt` from the `fmt` package: `raco pkg install fmt`. `raco fmt -i <file>` rewrites in place
- `raco fmt` prints to stdout without `-i`. `fmt-check` compares that output to each file and fails on any difference
- `raco make` compiles every module. Run it as `check` so unbound identifiers and syntax errors fail CI
- Lint with Resyntax: `raco pkg install --installation resyntax`. `resyntax analyze` reports suggestions and
  `resyntax fix` applies them
- Makefile targets: `fmt` and `fmt-select` call `raco fmt -i`. `check` calls `raco make`. `lint` calls
  `resyntax analyze`. `test` calls `raco test`
