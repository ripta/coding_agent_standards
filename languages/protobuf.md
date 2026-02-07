# Protocol Buffer Standards

## File Organization

- Location: `api/<service>/<version>/` (e.g., `api/feeds/v1/feeds.proto`)
- Lowercase directory names, lowercase filenames

## Naming

- Messages: PascalCase (`SubscribeToFeedRequest`, `Feed`)
- Fields: snake_case (`feed_url`, `group_id`)
- Services: PascalCase (`FeedService`)
- RPC methods: PascalCase (`SubscribeToFeed`, `ListMyFeeds`)
- Enums: SCREAMING_SNAKE_CASE with type prefix (`PATTERN_TYPE_URL`)
- First enum value: always `_UNSPECIFIED = 0`

## Comments

- Comments before fields and methods, not inline
- Service-level doc comment describing the service purpose
- Method-level doc comment describing what the RPC does

## Timestamps

- Use `google.protobuf.Timestamp` for all temporal fields

## Code Generation

- Use `buf` for linting (STANDARD + COMMENTS presets) and generation
- Generate Go code to `pkg/gen/`
- Generate TypeScript code to `ui/src/gen/`
- Workflow: define proto, `make lint`, `make generate`, implement, register handler
