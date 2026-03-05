# Test Plan: Audit Loop Fix

## Test 1: Silent Pillar Reload

**Objective**: Verify that editing pillar files skips audit and reloads silently.

**Steps**:
1. Open `.trepan/system_rules.md`
2. Add a new rule at the end:
   ```markdown
   ## Rule #99: Test Rule for Audit Loop Fix
   This rule verifies that pillar files are not audited.
   **NEVER** audit pillar files - they are laws, not code.
   ```
3. Save the file (Ctrl+S)

**Expected Results**:
- ✅ Notification appears: "🛡️ Trepan: system_rules.md updated - pillars reloaded"
- ✅ File saves immediately (no delay)
- ✅ No audit performed
- ✅ Console shows: `[TREPAN META-GATE] Pillar file save detected: system_rules.md`
- ✅ Console shows: `[TREPAN META-GATE] Triggering silent pillar reload (no audit)`
- ✅ Status bar briefly shows green checkmark

**Failure Indicators**:
- ❌ Modal dialog appears asking to review changes
- ❌ Long delay before save completes
- ❌ Sidebar shows "Meta-Gate Audit" message
- ❌ Error message about drift score

---

## Test 2: Flexible Action Tag Parsing

**Objective**: Verify that extension accepts [ACTION], [ACTIONS], and [AI_ASSISTANT_ACTIONS].

**Steps**:
1. Create a test file: `test_action_tags.js`
2. Add some code:
   ```javascript
   function testFunction() {
       console.log("Testing action tag parsing");
   }
   ```
3. Save the file

**Expected Results**:
- ✅ Extension parses whichever tag format the model generates
- ✅ Console shows: `[TREPAN AI AUTONOMY] Found [ACTION] section` (or ACTIONS, or AI_ASSISTANT_ACTIONS)
- ✅ Fallback heuristics work if no explicit actions
- ✅ No errors in console

**Failure Indicators**:
- ❌ Console shows: `[TREPAN AI AUTONOMY] No [AI_ASSISTANT_ACTIONS] section found` when model used [ACTION]
- ❌ Explicit actions are ignored
- ❌ Only fallback heuristics execute

---

## Test 3: Graceful Fallback for Malformed Output

**Objective**: Verify that malformed model output doesn't crash the system.

**Manual Test** (requires modifying server temporarily):

1. Temporarily modify `trepan_server/server.py` to return garbage:
   ```python
   # In /evaluate endpoint, after generate_with_ollama():
   raw = "This is garbage output with no tags at all!"
   ```

2. Create a test file and save it

**Expected Results**:
- ✅ Parser returns verdict="WARN"
- ✅ Warning notification: "⚠️ Trepan: Model output was malformed, save allowed (fail-open)"
- ✅ File saves successfully (fail-open)
- ✅ Console shows: `[TREPAN WARNING] Parser returned WARN`
- ✅ No 500 errors
- ✅ No crash

**Failure Indicators**:
- ❌ 500 Internal Server Error
- ❌ Extension crashes
- ❌ Save is blocked
- ❌ Error dialog appears

---

## Test 4: Regular Code Files Still Audited

**Objective**: Verify that non-pillar files are still audited normally.

**Steps**:
1. Create a test file: `test_regular_audit.js`
2. Add code that violates a rule (if you have one):
   ```javascript
   // If you have a rule against eval()
   eval("console.log('test')");
   ```
3. Save the file

**Expected Results**:
- ✅ Extension sends code to server for audit
- ✅ Model evaluates the code
- ✅ If violation detected, save is blocked (or warning shown)
- ✅ Sidebar shows audit result
- ✅ Console shows: `[TREPAN DEBUG] Save event triggered`
- ✅ Console shows drift score and verdict

**Failure Indicators**:
- ❌ No audit performed
- ❌ Code saves without evaluation
- ❌ Trepan appears to be disabled

---

## Test 5: Multiple Pillar Files

**Objective**: Verify that all pillar files skip audit.

**Steps**:
1. Edit `.trepan/golden_state.md` - add a pattern
2. Save (should skip audit)
3. Edit `.trepan/problems_and_resolutions.md` - add a problem
4. Save (should skip audit)
5. Edit `.trepan/history_phases.md` - add an entry
6. Save (should skip audit)

**Expected Results**:
- ✅ All pillar files save immediately
- ✅ Notification for each: "🛡️ Trepan: [filename] updated - pillars reloaded"
- ✅ No audits performed
- ✅ Console shows silent reload for each

**Failure Indicators**:
- ❌ Any pillar file triggers audit
- ❌ Delays or errors

---

## Test 6: Fallback Heuristics Still Work

**Objective**: Verify that fallback heuristics work when model doesn't generate explicit actions.

**Steps**:
1. Create code that violates a rule
2. Save the file
3. Check if model generates [AI_ASSISTANT_ACTIONS]

**Expected Results**:
- ✅ If model generates explicit actions, they execute
- ✅ If not, fallback heuristics analyze [THOUGHT] section
- ✅ Console shows which strategy was used
- ✅ Pillar files are updated based on detected patterns
- ✅ Notification shows number of updates

**Failure Indicators**:
- ❌ No pillar updates occur
- ❌ Both strategies fail
- ❌ Errors in console

---

## Quick Verification Checklist

After implementing the fixes, verify:

- [ ] Editing `system_rules.md` shows notification and saves immediately
- [ ] Editing `golden_state.md` shows notification and saves immediately
- [ ] Editing regular code files still triggers audit
- [ ] Console shows `[TREPAN META-GATE] Pillar file save detected` for pillar files
- [ ] Console shows `[TREPAN META-GATE] Triggering silent pillar reload` for pillar files
- [ ] No errors in console when saving pillar files
- [ ] Status bar shows green checkmark briefly after pillar save
- [ ] Extension accepts [ACTION], [ACTIONS], and [AI_ASSISTANT_ACTIONS] tags
- [ ] Malformed model output shows warning but allows save (fail-open)

---

## Automated Test Script

```javascript
// test_audit_loop_fix.js
// Run with: node test_audit_loop_fix.js

const testCases = [
    {
        name: "Flexible Action Tag Parsing",
        input: "[ACTION] ACCEPT",
        expectedMatch: true
    },
    {
        name: "Flexible Actions Tag Parsing",
        input: "[ACTIONS] REJECT",
        expectedMatch: true
    },
    {
        name: "Flexible AI_ASSISTANT_ACTIONS Tag Parsing",
        input: "[AI_ASSISTANT_ACTIONS] ACCEPT",
        expectedMatch: true
    },
    {
        name: "No Action Tag",
        input: "Just some text without tags",
        expectedMatch: false
    }
];

console.log("Testing Flexible Action Tag Parsing\n");

testCases.forEach(test => {
    const pattern = /\[(AI_ASSISTANT_ACTIONS|ACTIONS|ACTION)\]([\s\S]*?)(?:\[|$)/;
    const match = test.input.match(pattern);
    const passed = (match !== null) === test.expectedMatch;
    
    console.log(`${passed ? '✅' : '❌'} ${test.name}`);
    if (match) {
        console.log(`   Found: [${match[1]}]`);
    }
    console.log();
});

console.log("All tests completed!");
```

---

## Success Criteria

The audit loop fix is successful if:

1. ✅ Pillar files save immediately without audit
2. ✅ Regular code files are still audited
3. ✅ Extension accepts multiple action tag formats
4. ✅ Malformed output doesn't crash the system
5. ✅ Fallback heuristics still work
6. ✅ No 500 errors
7. ✅ User experience is smooth

---

**Status**: Ready for testing! 🧪
