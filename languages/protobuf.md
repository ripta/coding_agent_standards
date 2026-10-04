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

## Schema Evolution

Every change to a published schema must stay wire-compatible with the clients and servers already running.

Safe changes:

- Adding a field with a new field number
- Adding an RPC method, a message, or a service
- Adding an enum value at the end, when readers handle values they do not know

Breaking changes:

- Changing a field's number or type
- Removing or renaming a field, method, message, or service
- Changing a method's request or response type
- Changing the package
- Making an optional field required

When a breaking change is unavoidable, add a new version package, such as `feeds.v2` in `api/feeds/v2/`. Keep the old
version serving until its clients move. Record the migration path and the retirement date in an ADR.

## Field Numbers

- Numbers 1–15 encode in one byte. Give them to the fields that appear in most messages.
- Numbers 16–2047 encode in two bytes. Use them for less frequent fields.
- Never use 19000–19999. Protobuf reserves that range for itself.
- When deleting a field, `reserve` both its number and its name, so neither is reused with a different meaning.
- Never reuse an enum value. A removed enum value is reserved the same way.

```protobuf
message Feed {
  reserved 5, 7;
  reserved "old_field_name";

  int64 id = 1;
  string url = 2;

  int32 error_count = 16;
}
```

## Code Generation

- Use `buf` for linting (STANDARD + COMMENTS presets) and generation
- Generate Go code to `pkg/gen/`
- Generate TypeScript code to `ui/src/gen/`
- Workflow: define proto, `make lint`, `make generate`, implement, register handler
