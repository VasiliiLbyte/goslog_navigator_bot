---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Testing

> This file extends [common/testing.md](../common/testing.md) with Python specific content.

## Framework

Use **pytest** as the testing framework.

## Python Risk-Based Test Policy

- **quick-fix:** run changed tests and nearby package tests (`pytest path/to/tests -q`).
- **feature:** run package-level tests plus coverage on touched modules.
- **critical:** run full suite, coverage report, and integration/API tests for impacted flows.

## Coverage

```bash
pytest --cov=src --cov-report=term-missing
```

Recommended command set:

```bash
# quick-fix
pytest -q

# feature
pytest --cov=src --cov-report=term-missing

# critical
pytest --cov=src --cov-report=term-missing --maxfail=1
```

## Test Organization

Use `pytest.mark` for test categorization:

```python
import pytest

@pytest.mark.unit
def test_calculate_total():
    ...

@pytest.mark.integration
def test_database_connection():
    ...
```

## Reference

See skill: `python-testing` for detailed pytest patterns and fixtures.
