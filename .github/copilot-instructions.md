# Project Coding Standards

## Naming Conventions

- Use `snake_case` for variable names, function names, and method names.
- Use `PascalCase` for class names and exceptions.
- Use `ALL_CAPS` for module-level constants.
- Prefix unused or private variables/members with an underscore (`_`).
- File names should also follow `snake_case`.

## Type Safety

- Use type hints for all function arguments, return types, and class attributes.
- Prefer built-in generics (Python 3.9+):
  - Use `list[str]`, `dict[str, Any]`, `tuple[int, ...]`
  - Avoid `List`, `Dict`, `Tuple` from the `typing` module unless required for compatibility.
- Use `T | None` for nullable values.
- Avoid `Any` unless strictly necessary.
- Use `Literal`, `TypedDict`, or Pydantic models for structured data.

## Data Modeling and Validation

- Use Pydantic for data validation, serialization, and transformation.
- Always define strict types for model fields.
- Use `field(default=..., alias=..., description=...)` when metadata is needed.
- Use `model_config = ConfigDict(...)` or `class Config:` in legacy syntax to configure validation behavior.
- Prefer `model.model_dump()` and `model.model_validate()` over `.dict()` and `.parse_obj()` in newer versions.
- For deeply nested structures, define reusable models rather than embedding dicts/lists inline.
- Use `@field_validator` and `@model_validator` for complex validation logic.
- Keep Pydantic models immutable (`frozen=True`) if mutation is not intended.

## Error Handling

- Raise exceptions with specific, actionable messages.
- Use built-in or custom exception types (e.g., `ValueError`, `FileNotFoundError`).
- Avoid bare `except:` clauses. Always catch specific exceptions.
- Log errors using the `logging` module with appropriate levels (`info`, `warning`, `error`, `critical`).
- Handle external failures (I/O, database, API) gracefully.

## Formatting and Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) and consistent idioms.
- Use `f-strings` for string formatting.
- Prefer `pathlib` over `os.path` for file and path handling.
- Format code using `ruff format`.
- Lint code using `ruff`.
- Organize imports in the order:
  1. Standard library
  2. Third-party libraries
  3. Local modules

## Documentation

- Use Google-style docstrings for all public modules, functions, classes, and methods.
- Document all parameters, return values, raised exceptions, and side effects.
- Keep functions and classes small and focused.
- Split logic into reusable utilities and modules when appropriate.

## Test and CI Guidelines

- Write unit tests for all new features and bug fixes.
- Use `pytest` for test discovery and execution.
- Prefer clear, isolated, deterministic tests.
- Mock external dependencies where needed.
- All pull requests must pass tests and linters before merging.
