# Completed Tasks

## 2026-03-26 20:05:00
- Implemented Global Evaluation Semaphore in `semanticguard_server/server.py`.
- Throttled `/evaluate_cloud` endpoint to a maximum of 2 concurrent evaluations.
- Verified syntax with `py_compile`.

## 2026-03-26 19:48:26
- Fixed token estimation logic in `evaluate_cloud` endpoint.
- Moved system prompt generation before token consumption for accurate weighting.
- Updated `TokenBucket` pacing using new formula: `(len(prompt) + len(code)) / 4 + 800`.
- Ensured token refund logic uses the updated estimation.

## 2026-03-26 08:30:00
- Migrated VS Code extension to Thin Client architecture
- Implemented `evaluateWithServer` with Gzip and 60s timeout
- Rewired `evaluateSave` and `auditEntireFolder` (concurrency 10)
- Removed legacy `callCloudAPI` and split-brain logic

## 2026-03-26 11:40:00
- Implemented Section 0 "Hard Overrides" in Golden System Prompt for catastrophic sinks.
- Established Meta-Autopsy "Prompt Reconciliation" loop in `server.py`.
- Updated VS Code extension to pass `current_prompt` context during autopsy calls.
- Enhanced audit output channel to display `bypassed_rule` and `bypass_reason`.
- Implemented 18 "Twitches" in `server.py` to resolve Final_Test gaps (SSRF, RCE, SQLi, and others).
- Added exclusion rules for parameterized queries and white-listed domain validations.

## 2026-03-26 12:45:00
- Resolved Autopsy Context Hallucinations by reconstructing the full Golden Prompt in `run_autopsy`.
- Stabilized rule reconciliation by passing `project_path` from the VS Code extension.
- Implemented Golden Prompt V2.5 "Assumption Logic": Treat all public function parameters as untrusted sources.
- Implemented Golden Prompt V2.5 "Guard Priority": Section 0 now respects valid security guards (eliminating FPs).
- Cleaned up `server.py` codebase by removing duplicate imports.

## How to Use

When you complete a task from `pending_tasks.md`, move it here with a timestamp.

Example:
```
## 2024-01-15 14:30:00
- Implemented user authentication
- Added input validation
```
