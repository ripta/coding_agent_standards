# Unsafe Rust and SAFETY Comments

Standards for writing and reviewing `unsafe` code. Every `unsafe` block,
`unsafe impl`, and `unsafe fn` declaration must follow these conventions.

## What `SAFETY:` is

`SAFETY:` is the Rust community convention for justifying an `unsafe`
operation. The compiler cannot prove `unsafe` blocks, `unsafe impl`s, or calls
to `unsafe fn`s are sound, so the convention is to attach a comment that
explains why the invariants required by the operation hold at that site. It is
the counterpart to the `# Safety` doc section on an `unsafe fn` declaration:
the declaration states the contract the caller must uphold, and `SAFETY:` is
the caller discharging it.

It is a community convention rather than a language feature, but it is
codified by the Rustonomicon, used pervasively in the standard library, and
lintable by Clippy.

## Enforcement

Enable Clippy's `undocumented_unsafe_blocks` lint at warn in the workspace
lint table and promote it to a hard error by the standard `-D warnings` gate.
It fires on any `unsafe` block that is not immediately preceded by a
`// SAFETY:` (or `/* SAFETY: */`) comment, so CI rejects new unsafe sites that
do not carry a justification.

Companion lints `multiple_unsafe_ops_per_block` and `unsafe_op_in_unsafe_fn`
are optional. Decide per project whether plain `unsafe { ... }` inside an
`unsafe fn` body is acceptable, or whether nested annotations are required.

## Categories of justification

There is no separate tag for different kinds of unsafety; every site uses
`SAFETY:`. By content, justifications cluster into a few recurring categories.
A new `unsafe` site should usually fit one of these, and the comment should
make clear which invariant it is leaning on.

- **FFI and platform-API contracts.** A call into a C function, libc, or an
  OS API is sound because the documented contract holds at this call: the
  pointer is non-null, the length is in bytes, the buffer is valid for the
  declared lifetime, the string is NUL-terminated, etc. The justification
  points at the contract the foreign function published.
- **Platform and architectural facts.** A port number is architectural; a
  fixed memory-mapped region is identity-mapped by the loader at this
  address; an intrinsic is valid because the binary requires the
  corresponding CPU feature. The justification is a fixed fact about the
  platform or build configuration.
- **Aliasing and uniqueness invariants.** "This `&mut T` from a raw pointer
  is sound because we are the only live reference"; "this allocator is the
  sole owner of the remaining usable slots". `unsafe impl Send` or `Sync`
  blocks explain why the trait's contract holds for this type.
- **Concurrency discipline.** Lock-free queues, atomic flags, and shared-
  memory structures are justified by naming the producer and consumer roles
  with explicit reference to which acquire/release pair publishes the slot,
  or which lock is held when the access happens.
- **Initialization and layout invariants.** `MaybeUninit::assume_init`,
  `transmute`, and raw pointer reads are justified by where and when the
  memory was initialized, and which type-layout guarantee (`#[repr(C)]`,
  `#[repr(transparent)]`, known size and alignment) makes the operation
  well-defined.
- **Caller-vouched preconditions.** Pointer writes into freshly allocated
  regions or arena slots are justified by "the caller promised this region
  is unused and writable through this alias", matching a clause on the
  enclosing `unsafe fn`'s `# Safety` section.

## Style

Block-comment style, not doc-comment style: `//` always, never `///`.
Placement is on the line immediately above the `unsafe` token (block, `impl`,
or specific call), with no blank line between, so Clippy attributes the
comment to the operation.

The body is conversational but technically precise. The pattern is the
invariant in plain words, then the reason it holds here. On `unsafe impl`
blocks, name the trait obligation by phrase ("uniqueness contract", "Send",
"Sync") and then explain why this implementation satisfies it. When a
justification takes the form "the caller promised X", the matching `# Safety`
doc on the enclosing function must say exactly X.

Longer justifications break into short paragraphs separated by a `//` blank
line rather than running on. Comments explain why the operation is sound,
never what it does; the surrounding code already shows that.

## `# Safety` doc sections

`# Safety` sections on `unsafe fn` declarations do not use the `SAFETY:` tag.
They use the standard markdown heading and describe the contract from the
caller's perspective in full sentences, naming each invariant the caller must
uphold so the `SAFETY:` comment at the call site has something concrete to
point at.
