---
description: update a Python code base to Python 3.9+
---

# Python Codebase Modernization

You are an experienced software developer. Please modernize this Python
codebase to follow current best practices and standards.

## Target Environment
- **Current Python version**: Python 3.6 or lower
- **Target Python version**: Python 3.9 or higher
- **Maintain backward compatibility**: Yes - code must remain compatible with the target Python version

## Modernization Goals

### Code Quality & Style
- Apply modern Python idioms and patterns
- Use f-strings instead of .format() or % formatting
- Replace old-style string formatting
- Use pathlib.Path instead of os.path where appropriate
- Apply list/dict/set comprehensions where readable
- Use context managers (with statements) for resource management

### Type Safety
- Add type hints to all functions and methods
- Use modern typing features: list[str] instead of List[str], dict[str, int] instead of Dict[str, int] (Python 3.9+)
- Use Optional[str] and Union[] from typing module for union types
- Ensure mypy compliance with strict mode
- Add py.typed marker if this is a library

### Modern Language Features
- **STRONGLY PREFERRED**: Use dataclasses instead of plain classes for data-holding objects
- Replace NamedTuple with dataclass where beneficial
- Replace attr.s/attrs classes with dataclasses
- Use asyncio/await patterns if applicable

### Testing Best Practices (pytest)
- Use pytest.mark.parametrize instead of duplicating test functions
- Move shared fixtures to conftest.py in appropriate directories
- Use fixture scopes (function, class, module, session) appropriately
- Use monkeypatch fixture for mocking/patching where appropriate
- Replace unittest.mock.patch with monkeypatch when simpler
- Replace unittest.TestCase classes with pytest-style functions where beneficial
- Use pytest's advanced features (fixtures, markers, parametrize)
- Ensure all tests pass after each change: pytest

### Project Structure & Tooling
- Convert to pyproject.toml (remove setup.py/setup.cfg if present)
- Configure ruff for linting and formatting
- Set up mypy for type checking
- Add pre-commit hooks configuration
- [Optional] Migrate to uv for dependency management

### Specific Constraints
- **Breaking changes are NOT allowed** - maintain API compatibility
- **No specific performance requirements** - focus on code quality and maintainability
- **Dependencies**: Keep minimal, but commonly used libraries that provide significant benefit are acceptable
- Prefer standard library solutions when they are sufficient

## Execution Approach
1. Start by analyzing the current codebase structure
2. Create a modernization plan with todos
3. Work incrementally, ensuring tests pass after each change
4. Run pytest after each modification
5. Run linting and type checking regularly
6. Commit changes in logical groups

# Important

Only git commit one logical change at a time.
