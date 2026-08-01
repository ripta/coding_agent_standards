# Coding Agent Standards

Personal coding standards, best practices, and Claude Code configuration for use across projects. This repo acts as a single source of truth for language conventions, development practices, project management SOPs, and AI agent behavior rules.

## Structure

```
coding_agent_standards/
├── languages/          Language-specific standards
├── practices/          Cross-cutting practices
├── project-management/ Plans, proposals, design, and tracking standards
├── .claude/            Project-local Claude Code config (skills, settings) for this repo
├── claude/             Claude Code skills, hooks, rules, and settings (exported to other projects)
├── profiles/           Composable project profiles
└── bin/                Utility scripts
```

### Languages

Standards for each language/framework covering naming, project structure, error handling, testing, and tooling:

- **1z** (`1z.md`) -- stack-oriented functional language, naming conventions, testing, quotation-based control flow
- **Go** (`go.md`) -- packages, error wrapping, concurrency, build patterns
- **CGO** (`cgo.md`) -- C FFI bridge layers, type conversions, memory management, gomobile
- **Swift** (`swift.md`) -- SwiftUI, async/await, SPM, Go/C library integration
- **Rust** (`rust.md`) -- modules, workspaces, error handling with thiserror/anyhow
- **Zig** (`zig.md`) -- allocators, error sets, build system, embedded tests
- **Svelte** (`svelte.md`) -- SvelteKit, Svelte 5 runes, Tailwind, protobuf RPC
- **TypeScript** (`typescript.md`) -- strict tsconfig, ESM, Biome for format and lint, pnpm
- **Phaser** (`phaser.md`) -- scenes, pooling, atlases, isometric projection
- **PixiJS** (`pixijs.md`) -- v8 application setup, scene graph, ticker, asset bundles
- **Protocol Buffers** (`protobuf.md`) -- file layout, naming, buf-based code generation

### Practices

Cross-cutting concerns that apply regardless of language:

- **Testing** -- table-driven tests, golden files, HTTP handler tests, testability patterns
- **Error Handling** -- wrapping, sentinel errors, structured responses, validation
- **Code Review** -- review priorities, submission checklist
- **Security** -- input validation, parameterized queries, secret management
- **Game Simulation** -- fixed timestep, sim/render split, determinism, offline replay

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
- **Skills** -- specialized agents for code review, testing, linting, Makefile maintenance, etc. These live in `claude/skills/` and are exported to other projects that import this repo.

Note the distinction between `.claude/` and `claude/`:
- **`.claude/`** is the standard Claude Code project config directory. Skills and settings here apply when working **in this repo** (e.g., `standards-synthesizer` for onboarding new languages).
- **`claude/`** contains skills, hooks, rules, and settings **exported to other projects** that reference this repo via `--add-dir` or `@import`.

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
| `1z-project` | 1z standalone projects |
| `1z-interpreter` | 1z interpreter (Zig + 1z) |
| `zig-project` | Zig projects |
| `svelte-app` | Svelte/SvelteKit apps |
| `ts-game` | Browser games in TypeScript, engine-agnostic base |
| `ts-phaser-game` | `ts-game` plus Phaser |
| `ts-pixi-game` | `ts-game` plus PixiJS |
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

### Installing the Claude Code Plugin

The skills, hooks, and agents under `claude/` are packaged as a Claude Code plugin named `coding-standards`. The marketplace manifest lives at the repo root (`.claude-plugin/marketplace.json`) and points at `./claude` as the plugin source.

Install once, inside any Claude Code session:

```
/plugin marketplace add ripta/coding_agent_standards
/plugin install coding-standards@coding-standards
```

Choose **user** scope when prompted so the plugin is available in all your projects. A local clone works as the marketplace source too (`/plugin marketplace add ~/projects/coding_agent_standards`), in which case updates track your clone instead of GitHub.

Plugin skills are namespaced: invoke them as `/coding-standards:<skill-name>`. If you keep a copy of a skill in `~/.claude/skills/`, both versions will appear -- delete the personal copy once the plugin version works for you.

#### Updating

Installed plugins are cached copies, not live references. After changes land in the repo:

```
/plugin marketplace update coding-standards
```

The plugin has no pinned version; Claude Code versions it by git commit SHA, so every update pulls the latest commit.

#### Active Development

To iterate on a skill without the cache in the way, launch Claude Code with the plugin loaded directly from source:

```sh
claude --plugin-dir ~/projects/coding_agent_standards/claude
```

Edit freely, then run `/reload-plugins` in the session to pick up changes immediately. Once satisfied, commit and push, and installed copies catch up via `/plugin marketplace update`.

### Setup Validation

The `bin/check-setup` script validates that a project has standards properly configured. It can be wired up as a Claude Code `SessionStart` hook to run automatically when you open a project.

### Non-standard Paths

If this repo doesn't live at `~/projects/coding_agent_standards`, create a symlink:

```sh
ln -s /actual/path/to/coding_agent_standards ~/coding-standards
```

## License

[MIT](LICENSE)
