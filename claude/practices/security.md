# Security Practices

- Validate all external input at system boundaries (user input, API requests, config files)
- Never trust internal function arguments for security decisions; validate at the edge
- Use parameterized queries; never interpolate user input into SQL or commands
- Validate URLs against an allowlist before making outbound requests
- Store secrets in environment variables; never commit them to version control
- Use structured error responses; never leak stack traces or internal paths to users
