# AI Assistant Autonomy - Quick Reference Card

## What Is It?

Your AI coding assistant (Copilot/Cursor/Codex) now automatically maintains your project's architectural pillars by learning from its own experience.

## How It Works (Simple)

```
1. AI generates code
2. You save file
3. Trepan evaluates
4. AI updates pillars automatically
5. You see notification
```

## What Gets Updated

| File | What It Tracks | When Updated |
|------|----------------|--------------|
| `problems_and_resolutions.md` | Errors and struggles | AI detects error |
| `system_rules.md` | Negative rules | AI's approach fails |
| `golden_state.md` | Success patterns | AI's solution works |
| `history_phases.md` | Task completions | AI completes task |

## User Experience

### What You See

**Notification**:
```
🤖 Trepan AI Autonomy: Executed 2 pillar update(s)
[View Changes]
```

**Console** (if Developer Tools open):
```
[TREPAN AI AUTONOMY] Found actions section
[TREPAN AI AUTONOMY] Executing: APPEND_TO_FILE .trepan/problems_and_resolutions.md
[TREPAN AI AUTONOMY] ✅ Successfully appended
```

**Git**: All changes tracked in Source Control

### What You Do

- **Review**: Click "View Changes" to see Git diff
- **Revert**: Use Git to undo if needed
- **Edit**: Can still edit pillars manually
- **Disable**: Turn off in settings if needed

## Example Scenarios

### Scenario 1: AI Makes Error

```python
# AI suggests:
async def get_data():
    result = await fetch_from_db()
    return result
```

**What happens**:
1. You save → Trepan evaluates
2. AI detects: "async/await doesn't work in Flask"
3. AI updates `problems_and_resolutions.md`:
   ```
   ## Problem #5: Async/await in Flask (UNRESOLVED)
   **AI Generated**: Yes
   **Description**: Tried async/await in Flask route
   ```
4. You see: "🤖 Executed 1 pillar update"

### Scenario 2: You Fix It

```python
# You write:
def get_data():
    thread = threading.Thread(target=fetch_from_db, daemon=True)
    thread.start()
    return {"status": "processing"}
```

**What happens**:
1. You save → Trepan evaluates
2. AI detects: "User switched from async to threading"
3. AI updates `system_rules.md`:
   ```
   ## AI-Learned Rule #3
   **NEVER** use async/await in Flask routes
   ```
4. You see: "🤖 Executed 1 pillar update"

### Scenario 3: Solution Works

**What happens**:
1. You save working code → Trepan evaluates
2. AI detects: "Threading solution successful"
3. AI updates `golden_state.md`:
   ```
   ## Pattern: Threading for Background Tasks
   **Use Case**: Long-running operations in Flask
   **Implementation**: threading.Thread with daemon=True
   ```
4. You see: "🤖 Executed 1 pillar update"

### Scenario 4: Future Prevention

**Next time AI suggests async/await in Flask**:
1. Trepan checks `system_rules.md`
2. Finds Rule #3: "NEVER use async/await in Flask"
3. Blocks save with: "🛑 Drift Score: 0.85"
4. Shows reason: "Violates Rule #3"

## Commands

### VS Code Commands

| Command | What It Does |
|---------|--------------|
| `Trepan: Initialize Project` | Create `.trepan/` with pillars |
| `Trepan: Open Ledger` | Open `Walkthrough.md` |
| `Trepan: Review with Ledger` | Split view: code + ledger |
| `Trepan: Status` | Show server status |
| `Trepan: Toggle Enabled` | Enable/disable airbag |

### Keyboard Shortcuts

- `Ctrl+S` / `Cmd+S`: Save (triggers evaluation)
- `Ctrl+Shift+P`: Command Palette (access Trepan commands)

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `trepan.enabled` | `true` | Enable/disable airbag |
| `trepan.serverUrl` | `http://127.0.0.1:8000` | Trepan server URL |
| `trepan.timeoutMs` | `30000` | Evaluation timeout (ms) |
| `trepan.excludePatterns` | `[]` | Files to exclude |

## Status Bar Icons

| Icon | Meaning |
|------|---------|
| `$(shield) Trepan ✅` | Online and ready |
| `$(shield) Trepan 🔄` | Evaluating save |
| `$(shield) Trepan ⏳` | Model loading |
| `$(shield) Trepan ⚫` | Offline (fail-open) |

## Troubleshooting

### No pillar updates?

1. Check console: `Help → Toggle Developer Tools`
2. Look for `[TREPAN AI AUTONOMY]` logs
3. Verify server: `http://localhost:8000/health`
4. Check Ollama: `ollama list`

### File not found errors?

1. Run `Trepan: Initialize Project`
2. Or create `.trepan/` folder manually

### Permission denied?

1. Check file permissions on `.trepan/`
2. Run VS Code as admin (Windows) or with sudo (Linux)

### Actions not executing?

1. Open Developer Tools
2. Check Console for errors
3. Look for parsing failures

## Console Logs

All autonomy actions logged with `[TREPAN AI AUTONOMY]` prefix:

```
[TREPAN AI AUTONOMY] Found actions section: APPEND_TO_FILE...
[TREPAN AI AUTONOMY] Executing: APPEND_TO_FILE .trepan/problems_and_resolutions.md
[TREPAN AI AUTONOMY] ✅ Successfully appended to .trepan/problems_and_resolutions.md
```

## Git Integration

All pillar updates tracked in Git:

```bash
# See what AI changed
git diff .trepan/

# Review specific file
git diff .trepan/system_rules.md

# Revert if needed
git checkout .trepan/system_rules.md

# Commit changes
git add .trepan/
git commit -m "AI learned: no async/await in Flask"
```

## Benefits

✅ **Zero Manual Work**: AI maintains pillars automatically
✅ **Self-Learning**: System gets smarter over time
✅ **Prevents Mistakes**: Negative rules block repeated failures
✅ **Extracts Patterns**: Success patterns become templates
✅ **Tracks Evolution**: History shows project learning
✅ **Transparent**: All changes visible in Git
✅ **Reversible**: Can revert any automatic update
✅ **Fail-Safe**: Errors don't block saves

## Response Format

LLM generates actions in this format:

```
[THOUGHT]
Analysis of code...

[AI_ASSISTANT_ACTIONS]
APPEND_TO_FILE: .trepan/problems_and_resolutions.md
CONTENT: |
  ## Problem #7: Description (UNRESOLVED)
  **Date**: 2026-03-04
  **AI Generated**: Yes
  **Description**: What failed
  **Status**: UNRESOLVED

APPEND_TO_FILE: .trepan/system_rules.md
CONTENT: |
  ## AI-Learned Rule #8
  **NEVER** [approach] because [reason]
  **Learned**: 2026-03-04

[SCORE]
0.85

[ACTION]
REJECT
```

Extension automatically:
1. Parses `[AI_ASSISTANT_ACTIONS]`
2. Executes `APPEND_TO_FILE` commands
3. Shows notification
4. Logs to console

## Best Practices

1. **Review regularly**: Check Git diffs after each session
2. **Keep pillars clean**: Remove duplicates, merge similar rules
3. **Trust the system**: Let AI learn from mistakes
4. **Monitor logs**: Keep Developer Tools open during development
5. **Use Git**: Track all changes, revert if needed

## FAQ

**Q: Does this work with all AI assistants?**
A: Yes! Works with Copilot, Cursor, Codex, and any AI in VS Code.

**Q: Can I disable it?**
A: Yes, use `trepan.enabled` setting or exclude specific files.

**Q: What if AI generates wrong rules?**
A: Edit or delete any pillar entry. All changes tracked in Git.

**Q: Does this slow down saves?**
A: Minimal impact. Evaluation is async and fails open if slow.

**Q: Is my code sent to the cloud?**
A: No! Everything runs locally via Ollama.

## Documentation

- **Technical**: `AI_ASSISTANT_AUTONOMY_IMPLEMENTATION.md`
- **User Guide**: `USER_GUIDE_AI_AUTONOMY.md`
- **Flow Diagram**: `AI_AUTONOMY_FLOW_DIAGRAM.md`
- **Tests**: `test_ai_autonomy_parsing.js`

## Status

✅ **FULLY IMPLEMENTED** - Ready for production use!

---

**Quick Start**: Just code normally. AI will maintain pillars automatically! 🤖🛡️
