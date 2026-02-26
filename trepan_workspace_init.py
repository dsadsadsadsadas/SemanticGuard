#!/usr/bin/env python3
"""
🛡️ Trepan Workspace Initializer
Creates the .trepan/ Pillar directory in any project root.

Usage:
    python trepan_workspace_init.py              # Init in current directory
    python trepan_workspace_init.py ./my_project # Init in a specific path
"""

import sys
import argparse
from pathlib import Path

TREPAN_DIR = ".trepan"

PILLARS = {
    "golden_state.md": """\
# 🏛️ Golden State — Architecture & Tech Stack

## Core Architecture
- **Platform**: [Define your platform here, e.g. FastAPI + React]
- **Database**: [e.g. PostgreSQL + SQLAlchemy]
- **Auth**: [e.g. JWT + OAuth2]
- **Deployment**: [e.g. Docker + AWS ECS]

## Invariants (NEVER change without explicit approval)
- [ ] Invariant 1: [e.g. All API endpoints must require JWT auth]
- [ ] Invariant 2: [e.g. No direct SQL strings — use ORM only]
- [ ] Invariant 3: [e.g. All secrets via environment variables]

## Tech Stack Constraints
- Backend language: [e.g. Python 3.11+]
- Frontend framework: [e.g. React 18 with TypeScript]
- Test framework: [e.g. pytest + vitest]
""",
    "done_tasks.md": """\
# ✅ Done Tasks — Completed Milestones

## Phase 1: Foundation
- [ ] Project scaffolding
- [ ] CI/CD pipeline

> Add completed milestones here as you ship them.
> Format: `- [x] Task description (YYYY-MM-DD)`
""",
    "pending_tasks.md": """\
# 📋 Pending Tasks — Future Milestones

## Next Up
- [ ] Task 1: [Description]
- [ ] Task 2: [Description]

## Backlog
- [ ] Backlog item 1

> Keep this up to date. Trepan uses this to detect context drift —
> if your AI is being asked to do something NOT on this list, it may flag it.
""",
    "system_rules.md": """\
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
""",
}


def init_workspace(root: Path) -> None:
    trepan_dir = root / TREPAN_DIR
    trepan_dir.mkdir(exist_ok=True)
    print(f"🛡️  Trepan Gatekeeper — Workspace Init")
    print(f"   Target: {trepan_dir.resolve()}")
    print()

    created = []
    skipped = []

    for filename, content in PILLARS.items():
        file_path = trepan_dir / filename
        if file_path.exists():
            skipped.append(filename)
        else:
            file_path.write_text(content, encoding="utf-8")
            created.append(filename)

    for f in created:
        print(f"   ✅ Created  .trepan/{f}")
    for f in skipped:
        print(f"   ⏭️  Skipped  .trepan/{f}  (already exists)")

    print()
    print("✨ Workspace initialized! Next steps:")
    print("   1. Fill in .trepan/golden_state.md with your architecture")
    print("   2. Fill in .trepan/system_rules.md with your coding rules")
    print("   3. Start the Trepan server:  trepan_server\\bootstrap.bat")
    print("   4. Install the Antigravity extension from the extension/ folder")


def main():
    parser = argparse.ArgumentParser(
        description="🛡️  Initialize a Trepan Gatekeeper workspace"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root directory (default: current directory)",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"❌ Error: '{root}' is not a valid directory.")
        sys.exit(1)

    init_workspace(root)


if __name__ == "__main__":
    main()
