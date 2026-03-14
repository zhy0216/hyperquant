# Contributing to HyperQuant

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/zhy0216/hyperquant.git
cd hyperquant
pip install -e ".[dev]"
```

## Workflow

1. Fork the repo and create a branch from `main`
2. Write your code and add tests
3. Ensure all checks pass: `make lint && make typecheck && make test`
4. Submit a pull request

## Code Standards

- **Formatting**: `ruff format` (line length 100)
- **Linting**: `ruff check` with auto-fix via `make fmt`
- **Type safety**: All functions must have type annotations (`mypy --disallow-untyped-defs`)
- **Tests**: Add tests for new functionality. Run with `make test`

## Reporting Issues

Open an issue with:
- What you expected vs what happened
- Steps to reproduce
- Python version and OS
