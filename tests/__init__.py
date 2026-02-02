"""DexAI Test Suite

This package contains all tests for the DexAI personal assistant.

Test organization:
- unit/: Unit tests for individual modules
  - security/: Security tool tests (sanitizer, audit, permissions)
  - adhd/: ADHD communication tests (language_filter, response_formatter)
  - tasks/: Task engine tests (manager, decompose, friction_solver)
  - memory/: Memory tool tests (commitments, context_capture)
- integration/: Integration tests for API endpoints and workflows

Running tests:
    # All tests
    uv run pytest

    # Specific module
    uv run pytest tests/unit/security/

    # With coverage
    uv run pytest --cov=tools --cov-report=term-missing

    # Excluding slow tests
    uv run pytest -m "not slow"
"""
