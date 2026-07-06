# Contributing to AegisNex

We welcome contributions from the community. This document outlines the process for contributing.

## Code of Conduct

This project adheres to the [Contributor Covenant](https://www.contributor-covenant.org/). By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/aegisnex.git`
3. Set up the development environment (see [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md))
4. Create a feature branch: `git checkout -b feat/my-feature`

## Development Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r local-requirements.txt
cp .env.example .env
python -m src.scripts.init_db
```

## Coding Standards

| Requirement | Standard |
|---|---|
| Formatter | `ruff format` |
| Linter | `ruff check` |
| Type checker | `mypy --strict` |
| Line length | 120 characters |
| Imports | `from __future__ import annotations` |
| Docstrings | Google style for public APIs |

### Naming

| Element | Convention | Example |
|---|---|---|
| Classes | PascalCase | `PlatformRepository` |
| Functions | snake_case | `execute_tool()` |
| Constants | UPPER_SNAKE | `TOOL_REGISTRY` |
| Private methods | `_` prefix | `_metrics_tool()` |

## Pre-Commit Checks

Run before every commit:

```bash
ruff format .              # Format code
ruff check --fix .        # Lint + auto-fix
mypy src/                 # Type checking
pytest                    # Tests
```

## Testing

```bash
pytest                          # All tests
pytest -x -vv                   # Fail-fast with verbose output
pytest --cov=src --cov-report=html  # Coverage report
pytest tests/test_intelligence.py -v  # Specific module
```

Tests use `pytest` with `pytest-asyncio` for async tests. See existing tests in `tests/` for patterns.

## Pull Request Process

1. Ensure all pre-commit checks pass
2. Write clear, descriptive commit messages
3. Reference any related issues in the PR description
4. Update documentation if adding new features
5. Add tests for new functionality
6. Keep PRs focused — one feature or fix per PR

### PR Title Format

```
feat: add HTTP monitoring endpoint
fix: resolve incident timeline ordering
docs: update API reference for search endpoint
refactor: extract monitoring engine from dashboard
test: add coverage for Guardian module
```

## Adding a New Tool

1. Implement in `src/intelligence/tools.py`
2. Register in `TOOL_REGISTRY` with risk level, access mode, permission level
3. Add API route in `src/dashboard.py` if needed
4. Write tests in `tests/test_tool_router.py`
5. Document in [TOOL_REFERENCE.md](docs/TOOL_REFERENCE.md)

## Adding a New Integration

1. Create provider class in `src/integrations/providers/`
2. Extend `IntegrationProvider` base class
3. Register in `src/integrations/__init__.py`
4. Add configuration schema
5. Write integration tests

## Adding a New Compliance Framework

1. Add framework definition in `src/compliance/frameworks.py`
2. Define controls list
3. Implement assessment logic in `src/compliance/engine.py`
4. Add evidence collection rules in `src/compliance/evidence.py`
5. Register in the compliance registry

## Questions?

Open a [discussion](https://github.com/your-org/aegisnex/discussions) or reach out to maintainers.
