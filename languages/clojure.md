# Clojure Standards

Builds on [`lisp.md`](./lisp.md). The baseline is the community [Clojure Style Guide](https://guide.clojure.style/).
This file and `lisp.md` win where they differ.

## Toolchain

- Target the current Clojure 1.12 release on a supported LTS JDK
- Use the Clojure CLI and `deps.edn`. Do not start new projects on Leiningen
- Build artifacts with `tools.build` in a `build.clj`
- Use Babashka for scripts and task running. Keep tasks in `bb.edn` when the project has more than a few
- Pin every dependency to an exact `:mvn/version` or a `:git/sha`. Never depend on a branch

## Project Layout

```text
deps.edn                 # :paths, :deps, and :aliases such as :test and :build
build.clj                # tools.build entry point, when the project ships an artifact
src/<org>/<app>/core.clj
test/<org>/<app>/core_test.clj
.clj-kondo/config.edn
.cljfmt.edn
```

- Namespaces have at least two segments: `acme.billing`, not `billing`
- Hyphens in a namespace become underscores in its file path: `acme.rate-limit` lives in `acme/rate_limit.clj`
- One namespace per file. Test namespaces end in `-test`

## Namespaces

- Require with an alias: `(:require [clojure.string :as str])`
- Use `:refer` only for a few names that read better bare, such as `deftest` and `is`. Never `:refer :all`
- Keep the `ns` form's `:require` list sorted

## Functions and Data

- Put the docstring before the argument vector. See "Docstrings" in `lisp.md`
- Use keywords for map keys. Namespace them, as in `:user/id`, when the map crosses a module boundary
- Destructure arguments in the parameter vector when it removes `get` noise
- Use `->` and `->>` for linear pipelines. Use `some->` when any step may return `nil`. Switch to `let` when steps need
  names
- Prefer `defn-` and `^:private` for helpers. The public API is what other namespaces call
- Use records and protocols only when you need polymorphic dispatch. Use multimethods for open dispatch on data

## Errors

- Throw `ex-info` with a message and a data map. Put the identifiers a caller needs into the map:
  `(throw (ex-info "user not found" {:user/id id}))`
- Read error data with `ex-data`. Do not parse messages
- Catch `ExceptionInfo` or a specific Java exception. Do not catch `Throwable` outside a top-level handler

## Java Interop

- Turn on `(set! *warn-on-reflection* true)` in every namespace that calls Java methods. Treat a reflection warning as a
  bug and add a type hint
- Wrap Java APIs in small Clojure functions at the edge. Keep interop out of core logic

## Testing

- Use `clojure.test`. Run it with the Cognitect `test-runner` from a `:test` alias
- Name tests for the behavior they prove: `(deftest expired-token-is-rejected ...)`
- Group related assertions with `testing`. Use `are` for tables of cases

## Formatting and Linting

- Format with `cljfmt`. Configure it in `.cljfmt.edn`. `cljfmt fix` formats in place and `cljfmt check` verifies
- Lint with `clj-kondo`, configured in `.clj-kondo/config.edn`. CI runs `clj-kondo --lint src test` and fails on any
  warning
- clj-kondo catches the misplaced docstring, unused bindings, and wrong arity before the code runs
- `clojure-lsp` reads the same clj-kondo config, so the editor and CI agree
- Makefile targets: `fmt` and `fmt-select` call `cljfmt fix`. `fmt-check` calls `cljfmt check`. `lint` calls
  `clj-kondo`. `test` runs the `:test` alias
