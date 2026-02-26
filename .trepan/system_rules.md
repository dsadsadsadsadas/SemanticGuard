# 📏 System Rules — Linter, Security & Formatting

## Security Rules (Hard Blockers)
- NO hardcoded secrets, API keys, or passwords
- NO `eval()` or `exec()` with user input
- NO `os.system()` or `subprocess` with `shell=True`
- ALL file paths must use `os.path.realpath()` + `startswith()` validation
- ALL SQL queries must use parameterized statements

## Code Style
- Max line length: 100 characters
- Use type hints on all public functions
- Docstrings required on all public classes and functions
- No print() in production code — use logging

## Formatting
- Python: Black + isort
- JS/TS: Prettier (2-space indent)
- Commits: Conventional Commits format (`feat:`, `fix:`, `docs:`)

## Test Coverage
- Minimum coverage: 80% on new code
- All API endpoints must have integration tests
