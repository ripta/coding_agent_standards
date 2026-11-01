# Lisp Standards

Rules shared by every Lisp dialect these standards cover: Clojure, Common Lisp, Racket, and Janet. Each dialect file
adds its own toolchain and idioms on top of these:

- [`clojure.md`](./clojure.md)
- [`common-lisp.md`](./common-lisp.md)
- [`racket.md`](./racket.md)
- [`janet.md`](./janet.md)
- [`lisp-embedding.md`](./lisp-embedding.md) for running a Lisp inside a host program

Where a dialect has a community style guide, its file adopts that guide as the baseline. The rules here and in the
dialect file win where they differ.

## Formatting

- The formatter owns indentation. Never hand-indent against it. Each dialect file names its formatter
- Closing parens gather on the last line of the form. Never leave a `)` alone on its own line:

  ```clojure
  ;; wrong
  (defn area [w h]
    (* w h)
  )

  ;; right
  (defn area [w h]
    (* w h))
  ```

- Keep lines under 100 characters
- Separate top-level forms with one blank line
- Align the arguments of a call when it breaks across lines, or indent the body by two spaces. The formatter decides
  which. Do not mix the two by hand

## Comments

- Clojure, Common Lisp, and Racket share the semicolon ladder: `;` trails code on the same line, `;;` sits on its own
  line inside a form, `;;;` introduces a top-level section, and `;;;;` heads a file
- Janet comments start with `#`. See `janet.md`
- Prefer a docstring to a comment above a definition. Use comments for the "why" inside a body
- Do not comment out forms to disable them. Delete them. Clojure's `#_` and Racket's `#;` are for the REPL, not commits

## Naming

- Names are `kebab-case`: `parse-header`, `max-retries`
- Predicates, mutators, and dynamic variables follow each dialect's convention. The dialect files list them:

  | Concept | Clojure | Common Lisp | Racket | Janet |
  |---|---|---|---|---|
  | Predicate | `empty?` | `evenp`, `empty-list-p` | `empty?` | `empty?` |
  | Mutation | `swap!` | `n` prefix, as in `nreverse` | `set-box!` | named plainly, as in `put` |
  | Dynamic variable | `*out*` with `^:dynamic` | `*standard-output*` | parameter `current-output-port` | `(dyn :out)` |
  | Constant | plain `def` | `+max-size+` | plain `define` | `def` |
  | Conversion | `->vec` | `coerce` | `string->symbol` | `string` |

- Do not abbreviate beyond the dialect's own standard library. `cfg` is fine when the dialect uses it. `prs-hdr` is not

## Docstrings

- Every public definition gets a docstring, except in Racket, which documents with Scribble and contracts
- Docstring position differs by dialect. A docstring in the wrong position is a string expression that is evaluated and
  discarded, so the definition has no documentation and no error tells you:

  | Dialect | Docstring goes |
  |---|---|
  | Clojure | before the argument vector: `(defn f "Doc." [x] ...)` |
  | Common Lisp | after the lambda list: `(defun f (x) "Doc." ...)` |
  | Janet | before the argument tuple: `(defn f "Doc." [x] ...)` |

- Lint in CI so a misplaced docstring fails the build. Each dialect file names the linter that catches it

## Data and Functions

- Model data as plain data first: maps, lists, vectors, structs. Reach for classes or records only when dispatch or a
  protocol needs them
- Keep functions pure. Push I/O, mutation, and global state to the edges of the program
- Prefer the dialect's sequence functions and comprehensions to hand-written recursion. Use explicit recursion when it
  is clearer, and use the dialect's tail-call form where the runtime needs one, such as Clojure's `recur`
- Prefer threading macros or `let` bindings to deeply nested calls when the nesting hides the data flow

## Macros

- Write a function first. Write a macro only when you need to control evaluation or introduce syntax
- Never write a macro to save a function call's runtime cost unless a measurement shows the call matters
- Keep expansions hygienic. Use the dialect's tool: `syntax-parse` in Racket, auto-gensyms such as `x#` in Clojure,
  `gensym` or `with-syms` in Common Lisp and Janet
- A macro's expansion is its contract. Test it by asserting on `macroexpand-1` output or by testing the code it
  generates, not only the final value
- A macro should expand to a call to a function that does the real work. That keeps the logic testable without the
  macro

## Reading Untrusted Input

The reader can run code. Read untrusted input only through a data-only reader:

- Clojure: `clojure.edn/read-string`, never `clojure.core/read-string`
- Common Lisp: bind `*read-eval*` to `nil` around `read`, and prefer a real parser such as a JSON library
- Racket: a data parser such as `json`. Never `eval` what `read` returned
- Janet: `parse` returns data without running it. Never pass the result to `eval`

## REPL and Image State

- Explore at the REPL freely. Whatever matters must land in a source file and a test before the work is done
- A fresh process loading from source must reproduce the result. Never rely on state that only exists in a running REPL
  or a saved image
- Reload a whole namespace or file after editing it. Redefining one form at a time leaves stale definitions behind

## Testing

- Use the dialect's standard runner. Each dialect file names it
- Tests live in a test directory or test submodule, not mixed into public source modules
- Every Makefile exposes `test` and `ci`, plus each of `check`, `lint`, `fmt`, `fmt-check`, and `fmt-select` that the
  dialect's tools support. See [`makefile.md`](../claude/practices/makefile.md) for the vocabulary
