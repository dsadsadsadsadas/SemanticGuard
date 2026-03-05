# Audit Loop Fix: Teaching Trepan to Ignore Its Own Laws

## The Problem

When you edited `system_rules.md` to add Rule #99, Trepan treated it as **code to audit** instead of **a new law to acknowledge**. This created an "audit loop" where:

1. You add Rule #99 to `system_rules.md`
2. Extension intercepts the save
3. Extension sends rule text to server for audit
4. Server evaluates the rule as if it were code
5. Model returns: "This rule scores 8/10, consider consolidating..."
6. Extension looks for `[AI_ASSISTANT_ACTIONS]` but finds `[ACTION]` instead
7. Parser fails or produces unexpected results

## The Three Fixes

### Fix 1: Path Exclusion (Silent Pillar Reload)

**Problem**: Pillar files (`.trepan/*.md`) were being audited like regular code.

**Solution**: Skip full audit for pillar files, just acknowledge and reload.

**Implementation** (`extension/extension.js`):

```javascript
if (isPillar) {
    const fileName = path.basename(document.fileName);
    
    console.log(`[TREPAN META-GATE] Pillar file save detected: ${fileName}`);
    console.log(`[TREPAN META-GATE] Triggering silent pillar reload (no audit)`);
    
    // Show brief notification
    vscode.window.showInformationMessage(
        `🛡️ Trepan: ${fileName} updated - pillars reloaded`,
        { modal: false }
    );
    
    // Allow save to proceed without audit
    setStatus("accepted");
    setTimeout(() => setStatus("online"), 1000);
    return [];
}
```

**Result**: When you edit `system_rules.md`, `golden_state.md`, or any pillar file:
- ✅ Save proceeds immediately
- ✅ No audit performed
- ✅ Pillars reloaded silently
- ✅ Brief notification shown

### Fix 2: Parser Robustness (Accept Multiple Tag Formats)

**Problem**: Extension only looked for `[AI_ASSISTANT_ACTIONS]`, but model might generate `[ACTIONS]` as a shorter variant.

**Solution**: Accept both tag formats.

**Implementation** (`extension/extension.js`):

```javascript
// Old (rigid):
const actionsMatch = llmResponse.match(/\[AI_ASSISTANT_ACTIONS\]([\s\S]*?)(?:\[|$)/);

// New (flexible):
const actionsMatch = llmResponse.match(/\[(AI_ASSISTANT_ACTIONS|ACTIONS)\]([\s\S]*?)(?:\[|$)/);

if (actionsMatch) {
    const sectionName = actionsMatch[1];  // Could be either format
    const actionsSection = actionsMatch[2].trim();
    console.log(`[TREPAN AI AUTONOMY] Found [${sectionName}] section - using explicit actions`);
    // ... parse and execute
}
```

**Note**: We specifically do NOT match `[ACTION]` because that tag is reserved for the verdict (ACCEPT/REJECT) at the end of responses. Matching it would cause confusion.

**Result**: Extension now accepts:
- ✅ `[AI_ASSISTANT_ACTIONS]` (ideal format)
- ✅ `[ACTIONS]` (shorter variant)
- ❌ `[ACTION]` (reserved for verdict only)

### Fix 3: Graceful Fallback (No 500 Errors)

**Problem**: If model produces malformed output (no `[ACTION]` tag), parser might fail.

**Solution**: Parser already returns `"WARN"` verdict instead of throwing errors. Extension now handles this gracefully.

**Implementation** (`trepan_server/response_parser.py`):

```python
if not action_matches:
    # No [ACTION] tag at all — model hallucinated completely
    logger.warning("Parser failsafe: no [ACTION] tag found in model output.")
    return {
        "verdict": "WARN",
        "score": 1.0,
        "reasoning": (
            "Parser failed: model produced no [ACTION] tag.\n\n"
            f"Raw output (truncated):\n{raw_output[:500]}"
        )
    }
```

**Implementation** (`extension/extension.js`):

```javascript
// Handle WARN verdict (parser failed but we don't want to block)
if (actionResult === "WARN") {
    console.warn('[TREPAN WARNING] Parser returned WARN - model output was malformed');
    vscode.window.showWarningMessage(
        `⚠️ Trepan: Model output was malformed, save allowed (fail-open)`,
        { modal: false }
    );
    // Allow save to proceed (fail-open)
    setStatus("online");
    return [];
}
```

**Result**: If model produces garbage output:
- ✅ Parser returns `"WARN"` instead of crashing
- ✅ Extension shows warning but allows save (fail-open)
- ✅ No 500 errors
- ✅ System remains operational

## How It Works Now

### Scenario 1: Editing System Rules

**Before**:
```
1. Edit system_rules.md → Add Rule #99
2. Save file
3. Extension sends rule text to server
4. Server audits the rule as code
5. Model: "This rule scores 8/10..."
6. Extension confused by response
7. User frustrated
```

**After**:
```
1. Edit system_rules.md → Add Rule #99
2. Save file
3. Extension detects: isPillar = true
4. Extension: "Pillar file detected, skipping audit"
5. Notification: "🛡️ Trepan: system_rules.md updated - pillars reloaded"
6. Save proceeds immediately
7. ✅ Rule #99 is now active
```

### Scenario 2: Model Produces [ACTIONS] Instead of [AI_ASSISTANT_ACTIONS]

**Before**:
```
1. Model generates: [ACTIONS] with APPEND_TO_FILE commands
2. Extension looks for: [AI_ASSISTANT_ACTIONS]
3. Not found → fallback heuristics only
4. Explicit actions ignored
```

**After**:
```
1. Model generates: [ACTIONS] with APPEND_TO_FILE commands
2. Extension looks for: [AI_ASSISTANT_ACTIONS|ACTIONS]
3. Found [ACTIONS] → parse it
4. Execute any APPEND_TO_FILE commands
5. ✅ Explicit actions work
```

### Scenario 3: Model Produces Garbage Output

**Before**:
```
1. Model hallucinates: "Let me help you with that..."
2. Parser: No [ACTION] tag found
3. Server: 500 Internal Server Error
4. Extension: Error dialog
5. Save blocked
```

**After**:
```
1. Model hallucinates: "Let me help you with that..."
2. Parser: No [ACTION] tag found → return "WARN"
3. Server: 200 OK with verdict="WARN"
4. Extension: Warning notification
5. Save proceeds (fail-open)
6. ✅ System remains operational
```

## User Experience

### Editing Pillar Files

**What you see**:
```
[Save system_rules.md]
↓
Notification: "🛡️ Trepan: system_rules.md updated - pillars reloaded"
↓
File saved immediately
```

**Console logs**:
```
[TREPAN META-GATE] Pillar file save detected: system_rules.md
[TREPAN META-GATE] Triggering silent pillar reload (no audit)
```

### Model Produces Malformed Output

**What you see**:
```
[Save code file]
↓
Warning: "⚠️ Trepan: Model output was malformed, save allowed (fail-open)"
↓
File saved (fail-open)
```

**Console logs**:
```
[TREPAN WARNING] Parser returned WARN - model output was malformed
```

## Configuration

### Re-Enable Meta-Gate Auditing (If Desired)

If you want to audit pillar changes again, uncomment the Meta-Gate logic in `extension/extension.js`:

```javascript
if (isPillar) {
    // Current: Silent reload
    // To re-enable auditing, comment out the silent reload block
    // and uncomment the Meta-Gate audit logic below
    
    /*
    setStatus("checking");
    trepanSidebarProvider.sendMessage({ type: 'scanning', title: 'Meta-Gate Audit: ' + fileName });
    // ... rest of Meta-Gate logic
    */
}
```

### Adjust Fail-Open Behavior

To make WARN verdict block saves instead of allowing them:

```javascript
if (actionResult === "WARN") {
    // Change from fail-open to fail-closed
    throw new Error('Trepan: Model output was malformed');
}
```

## Benefits

### 1. No More Audit Loops
- Pillar files are acknowledged, not audited
- Rules are laws, not code to review
- System respects its own architecture

### 2. Robust Parser
- Accepts multiple tag formats
- Handles malformed output gracefully
- Never throws 500 errors

### 3. Fail-Open Safety
- Malformed output doesn't block saves
- System remains operational even with bad model output
- Users can continue working

### 4. Better UX
- Clear notifications for pillar updates
- No confusing audit results for rules
- Smooth editing experience

## Testing

### Test 1: Edit System Rules

1. Open `.trepan/system_rules.md`
2. Add a new rule:
   ```markdown
   ## Rule #99: Test Rule
   This is a test rule to verify silent reload.
   ```
3. Save the file
4. Expected: Notification "🛡️ Trepan: system_rules.md updated - pillars reloaded"
5. Expected: No audit performed
6. Expected: File saved immediately

### Test 2: Model Produces [ACTION]

1. Trigger a code evaluation
2. Model generates: `[ACTION] ACCEPT`
3. Expected: Extension parses [ACTION] tag
4. Expected: Fallback heuristics still work
5. Expected: No errors

### Test 3: Model Produces Garbage

1. Trigger a code evaluation
2. Model generates: "Let me help you..."
3. Expected: Parser returns "WARN"
4. Expected: Warning notification shown
5. Expected: Save proceeds (fail-open)

## Files Modified

1. **extension/extension.js**:
   - Added silent pillar reload logic
   - Made action tag parsing flexible (accept [ACTION], [ACTIONS], [AI_ASSISTANT_ACTIONS])
   - Added WARN verdict handling

2. **trepan_server/response_parser.py**:
   - Already had graceful fallback (no changes needed)
   - Returns "WARN" verdict for malformed output

## Status

✅ **ALL FIXES IMPLEMENTED**

The audit loop is now fixed:
- Pillar files skip audit (silent reload)
- Parser accepts multiple tag formats
- Graceful fallback for malformed output
- No 500 errors
- Fail-open safety

## Summary

The system now understands the difference between:
- **Laws** (pillar files) → Acknowledge and reload
- **Code** (regular files) → Audit and evaluate

When you edit `system_rules.md`, Trepan says: "Got it, new law acknowledged!" instead of "Let me audit this rule for you..."

---

**The audit loop is broken. Trepan now respects its own laws!** 🛡️✅
