# AI Autonomy Fallback Implementation

## Problem Statement

The Llama 3.1 model was fine-tuned on:
- `[THOUGHT]` - Reasoning section
- `[SCORE]` - Drift score (0.00 to 1.00)
- `[ACTION]` - Verdict (ACCEPT/REJECT)

But NOT on:
- `[AI_ASSISTANT_ACTIONS]` - Autonomous pillar update instructions

This means the model might not reliably generate the `[AI_ASSISTANT_ACTIONS]` section.

## Solution: Dual-Strategy Approach

The extension now uses a **dual-strategy** approach:

### Strategy 1: Explicit Actions (If Model Generates Them)

If the model generates `[AI_ASSISTANT_ACTIONS]`, use them directly:

```
[AI_ASSISTANT_ACTIONS]
APPEND_TO_FILE: .trepan/problems_and_resolutions.md
CONTENT: |
  ## Problem #7: Description
  ...
```

### Strategy 2: Fallback Heuristics (If No Actions Section)

If no `[AI_ASSISTANT_ACTIONS]` section is found, analyze the `[THOUGHT]` section using keyword-based heuristics:

## Fallback Heuristics

### Heuristic 1: Rule Violation Detection

**Triggers**:
- Verdict: `REJECT`
- Drift Score: >= 0.40
- Keywords in `[THOUGHT]`: "violates", "breaks", "forbidden", "not allowed", "against rule"

**Action**:
```markdown
Append to .trepan/problems_and_resolutions.md:

## Problem: Rule Violation Detected (2026-03-04)
**Status**: UNRESOLVED
**Drift Score**: 0.85
**Description**: Code violates architectural rules
**AI Analysis**: [First 200 chars of THOUGHT]...
```

### Heuristic 2: Error/Failure Detection

**Triggers**:
- Keywords in `[THOUGHT]`: "error", "failed", "doesn't work", "broken", "issue", "problem"

**Action**:
```markdown
Append to .trepan/problems_and_resolutions.md:

## Problem: Error Detected (2026-03-04)
**Status**: UNRESOLVED
**Description**: AI detected potential error in code
**AI Analysis**: [First 200 chars of THOUGHT]...
```

### Heuristic 3: Pattern Compliance Detection

**Triggers**:
- Verdict: `ACCEPT`
- Drift Score: <= 0.15
- Keywords in `[THOUGHT]`: "follows pattern", "correct approach", "good practice", "recommended", "aligns with"

**Action**:
```markdown
Append to .trepan/history_phases.md:

## Success: Pattern Followed (2026-03-04)
**Drift Score**: 0.05
**Description**: Code follows architectural patterns correctly
**AI Analysis**: [First 200 chars of THOUGHT]...
```

## Implementation Details

### Function Signature

```javascript
async function executeAIAssistantActions(llmResponse, verdict, score)
```

**Parameters**:
- `llmResponse`: Full LLM response text (includes [THOUGHT], [SCORE], [ACTION])
- `verdict`: The verdict string ("ACCEPT" or "REJECT")
- `score`: The drift score (0.00 to 1.00)

### Execution Flow

```
1. Check if [AI_ASSISTANT_ACTIONS] section exists
   ├─ YES → Parse and execute explicit actions
   └─ NO → Use fallback heuristics

2. Fallback Heuristics:
   ├─ Extract [THOUGHT] section
   ├─ Convert to lowercase for keyword matching
   ├─ Check Heuristic 1: Rule Violation?
   ├─ Check Heuristic 2: Error/Failure?
   └─ Check Heuristic 3: Pattern Compliance?

3. For each triggered heuristic:
   ├─ Generate appropriate content
   ├─ Append to target pillar file
   └─ Increment execution counter

4. If any actions executed:
   └─ Show notification to user
```

### Helper Function

```javascript
async function appendToFile(projectRoot, filePath, content)
```

**Purpose**: Safely append content to a pillar file with error handling

**Features**:
- Checks if file exists
- Handles newline formatting
- Logs success/failure
- Returns boolean for tracking

## Example Scenarios

### Scenario 1: Model Generates [AI_ASSISTANT_ACTIONS]

**LLM Response**:
```
[THOUGHT]
The code violates system_rules.md Rule #3.

[AI_ASSISTANT_ACTIONS]
APPEND_TO_FILE: .trepan/problems_and_resolutions.md
CONTENT: |
  ## Problem #7: Async in Flask (UNRESOLVED)
  **Date**: 2026-03-04
  **Description**: Tried async/await in Flask

[SCORE]
0.85

[ACTION]
REJECT
```

**Result**: Extension uses explicit actions from `[AI_ASSISTANT_ACTIONS]`

### Scenario 2: Model Doesn't Generate [AI_ASSISTANT_ACTIONS]

**LLM Response**:
```
[THOUGHT]
The incoming code violates system_rules.md Rule #3 which states
"NEVER use async/await in synchronous Flask routes". This is
forbidden because Flask is not async-native.

[SCORE]
0.85

[ACTION]
REJECT
```

**Result**: Extension detects:
- Verdict: REJECT
- Score: 0.85 (>= 0.40)
- Keywords: "violates", "forbidden"

**Action**: Appends to `problems_and_resolutions.md`:
```markdown
## Problem: Rule Violation Detected (2026-03-04)
**Status**: UNRESOLVED
**Drift Score**: 0.85
**Description**: Code violates architectural rules
**AI Analysis**: The incoming code violates system_rules.md Rule #3 which states
"NEVER use async/await in synchronous Flask routes". This is
forbidden because Flask is not async-native...
```

### Scenario 3: Low Drift Score + Pattern Compliance

**LLM Response**:
```
[THOUGHT]
The code follows the recommended pattern from golden_state.md
for background tasks using threading.Thread. This is the correct
approach for Flask applications.

[SCORE]
0.05

[ACTION]
ACCEPT
```

**Result**: Extension detects:
- Verdict: ACCEPT
- Score: 0.05 (<= 0.15)
- Keywords: "follows", "recommended", "correct approach"

**Action**: Appends to `history_phases.md`:
```markdown
## Success: Pattern Followed (2026-03-04)
**Drift Score**: 0.05
**Description**: Code follows architectural patterns correctly
**AI Analysis**: The code follows the recommended pattern from golden_state.md
for background tasks using threading.Thread. This is the correct
approach for Flask applications...
```

## Benefits of Fallback Strategy

### 1. Works Without Fine-Tuning
- No need to retrain model on `[AI_ASSISTANT_ACTIONS]`
- Uses existing `[THOUGHT]` section that model already generates
- Leverages your existing fine-tuning investment

### 2. Deterministic and Reliable
- Keyword matching is predictable
- No hallucination risk
- Easy to debug and refine

### 3. Graceful Degradation
- If model generates `[AI_ASSISTANT_ACTIONS]`, use them
- If not, fall back to heuristics
- Always provides some level of autonomy

### 4. Easy to Extend
- Add new heuristics by adding keyword patterns
- Adjust thresholds based on observed behavior
- No server-side changes needed

## Limitations and Future Improvements

### Current Limitations

1. **Less Precise**: Heuristics are simpler than explicit actions
2. **Fixed Thresholds**: Score thresholds (0.40, 0.15) might need tuning
3. **Keyword-Based**: Might miss nuanced situations

### Future Improvements

1. **Fine-Tune on [AI_ASSISTANT_ACTIONS]**:
   - Create training dataset with `[AI_ASSISTANT_ACTIONS]` examples
   - Fine-tune model to generate explicit actions
   - Gradually phase out fallback heuristics

2. **Machine Learning Heuristics**:
   - Use simple ML classifier on `[THOUGHT]` text
   - Train on observed patterns
   - More accurate than keyword matching

3. **Server-Side Analysis**:
   - Add `/analyze_reasoning` endpoint
   - Use NLP to extract structured information
   - Return actions for extension to execute

4. **User Feedback Loop**:
   - Let users approve/reject automatic updates
   - Learn from user corrections
   - Improve heuristics over time

## Configuration

### Adjusting Thresholds

Edit `extension/extension.js` to tune thresholds:

```javascript
// Heuristic 1: Rule Violation Detection
if (verdict === 'REJECT' && score >= 0.40) {  // Adjust 0.40 threshold
    // ...
}

// Heuristic 3: Pattern Compliance Detection
if (verdict === 'ACCEPT' && score <= 0.15) {  // Adjust 0.15 threshold
    // ...
}
```

### Adding New Keywords

```javascript
// Add more keywords to detect patterns
const errorKeywords = ['error', 'failed', 'doesn\'t work', 'broken', 'issue', 'problem', 'crash', 'exception'];
const patternKeywords = ['follows pattern', 'correct approach', 'good practice', 'recommended', 'aligns with', 'best practice'];
```

### Disabling Fallback

To disable fallback heuristics (only use explicit actions):

```javascript
if (actionsMatch) {
    // Use explicit actions
} else {
    console.log('[TREPAN AI AUTONOMY] No actions found - skipping (fallback disabled)');
    return;  // Skip fallback
}
```

## Testing the Fallback

### Test 1: Rule Violation

1. Create code that violates a rule in `system_rules.md`
2. Save the file
3. Check console for: `[TREPAN AI AUTONOMY] Detected rule violation`
4. Verify `problems_and_resolutions.md` was updated

### Test 2: Error Detection

1. Create code with obvious errors
2. Save the file
3. Check console for: `[TREPAN AI AUTONOMY] Detected error pattern`
4. Verify `problems_and_resolutions.md` was updated

### Test 3: Pattern Compliance

1. Create code that follows `golden_state.md` patterns
2. Save the file
3. Check console for: `[TREPAN AI AUTONOMY] Detected pattern compliance`
4. Verify `history_phases.md` was updated

## Console Logging

The fallback strategy logs its decisions:

```
[TREPAN AI AUTONOMY] No [AI_ASSISTANT_ACTIONS] found - using fallback heuristics
[TREPAN AI AUTONOMY] Detected rule violation - recording in problems
[TREPAN AI AUTONOMY] ✅ Successfully appended to .trepan/problems_and_resolutions.md
```

Or if explicit actions are found:

```
[TREPAN AI AUTONOMY] Found [AI_ASSISTANT_ACTIONS] section - using explicit actions
[TREPAN AI AUTONOMY] ✅ Successfully appended to .trepan/problems_and_resolutions.md
```

## Status

✅ **IMPLEMENTED** - Fallback strategy is now active!

The system will:
1. Try to use explicit `[AI_ASSISTANT_ACTIONS]` if present
2. Fall back to keyword-based heuristics if not
3. Always provide some level of autonomous pillar updates

## Recommendation

**Short-term**: Use the fallback strategy as-is. It works with your existing fine-tuned model.

**Long-term**: Consider fine-tuning the model on `[AI_ASSISTANT_ACTIONS]` examples to get more precise autonomous updates. The fallback will still work as a safety net.

---

**The AI autonomy system now works WITHOUT requiring model fine-tuning on [AI_ASSISTANT_ACTIONS]!** 🤖🛡️
