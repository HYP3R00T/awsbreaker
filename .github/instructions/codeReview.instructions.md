# Code Review Instructions

The goal of code review is to ensure high-quality, maintainable, and secure code. Use the following checklist to review contributions.

## What to Look For

### Code Style & Structure

- Code follows project conventions and [PEP 8](https://peps.python.org/pep-0008/).
- All functions, methods, and class attributes are properly type-annotated.
  - Prefer built-in generics (`list[str]`, `dict[str, Any]`) over `typing.List`, etc.
- Code is modular, testable, and single-purpose where applicable.
- No unnecessary complexity, redundant logic, or repeated code.
- Imports are grouped and ordered: standard library → third-party → local.

### Type Safety

- All public APIs and core logic use consistent type hints.
- `Optional[...]` or `T | None` is used for nullable values.
- Avoid `Any` unless unavoidable.
- Use `Literal`, `TypedDict`, or Pydantic models for structured data.

### Data Validation

- Pydantic models are used for input validation and data serialization.
- Field types are precise, with appropriate constraints.
- Nested or reusable models are created for complex structures.
- Use `@field_validator` and `@model_validator` where needed.

### Error Handling

- Use clear, actionable exception messages.
- Always raise specific exception types (e.g., `ValueError`, `HTTPException`).
- Avoid `except:`; catch only the necessary exceptions.
- No silent failure or swallowed exceptions.

### Logging

- Uses `structlog` instead of the standard `logging` module.
- Logs include structured, context-rich fields (e.g., `event="...", user_id=...`).
- Errors and exceptions are logged with severity: `info`, `warning`, `error`, `critical`.
- Avoid logging sensitive data.

### Testing

- New code is covered by tests (`pytest` recommended).
- Tests are deterministic, readable, and minimal.
- External dependencies are mocked.
- Edge cases and failure paths are covered.

### Security

- Validate all external inputs.
- Sanitize any user-generated content or file paths.
- Avoid hardcoded credentials or API keys.
- Confirm that secret values are not logged or exposed.

## Review Suggestions

- Use clear and constructive language in comments.
- Prefer inline code suggestions when possible.
- Provide summary feedback on overall quality and risks.
- Suggest small, actionable improvements.
