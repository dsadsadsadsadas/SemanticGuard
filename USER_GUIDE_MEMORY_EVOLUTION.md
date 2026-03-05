# User Guide: Memory Evolution & Task Management

## Overview

Trepan now includes a powerful Memory Evolution system that allows it to learn from your past mistakes and successes. This guide shows you how to use these new features.

## Feature 1: Task Management

### Moving Tasks from Pending to Done

When you complete a task, you can move it from your pending list to your done list with a timestamp.

#### Using the API

```bash
curl -X POST http://127.0.0.1:8000/move_task \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Implement user authentication",
    "project_path": "C:\\Users\\ethan\\Documents\\Projects\\Trepan_Test_Zone"
  }'
```

#### What Happens

1. Task is removed from `.trepan/pending_tasks.md`
2. Task is added to `.trepan/done_tasks.md` with timestamp
3. Vault is updated with new snapshots
4. `.trepan.lock` is re-signed

#### Example

**Before** (pending_tasks.md):
```markdown
# Pending Tasks

- Implement user authentication
- Add rate limiting
- Write integration tests
```

**After** (done_tasks.md):
```markdown
# Completed Tasks

## 2024-01-15 14:30:00
- Implement user authentication
```

**After** (pending_tasks.md):
```markdown
# Pending Tasks

- Add rate limiting
- Write integration tests
```

## Feature 2: Memory Evolution (The Memory-to-Law Pipeline)

### How It Works

Trepan can analyze your `problems_and_resolutions.md` file and automatically:
- Extract successful patterns from RESOLVED problems → Add to `golden_state.md`
- Extract failure causes from UNRESOLVED problems → Add as negative rules to `system_rules.md`

This means Trepan learns from your experience and prevents you from repeating past mistakes.

### Step 1: Log Your Problems

When you encounter a problem, document it in `.trepan/problems_and_resolutions.md`:

```markdown
# Problems and Resolutions

## Problem 1: SQL Injection Vulnerability (RESOLVED)
**Date**: 2024-01-15
**Description**: Security audit found SQL injection vulnerability in user search endpoint.
**Root Cause**: String concatenation used for SQL queries instead of parameterized statements.
**Resolution**: Replaced all string concatenation with parameterized queries using prepared statements.
**Status**: RESOLVED
**Pattern Learned**: NEVER use string concatenation for SQL queries. Always use parameterized statements with placeholders.

## Problem 2: Memory Leak in Production (UNRESOLVED)
**Date**: 2024-01-20
**Description**: Production server memory usage grows unbounded over 24 hours.
**Root Cause**: Suspected circular references in event listeners not being garbage collected.
**Resolution**: Still investigating. Tried weak references but issue persists.
**Status**: UNRESOLVED
**Failure Pattern**: Event listeners with strong references to parent objects create circular references.
```

### Step 2: Trigger Memory Evolution

Once you've resolved a problem (or identified a recurring failure), trigger the memory evolution:

```bash
curl -X POST http://127.0.0.1:8000/evolve_memory \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "C:\\Users\\ethan\\Documents\\Projects\\Trepan_Test_Zone"
  }'
```

### Step 3: Review the Results

The API will return:
```json
{
  "status": "success",
  "patterns_added": 2,
  "rules_added": 1,
  "message": "Memory evolved: 2 patterns, 1 rules"
}
```

### What Gets Updated

#### golden_state.md (Successful Patterns)
```markdown
## Evolved Patterns (Learned from Experience)
_Auto-generated on 2024-01-15 14:30:00_

- Pattern 1: Always use parameterized statements for SQL queries to prevent injection attacks
- Pattern 2: Use thread-local storage for session data in multi-threaded applications
```

#### system_rules.md (Negative Rules)
```markdown
## Evolved Rules (Learned from Failures)
_Auto-generated on 2024-01-15 14:30:00_

- Rule 1: NEVER use string concatenation for SQL queries because it creates injection vulnerabilities
- Rule 2: NEVER use strong references in event listeners because they create circular references that prevent garbage collection
```

### Step 4: Future Protection

From now on, whenever you write code, Trepan will:
- ✅ Reference the evolved patterns in `golden_state.md`
- ✅ Enforce the evolved rules in `system_rules.md`
- ✅ Reject code that repeats past mistakes
- ✅ Accept code that follows learned patterns

## Real-World Example

### Scenario: SQL Injection Bug

1. **Problem Occurs**: Your security audit finds SQL injection vulnerability
   ```python
   # BAD CODE (vulnerable)
   query = f"SELECT * FROM users WHERE username = '{username}'"
   cursor.execute(query)
   ```

2. **You Log It**:
   ```markdown
   ## Problem: SQL Injection in User Search (RESOLVED)
   Root Cause: String concatenation in SQL queries
   Resolution: Used parameterized statements
   Status: RESOLVED
   ```

3. **You Trigger Evolution**:
   ```bash
   curl -X POST http://127.0.0.1:8000/evolve_memory -d '{"project_path": "..."}'
   ```

4. **Trepan Learns**:
   - Adds pattern to `golden_state.md`: "Use parameterized SQL statements"
   - Adds rule to `system_rules.md`: "NEVER use string concatenation for SQL"

5. **Future Protection**:
   - If you (or another developer) tries to write vulnerable SQL code again:
   ```python
   # This will be REJECTED by Trepan
   query = f"SELECT * FROM users WHERE id = {user_id}"
   ```
   - Trepan will reject it with reasoning: "Violates evolved rule: NEVER use string concatenation for SQL queries"

## Best Practices

### 1. Document Problems Thoroughly

Include:
- **Date**: When the problem occurred
- **Description**: What went wrong
- **Root Cause**: Why it happened
- **Resolution**: How you fixed it (or what you tried)
- **Status**: RESOLVED or UNRESOLVED
- **Pattern/Failure**: What you learned

### 2. Mark Status Clearly

Use exactly these status values:
- `Status: RESOLVED` - For fixed problems (patterns will be extracted)
- `Status: UNRESOLVED` - For ongoing issues (negative rules will be extracted)

### 3. Trigger Evolution Regularly

Good times to trigger memory evolution:
- After resolving a major bug
- At the end of each sprint
- After security audits
- When onboarding new team members (so they learn from past mistakes)

### 4. Review Evolved Rules

After evolution, review:
- `.trepan/golden_state.md` - Check the new patterns make sense
- `.trepan/system_rules.md` - Check the new rules are correct
- `.trepan/Walkthrough.md` - Review the LLM's reasoning

### 5. Keep Problems File Clean

Periodically archive old problems:
```markdown
# Problems and Resolutions

## Active Problems
(Current issues go here)

## Archived Problems (2024-Q1)
(Old issues moved here)
```

## Advanced Usage

### Batch Task Management

Move multiple tasks at once:
```bash
for task in "Task 1" "Task 2" "Task 3"; do
  curl -X POST http://127.0.0.1:8000/move_task \
    -H "Content-Type: application/json" \
    -d "{\"task_description\": \"$task\", \"project_path\": \"...\"}"
done
```

### Scheduled Memory Evolution

Set up a cron job (Linux/Mac) or Task Scheduler (Windows) to run memory evolution daily:

**Linux/Mac** (crontab):
```bash
0 0 * * * curl -X POST http://127.0.0.1:8000/evolve_memory -d '{"project_path": "..."}'
```

**Windows** (PowerShell script):
```powershell
$body = @{
    project_path = "C:\Users\ethan\Documents\Projects\Trepan_Test_Zone"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/evolve_memory" `
                  -Method Post `
                  -Body $body `
                  -ContentType "application/json"
```

### Integration with CI/CD

Add memory evolution to your CI/CD pipeline:

```yaml
# .github/workflows/trepan-evolution.yml
name: Trepan Memory Evolution

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday

jobs:
  evolve:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Start Trepan Server
        run: |
          cd trepan_server
          python -m uvicorn server:app &
          sleep 10
      - name: Trigger Memory Evolution
        run: |
          curl -X POST http://127.0.0.1:8000/evolve_memory \
            -H "Content-Type: application/json" \
            -d '{"project_path": "${{ github.workspace }}"}'
      - name: Commit Changes
        run: |
          git config user.name "Trepan Bot"
          git config user.email "trepan@example.com"
          git add .trepan/
          git commit -m "chore: Trepan memory evolution"
          git push
```

## Troubleshooting

### "problems_and_resolutions.md not found"

Create the file:
```bash
echo "# Problems and Resolutions\n\nNo problems reported yet." > .trepan/problems_and_resolutions.md
```

### "No patterns or rules extracted"

Make sure your problems have:
- Clear `Status: RESOLVED` or `Status: UNRESOLVED` markers
- Detailed root cause and resolution sections
- Explicit pattern or failure descriptions

### "Vault compromised" error

Re-sign the vault:
```bash
curl -X POST http://127.0.0.1:8000/resign_vault
```

### Memory evolution not working

Check:
1. Trepan server is running: `curl http://127.0.0.1:8000/health`
2. Ollama is running: `ollama list`
3. llama3.1 model is available: `ollama pull llama3.1:8b`
4. Server logs for errors: Check terminal where server is running

## FAQ

**Q: How often should I trigger memory evolution?**
A: After resolving major bugs, at the end of sprints, or when you want Trepan to learn from recent problems.

**Q: Can I manually edit the evolved patterns and rules?**
A: Yes! They're in `golden_state.md` and `system_rules.md`. Just remember to re-sign the vault after manual edits.

**Q: What if the LLM extracts the wrong pattern?**
A: Review the evolved sections and manually correct them. The LLM is good but not perfect.

**Q: Can I undo a memory evolution?**
A: Yes, restore from the vault snapshots in `.trepan/trepan_vault/` or use git to revert the changes.

**Q: Does memory evolution work offline?**
A: Yes! It uses your local Ollama instance, no cloud required.

## Summary

The Memory Evolution system makes Trepan a self-improving architectural seatbelt:

1. **Log problems** in `problems_and_resolutions.md`
2. **Trigger evolution** with `/evolve_memory` endpoint
3. **Trepan learns** from your experience
4. **Future code** is protected from past mistakes

This creates a virtuous cycle where your codebase becomes more resilient over time, and Trepan becomes smarter about your specific project's needs.

---

**Next Steps**: Try logging a real problem you've encountered and trigger memory evolution to see it in action!
