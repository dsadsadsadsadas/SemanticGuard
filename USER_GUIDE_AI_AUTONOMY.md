# User Guide: AI Assistant Autonomy

## What is AI Assistant Autonomy?

Trepan now enables your AI coding assistants (GitHub Copilot, Cursor, Codex, etc.) to act as **autonomous agents** that automatically maintain your project's architectural pillars. Instead of you manually updating rules and patterns, the AI learns from its own experience and updates the pillars automatically.

## How It Works

### The Autonomous Loop

```
1. AI generates code
   ↓
2. You save the file
   ↓
3. Trepan evaluates the code
   ↓
4. AI detects patterns (errors, solutions, completions)
   ↓
5. AI generates pillar updates
   ↓
6. Extension executes updates automatically
   ↓
7. Pillars evolve without manual intervention
```

### What Gets Updated Automatically

The AI assistant automatically maintains these files:

1. **problems_and_resolutions.md** - Records errors and struggles
2. **system_rules.md** - Generates negative rules from failures
3. **golden_state.md** - Extracts success patterns from solutions
4. **history_phases.md** - Tracks task completions and evolution

## Real-World Examples

### Example 1: AI Learns from Its Own Error

**Scenario**: You're building a Flask API and the AI suggests using `async/await`.

**What happens**:

1. **AI generates code**:
   ```python
   @app.route('/api/data')
   async def get_data():
       result = await fetch_from_db()
       return jsonify(result)
   ```

2. **You save the file** → Trepan intercepts

3. **Trepan evaluates** → Detects that Flask is synchronous, not async

4. **AI automatically updates** `problems_and_resolutions.md`:
   ```markdown
   ## Problem #5: Async/await in Flask (UNRESOLVED)
   **Date**: 2026-03-04
   **AI Generated**: Yes
   **Description**: Tried to use async/await in Flask route
   **Approach**: Used async def with await
   **Result**: Flask doesn't support async routes natively
   **Status**: UNRESOLVED
   ```

5. **You see notification**: "🤖 Trepan AI Autonomy: Executed 1 pillar update(s)"

6. **You can review**: Click "View Changes" to see the Git diff

### Example 2: AI Generates Negative Rule

**Scenario**: You reject the async approach and use threading instead.

**What happens**:

1. **You write correct code**:
   ```python
   @app.route('/api/data')
   def get_data():
       thread = threading.Thread(target=fetch_from_db, daemon=True)
       thread.start()
       return jsonify({"status": "processing"})
   ```

2. **You save the file** → Trepan intercepts

3. **Trepan evaluates** → Detects pattern change from failed approach

4. **AI automatically updates** `system_rules.md`:
   ```markdown
   ## AI-Learned Rule #3
   **NEVER** use async/await in synchronous Flask routes because Flask is not async-native
   **Context**: Background tasks, long-running operations
   **Learned**: 2026-03-04
   ```

5. **Future prevention**: If AI suggests async/await in Flask again, Trepan will reject it with reference to Rule #3

### Example 3: AI Extracts Success Pattern

**Scenario**: Your threading solution works perfectly.

**What happens**:

1. **You save the working code** → Trepan intercepts

2. **Trepan evaluates** → Detects successful pattern

3. **AI automatically updates** `golden_state.md`:
   ```markdown
   ## AI-Discovered Pattern: Threading for Background Tasks
   **Learned**: 2026-03-04
   **Use Case**: Long-running operations in Flask
   **Implementation**: Use threading.Thread with daemon=True
   **Why It Works**: Keeps Flask synchronous while allowing background work
   **Example**:
   ```python
   thread = threading.Thread(target=long_task, daemon=True)
   thread.start()
   ```
   ```

4. **Future guidance**: AI will use this pattern for similar problems

### Example 4: AI Updates History

**Scenario**: You complete the API implementation.

**What happens**:

1. **You save the final code** → Trepan intercepts

2. **Trepan evaluates** → Detects task completion

3. **AI automatically updates** `history_phases.md`:
   ```markdown
   ## AI Task: 2026-03-04
   **Completed**: Implemented background task API
   **Approach**: Threading with daemon threads
   **Problems**: Had to switch from async to threading (see Problem #5)
   **Outcome**: Working API with non-blocking background tasks
   ```

4. **Project history**: Tracks evolution with problem links

## User Experience

### What You See

When the AI updates pillars, you'll see:

1. **Notification**:
   ```
   🤖 Trepan AI Autonomy: Executed 2 pillar update(s)
   [View Changes]
   ```

2. **Console logs** (if you have Developer Tools open):
   ```
   [TREPAN AI AUTONOMY] Found actions section: APPEND_TO_FILE...
   [TREPAN AI AUTONOMY] Executing: APPEND_TO_FILE .trepan/problems_and_resolutions.md
   [TREPAN AI AUTONOMY] ✅ Successfully appended to .trepan/problems_and_resolutions.md
   ```

3. **Git changes**: All pillar updates appear in Source Control

### What You Control

You have full control:

- **Review changes**: Click "View Changes" to see Git diff
- **Revert if needed**: Use Git to undo any automatic updates
- **Edit manually**: You can still edit pillar files directly
- **Disable if needed**: Turn off Trepan in settings

## Benefits

### 1. Zero Manual Work

**Before AI Autonomy**:
- You write code
- AI suggests something that fails
- You manually copy error to `problems_and_resolutions.md`
- You manually write negative rule in `system_rules.md`
- You manually update `history_phases.md`

**With AI Autonomy**:
- You write code
- AI detects its own error
- AI updates all pillars automatically
- You just review the changes

### 2. Continuous Learning

The system gets smarter over time:

- **Week 1**: AI suggests async/await in Flask → fails → learns
- **Week 2**: AI suggests threading → works → extracts pattern
- **Week 3**: AI automatically uses threading pattern for similar problems
- **Week 4**: AI has learned 10+ patterns and 5+ negative rules

### 3. Prevents Repeated Mistakes

Once the AI learns a lesson, it never forgets:

- **First time**: AI suggests `eval()` → rejected → Rule: "NEVER use eval()"
- **Second time**: AI tries `eval()` again → Trepan blocks with reference to rule
- **Third time**: AI doesn't even suggest `eval()` anymore

### 4. Transparent Operation

Everything is visible:

- **Notifications**: You see when pillars are updated
- **Git tracking**: All changes are version controlled
- **Console logs**: Full debugging information available
- **Sidebar reasoning**: See why AI made each decision

## Configuration

### Enable/Disable

AI Autonomy is enabled by default. To disable:

1. Open VS Code Settings
2. Search for "Trepan"
3. Uncheck "Trepan: Enabled"

### Adjust Timeout

If LLM responses are slow:

1. Open VS Code Settings
2. Search for "Trepan: Timeout Ms"
3. Increase from 30000 (30s) to 60000 (60s)

### Exclude Files

To prevent Trepan from evaluating certain files:

1. Open VS Code Settings
2. Search for "Trepan: Exclude Patterns"
3. Add patterns like `**/test/**`, `**/*.test.js`

## Troubleshooting

### "No pillar updates executed"

**Cause**: LLM didn't generate `[AI_ASSISTANT_ACTIONS]` section

**Solution**:
1. Check console logs for `[TREPAN AI AUTONOMY]` messages
2. Verify Trepan server is running: `http://localhost:8000/health`
3. Check if Ollama is running: `ollama list`

### "File not found" errors

**Cause**: Pillar files don't exist yet

**Solution**:
1. Run "Trepan: Initialize Project" from Command Palette
2. Or manually create `.trepan/` folder with pillar files

### "Permission denied" errors

**Cause**: File system permissions issue

**Solution**:
1. Check file permissions on `.trepan/` folder
2. Run VS Code as administrator (Windows) or with sudo (Linux)

### Actions not executing

**Cause**: Extension not parsing response correctly

**Solution**:
1. Open Developer Tools: Help → Toggle Developer Tools
2. Check Console for `[TREPAN AI AUTONOMY]` logs
3. Look for parsing errors or regex match failures

## Advanced Usage

### Custom Action Types

Currently supported:
- `APPEND_TO_FILE`: Adds content to end of file

Future support planned:
- `UPDATE_FILE`: Replaces specific section
- `DELETE_ENTRY`: Removes specific entry
- `CREATE_FILE`: Creates new file

### Manual Pillar Updates

You can still edit pillars manually:

1. Open `.trepan/system_rules.md` (or any pillar file)
2. Make your changes
3. Save the file
4. Trepan will evaluate the change via Meta-Gate
5. If approved, vault is re-signed automatically

### Reviewing AI Decisions

To see why AI made a decision:

1. Open Trepan sidebar (View → Trepan Explorer)
2. Click "💭 See Reasoning" on any audit entry
3. Read the `[THOUGHT]` section
4. Check the `[AI_ASSISTANT_ACTIONS]` section

### Git Integration

All pillar updates are tracked in Git:

```bash
# See what AI changed
git diff .trepan/

# Review specific file
git diff .trepan/system_rules.md

# Revert if needed
git checkout .trepan/system_rules.md
```

## Best Practices

### 1. Review Pillar Updates Regularly

- Check Git diffs after each session
- Ensure AI-generated rules make sense
- Edit or remove incorrect entries

### 2. Keep Pillars Clean

- Remove duplicate entries
- Merge similar rules
- Archive old problems that are no longer relevant

### 3. Trust the System

- Let AI learn from mistakes
- Don't manually intervene too quickly
- Give the system time to evolve

### 4. Monitor Console Logs

- Keep Developer Tools open during development
- Watch for `[TREPAN AI AUTONOMY]` messages
- Report any parsing errors or failures

## FAQ

**Q: Does this work with all AI assistants?**
A: Yes! Works with GitHub Copilot, Cursor, Codex, and any AI that generates code in VS Code.

**Q: Can I disable autonomy for specific files?**
A: Yes, use the "Trepan: Exclude Patterns" setting to exclude files or folders.

**Q: What if AI generates incorrect rules?**
A: You can manually edit or delete any pillar entry. All changes are tracked in Git.

**Q: Does this slow down saves?**
A: Minimal impact. Evaluation happens asynchronously and fails open if slow.

**Q: Can I see what AI is thinking?**
A: Yes! Open the Trepan sidebar and click "💭 See Reasoning" on any audit entry.

**Q: What if I disagree with AI's decision?**
A: You can override saves with "Force Override" button, or disable Trepan temporarily.

**Q: Is my code sent to the cloud?**
A: No! Everything runs locally via Ollama. Your code never leaves your machine.

**Q: Can I customize the autonomy behavior?**
A: Yes, by editing `trepan_server/prompt_builder.py` to change the AI Autonomy Protocol.

## Status

✅ **FULLY IMPLEMENTED** - AI Assistant Autonomy is now active!

All components are working:
- Prompt builder with autonomy protocol
- Extension action executor
- Automatic pillar updates
- User notifications
- Console logging
- Error handling

## Next Steps

1. **Start coding** - Let the AI generate code as usual
2. **Save files** - Trepan will intercept and evaluate
3. **Watch pillars evolve** - Check `.trepan/` folder for updates
4. **Review changes** - Use Git to see what AI learned
5. **Enjoy autonomous learning** - System gets smarter over time!

## Support

If you encounter issues:

1. Check console logs for `[TREPAN AI AUTONOMY]` messages
2. Verify Trepan server is running: `http://localhost:8000/health`
3. Check Ollama is running: `ollama list`
4. Review `AI_ASSISTANT_AUTONOMY_IMPLEMENTATION.md` for technical details
5. Open an issue with console logs and error messages

---

**Welcome to the future of autonomous AI coding assistants!** 🤖🛡️
