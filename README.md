# Coding Agent Standards

Personal coding standards, best practices, and Claude Code configuration for use across projects. This repo acts as a single source of truth for language conventions, development practices, project management SOPs, and AI agent behavior rules.

## Structure

```
coding_agent_standards/
├── languages/          Language-specific standards
├── practices/          Cross-cutting practices
├── project-management/ Plans, proposals, design, and tracking standards
├── claude/             Claude Code skills, hooks, rules, and settings
├── profiles/           Composable project profiles
└── bin/                Utility scripts
```

### Languages

Standards for each language/framework covering naming, project structure, error handling, testing, and tooling:

- **Go** (`go.md`) -- packages, error wrapping, concurrency, build patterns
- **CGO** (`cgo.md`) -- C FFI bridge layers, type conversions, memory management, gomobile
- **Swift** (`swift.md`) -- SwiftUI, async/await, SPM, Go/C library integration
- **Rust** (`rust.md`) -- modules, workspaces, error handling with thiserror/anyhow
- **Zig** (`zig.md`) -- allocators, error sets, build system, embedded tests
- **Svelte** (`svelte.md`) -- SvelteKit, Svelte 5 runes, Tailwind, protobuf RPC
- **Protocol Buffers** (`protobuf.md`) -- file layout, naming, buf-based code generation

### Practices

Cross-cutting concerns that apply regardless of language:

- **Testing** -- table-driven tests, golden files, HTTP handler tests, testability patterns
- **Error Handling** -- wrapping, sentinel errors, structured responses, validation
- **Code Review** -- review priorities, submission checklist
- **Security** -- input validation, parameterized queries, secret management

### Project Management

Standards for planning and tracking work:

- **Plans** -- phase and milestone definitions, promotion rules, document format
- **Proposals** -- feature proposal lifecycle (draft through implemented), numbering
- **Design** -- Architecture Decision Records (ADRs), lifecycle, immutability rules
- **Tracking** -- cross-reference conventions, metadata standards, markdown guidelines

### Claude Code Configuration

Rules, hooks, settings, and skills for Claude Code agents:

- **Rules** -- decision-making boundaries, work discipline, git workflow, commit/PR style
- **Hooks** -- templates for auto-formatting on edit, pre-commit linting, test reminders
- **Settings** -- tool permission whitelists per language ecosystem
- **Skills** -- specialized agents for code review, testing, linting, Makefile maintenance, etc.

### Profiles

Composable profiles that bundle the right standards for a given project type. Each profile imports a baseline plus relevant language and practice standards:

| Profile | Stack |
|---|---|
| `go-service` | Go backend services |
| `go-svelte-fullstack` | Go + Svelte + protobuf |
| `go-cgo-library` | Go libraries with C FFI |
| `swift-macos-app` | SwiftUI macOS apps |
| `swift-cli` | Swift command-line tools |
| `rust-project` | Rust projects |
| `zig-project` | Zig projects |
| `svelte-app` | Svelte/SvelteKit apps |
| `oss-contrib` | Lightweight profile for contributing to repos you don't own |

## Usage

Import a profile from your project's `CLAUDE.md`:

```markdown
@~/projects/coding_agent_standards/profiles/go-service.md
```

For repos you don't own, use `CLAUDE.local.md` (auto-gitignored by Claude Code) to avoid committing personal standards:

```markdown
@~/projects/coding_agent_standards/profiles/oss-contrib.md
```

### Setup Validation

The `bin/check-setup` script validates that a project has standards properly configured. It can be wired up as a Claude Code `SessionStart` hook to run automatically when you open a project.

### Non-standard Paths

If this repo doesn't live at `~/projects/coding_agent_standards`, create a symlink:

```sh
ln -s /actual/path/to/coding_agent_standards ~/coding-standards
```

## License

[MIT](LICENSE)
