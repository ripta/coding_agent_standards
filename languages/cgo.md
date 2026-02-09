# cgo / gomobile Standards

Standards for Go projects that expose functionality through C ABI interfaces, including c-archive builds and gomobile bindings.

## Project Structure

```
cmd/<name>/main.go           # Optional: standalone Go binary for testing
internal/                    # Pure Go implementation (no cgo here)
bridge/                      # cgo export layer: thin wrappers with //export
  bridge.go                  # Exported C functions
  types.go                   # C-compatible type conversions
gomobile/                    # gomobile bind layer (if targeting mobile)
  api.go                     # Public Go API surface for gomobile bind
dist/                        # Build output: .a, .h, .xcframework
Makefile                     # Build targets for all output formats
```

## Bridge Layer

- Keep the `bridge/` package thin: it only converts between Go and C types and delegates to `internal/`
- Every exported function must have an `//export FunctionName` comment
- The bridge package must import `"C"` and contain a `main` function (required for c-archive)
- Use `import "C"` in only one file per package when possible to reduce cgo compilation scope

## Type Conversions

- Strings: `C.CString` / `C.GoString` -- always free C strings with `C.free` on the receiving side
- Byte slices: pass as `*C.char` + `C.int` length pairs, never rely on null termination for binary data
- Errors: return C int status codes (0 = success) with a separate error string out-parameter, or use a result struct
- Booleans: use `C.int` (0/1), not `C.bool` (portability)
- Structs: define C-compatible structs explicitly; don't pass Go structs across the boundary

## Memory Management

- Document ownership at every boundary crossing: who allocates, who frees
- Go-allocated memory passed to C must remain referenced to prevent GC collection (use `runtime.KeepAlive` or pin)
- C-allocated memory passed to Go must be freed by the C side or explicitly with `C.free`
- Never store Go pointers in C memory (violates cgo pointer passing rules)
- For long-lived objects, use a handle table (map Go objects to integer handles passed to C)

## gomobile bind

- The `gomobile/` package exports a clean Go API (no `C` import, no `//export`)
- gomobile bind generates the Objective-C / Java wrappers automatically
- Supported types: primitives, `string`, `[]byte`, interfaces with exported methods, structs with exported fields
- Avoid: channels, function values, maps, slices of non-byte types (not supported by gomobile)
- Name the package clearly (e.g., `package mylib`) -- this becomes the framework name

## Build Targets

```makefile
# c-archive: produces .a and .h
build-archive:
	CGO_ENABLED=1 go build -buildmode=c-archive -o dist/libmylib.a ./bridge/

# gomobile bind: produces .xcframework (iOS/macOS)
build-xcframework:
	gomobile bind -target=macos -o dist/MyLib.xcframework ./gomobile/

# gomobile bind: produces .aar (Android)
build-aar:
	gomobile bind -target=android -o dist/MyLib.aar ./gomobile/

# Header generation: extract/verify the generated .h
build-header:
	CGO_ENABLED=1 go build -buildmode=c-archive -o dist/libmylib.a ./bridge/
	@echo "Header at dist/libmylib.h"

clean:
	rm -rf dist/
```

## Testing

- Unit test the `internal/` package with standard Go tests (no cgo involved)
- Integration test the `bridge/` layer with a small C test program that links against the archive
- Test the `gomobile/` API from Go directly before running gomobile bind
- Verify the generated `.h` header has the expected function signatures

## Linting

- Standard `golangci-lint` for Go code
- Run `go vet` which includes cgo-specific checks (pointer passing rules)
- Review `//export` comments match function names exactly (silent failures if mismatched)

## Common Pitfalls

- Forgetting `import "C"` must be immediately preceded by the cgo preamble comment (no blank line between)
- Passing Go function pointers to C (use static functions with handle lookup instead)
- Not setting `CGO_ENABLED=1` when cross-compiling
- gomobile bind silently drops unsupported types from the generated interface
- Missing `runtime.KeepAlive` causes GC to collect objects still referenced from C
