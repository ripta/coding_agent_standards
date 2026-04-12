# Python Service Profile

For Python web services built with FastAPI.

@../profiles/baseline.md
@../languages/python.md
@../practices/testing.md
@../practices/error-handling.md
@../practices/security.md

## Framework

- Use FastAPI with Uvicorn as the ASGI server
- Define the app in `app.py` or `main.py`: `app = FastAPI()`
- Use routers for grouping: `router = APIRouter(prefix="/api/v1")`, registered via `app.include_router()`
- Run via `uv run uvicorn src.myapp.main:app --reload` in development

## Request/Response Models

- Use Pydantic `BaseModel` for all request and response schemas
- Enable strict mode: `model_config = ConfigDict(strict=True)`
- Use `Annotated` types with `Field()` for validation: `Annotated[int, Field(ge=1, le=100)]`
- Return typed response models; never return raw dicts from endpoints

## Dependency Injection

- Use FastAPI's `Depends()` for service injection
- Define dependency factories that return configured service instances
- Use `lifespan` context manager for app-level setup/teardown (database pools, clients)

## Error Handling

- Define exception handlers via `@app.exception_handler(AppError)`
- Return structured JSON errors: `{"error": "message", "code": "ERROR_CODE"}`
- Map domain exceptions to HTTP status codes (400, 404, 409, 422, 500)
- Use `HTTPException` only for truly HTTP-level concerns; prefer domain exceptions

## Health & Observability

- Expose `GET /healthz` (liveness) and `GET /readyz` (readiness) endpoints
- Use `structlog` for structured JSON logging
- Add request ID middleware for tracing

## Service Testing

- Use `httpx.AsyncClient` with `ASGITransport` for async endpoint tests
- Override dependencies in tests via `app.dependency_overrides`
- Test error responses and status codes explicitly
