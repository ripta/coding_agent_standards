# Common Lisp Standards

Builds on [`lisp.md`](./lisp.md). The baseline is the
[Google Common Lisp Style Guide](https://google.github.io/styleguide/lispguide.xml). This file and `lisp.md` win where
they differ.

## Toolchain

- Target SBCL. It ships monthly, so pin the version CI uses and bump it on purpose
- Write portable ANSI Common Lisp unless a feature needs SBCL. Isolate implementation-specific code behind a small
  package, or use a portability library such as `uiop` or `bordeaux-threads`
- Build with ASDF
- Manage dependencies with `ocicl`. Commit its `ocicl.csv` lockfile so every checkout loads the same versions
- Use SLY or SLIME in Emacs, or Alive in VS Code, for interactive work

## Project Layout

```text
<app>.asd                # defines <app> and <app>/test
src/package.lisp
src/<module>.lisp
test/package.lisp
test/<module>-test.lisp
ocicl.csv
```

- One `.asd` file at the root defines the main system and a `<app>/test` system
- List components explicitly with `:serial t` or `:depends-on`. Use `package-inferred-system` only if the whole project
  adopts it

## Packages

- One package per module, defined with `uiop:define-package` or `defpackage`
- `:use` only `:cl`. Bring in other packages with `:local-nicknames`, so references stay qualified as `str:split`
- Export the public API explicitly. Never reach into another package with `::`

## Naming

- Predicates end in `p`. Add a hyphen when the name already contains one: `evenp`, `empty-list-p`
- Special variables wear earmuffs: `*default-timeout*`. Define them with `defvar` when a reload must keep the value,
  and `defparameter` when a reload should reset it
- Constants wear plus signs: `+max-depth+`. Use `defconstant` only for values that are `eql` across reloads, such as
  numbers and characters. A string or list constant breaks on reload
- Destructive variants start with `n`, as in `nreverse`. Never call one on a literal or on data you do not own

## Functions and Data

- Put the docstring after the lambda list. See "Docstrings" in `lisp.md`
- Use `defstruct` for plain records and CLOS `defclass` when you need inheritance or generic dispatch
- Prefer `loop` or the sequence functions for iteration. Do not rely on tail-call elimination, which the standard does
  not guarantee
- Declare types at public boundaries with `declaim` and `ftype` when it catches mistakes. Never set `(safety 0)`
  globally. Lower it only inside a measured hot function

## Conditions

- Signal errors with `error` and a condition class from `define-condition`. Give the class slots for the data a
  handler needs. Do not signal bare strings from library code
- Use `handler-case` to recover at a boundary. Use `handler-bind` when the handler must run before the stack unwinds
- Offer restarts with `restart-case` when a caller could reasonably choose how to continue, such as skipping a bad
  record. Restarts are the condition system's main advantage; use them for recoverable library errors
- Clean up with `unwind-protect`. Wrap resources in `with-` macros that expand to it

## Testing

- Use FiveAM. The `<app>/test` system depends on it and defines one suite per module
- The test system's `test-op` must signal an error when any test fails. Otherwise `asdf:test-system` returns normally
  and CI passes a failing suite
- Run tests in a fresh process: `sbcl --non-interactive --eval '(asdf:test-system :<app>)'`.
  `--non-interactive` turns an unhandled error into a nonzero exit

## Compiling and Linting

- The compiler is the first linter. Load the system in CI with `handler-bind` on `warning`, and exit nonzero when any
  warning or style-warning was signalled. ASDF's own failure flags do not catch style-warnings
- `mallet` and `sblint` are optional extra linters. Neither is required yet
- No command-line formatter is standard. Indentation follows SLY or SLIME's Common Lisp indenter. Keep the editor's
  indentation and do not hand-align against it
- Makefile targets: `check` loads the system with warnings fatal. `test` runs the test system. `fmt-check` stays
  absent until a formatter is chosen
