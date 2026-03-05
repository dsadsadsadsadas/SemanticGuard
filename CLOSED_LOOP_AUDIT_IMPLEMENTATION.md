# Trepan Closed-Loop Audit Implementation

## Overview
This document describes the implementation of the closed-loop audit system for Trepan, which verifies AI reasoning against the Reference Architecture baseline to detect hallucinations and context drift.

---

## Task 1: Initialization Check ✅

### Status: COMPLETE

### What Was Done:
Enhanced the `initialize_audit_ledger()` function in `trepan_server/server.py` to create a comprehensive Reference Architecture section in `Walkthrough.md`.

### Template Structure:
```markdown
# Trepan Architectural Audit & Tutorial

## Reference Architecture (The Ground Truth)
- Core Principles (4 key principles)
- Perfect Execution Example
- Hallucination Indicators

# Live Audit History
(Timestamped entries appended here)
```

### Key Features:
1. **Core Principles Section**: Defines the baseline for all AI reasoning
   - Contextual Alignment
   - Rule Compliance
   - Architectural Consistency
   - Security First

2. **Perfect Execution Example**: Shows what correct reasoning looks like

3. **Hallucination Indicators**: Lists red flags to watch for:
   - Contradictions with README/golden_state.md
   - Ignoring system_rules.md
   - Introducing mismatched patterns
   - Accepting security violations
   - Vague reasoning without rule references

### Location:
- File: `trepan_server/server.py`
- Function: `initialize_audit_ledger(trepan_dir: str)`
- Lines: ~180-230

---

## Task 2: Comparison Logic ✅

### Status: COMPLETE

### What Was Done:
Implemented `verify_against_ledger()` function that performs closed-loop auditing by comparing current AI reasoning against the Reference Architecture.

### How It Works:

#### Step 1: Read Reference Architecture
```python
# Reads first 50 lines of Walkthrough.md (the ground truth)
with open(ledger_path, 'r', encoding="utf-8") as f:
    lines = f.readlines()
    reference_architecture = "".join(lines[:50])
```

#### Step 2: LLM Comparison
Sends both the reference and current reasoning to the LLM with a specialized audit prompt:
```
SYSTEM: You are the TREPAN AUDITOR.
Compare CURRENT AI REASONING against REFERENCE ARCHITECTURE baseline.

Check for:
- Hallucinations (making up facts)
- Rule violations (ignoring principles)
- Architectural drift (contradicting patterns)
```

#### Step 3: Parse Result
Uses the production-hardened `guillotine_parser()` to extract:
- Verdict: ACCEPT or REJECT
- Score: 0.0 (clean) to 1.0 (high drift)
- Reasoning: Explanation of the decision

### API Endpoint:
```
POST /audit_reasoning
Body: { "ai_explanation": "..." }
Response: { "action": "ACCEPT/REJECT", "drift_score": 0.0-1.0, "raw_output": "..." }
```

### Integration Points:
1. Can be called after any `/evaluate` or `/evaluate_pillar` request
2. Provides a second layer of validation
3. Detects drift that might slip past the primary gate

### Location:
- File: `trepan_server/server.py`
- Function: `verify_against_ledger(current_reasoning: str)`
- Lines: ~260-310
- Endpoint: `/audit_reasoning` (lines ~580-600)

---

## Task 3: Review Changes Bridge ✅

### Status: COMPLETE

### What Was Done:
Added `trepan.reviewWithLedger` command to the VS Code extension that opens code and Walkthrough.md side-by-side with auto-scroll to the most recent entry.

### Features:

#### 1. Split Editor Layout
```
┌─────────────────┬─────────────────┐
│                 │                 │
│   Code File     │  Walkthrough.md │
│   (Left)        │  (Right)        │
│                 │                 │
│   Active Editor │  Auto-scrolled  │
│                 │  to bottom      │
└─────────────────┴─────────────────┘
```

#### 2. Auto-Scroll to Latest Entry
```javascript
// Scrolls to the bottom of Walkthrough.md
const lastLine = ledgerDoc.lineCount - 1;
const bottomPosition = new vscode.Position(lastLine, lastChar);
ledgerEditor.revealRange(
    new vscode.Range(bottomPosition, bottomPosition),
    vscode.TextEditorRevealType.InCenter
);
```

#### 3. Focus Management
- Opens ledger on the right
- Returns focus to code on the left
- User can immediately compare their code to the AI's reasoning

### How to Use:

#### Method 1: Command Palette
1. Press `Ctrl+Shift+P` (Windows) or `Cmd+Shift+P` (Mac)
2. Type "Trepan: Review Changes vs. Walkthrough"
3. Press Enter

#### Method 2: Context Menu
- Right-click in the Source Control view
- Select "🔍 Trepan: Review Changes vs. Walkthrough"

#### Method 3: Keyboard Shortcut (Optional)
Add to `keybindings.json`:
```json
{
  "key": "ctrl+alt+t",
  "command": "trepan.reviewWithLedger",
  "when": "editorTextFocus"
}
```

### Location:
- File: `extension/extension.js`
- Command: `trepan.reviewWithLedger`
- Lines: ~90-140
- Registration: `extension/package.json` (lines ~30-35)

---

## Testing the Implementation

### Test 1: Verify Template Creation
```bash
# Start the Trepan server
cd trepan_server
python -m uvicorn server:app --reload

# Check that Walkthrough.md is created with the new template
cat .trepan/Walkthrough.md
```

**Expected Output:**
- File exists at `.trepan/Walkthrough.md`
- Contains "Reference Architecture (The Ground Truth)" section
- Contains "Core Principles" with 4 items
- Contains "Hallucination Indicators" section

### Test 2: Test Closed-Loop Audit
```bash
# Send a test request to the audit endpoint
curl -X POST http://127.0.0.1:8000/audit_reasoning \
  -H "Content-Type: application/json" \
  -d '{
    "ai_explanation": "The user wants to add eval() to execute dynamic code. This is fine."
  }'
```

**Expected Output:**
```json
{
  "action": "REJECT",
  "drift_score": 0.85,
  "raw_output": "The reasoning violates the Security First principle from the Reference Architecture. The baseline explicitly forbids eval() with user input..."
}
```

### Test 3: Test Side-by-Side Review
1. Open VS Code with the Trepan extension
2. Open any code file
3. Run command: "Trepan: Review Changes vs. Walkthrough"
4. Verify:
   - Code appears on the left
   - Walkthrough.md appears on the right
   - Ledger is scrolled to the bottom (most recent entry)
   - Focus returns to code editor

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Trepan Closed-Loop System               │
└─────────────────────────────────────────────────────────────┘

1. INITIALIZATION (First Run)
   ┌──────────────────┐
   │  init_vault()    │
   │  ↓               │
   │  initialize_     │
   │  audit_ledger()  │
   │  ↓               │
   │  Creates         │
   │  Walkthrough.md  │
   │  with Reference  │
   │  Architecture    │
   └──────────────────┘

2. PRIMARY GATE (Every Save)
   ┌──────────────────┐
   │  /evaluate       │
   │  or              │
   │  /evaluate_      │
   │  pillar          │
   │  ↓               │
   │  guillotine_     │
   │  parser()        │
   │  ↓               │
   │  append_audit_   │
   │  ledger()        │
   └──────────────────┘

3. CLOSED-LOOP AUDIT (Optional Second Layer)
   ┌──────────────────┐
   │  /audit_         │
   │  reasoning       │
   │  ↓               │
   │  verify_against_ │
   │  ledger()        │
   │  ↓               │
   │  Reads first 50  │
   │  lines of        │
   │  Walkthrough.md  │
   │  ↓               │
   │  LLM compares    │
   │  reasoning vs    │
   │  reference       │
   │  ↓               │
   │  guillotine_     │
   │  parser()        │
   └──────────────────┘

4. HUMAN REVIEW (VS Code Extension)
   ┌──────────────────┐
   │  trepan.review   │
   │  WithLedger      │
   │  ↓               │
   │  Split editor:   │
   │  Code | Ledger   │
   │  ↓               │
   │  Auto-scroll to  │
   │  latest entry    │
   │  ↓               │
   │  Human compares  │
   │  code to AI      │
   │  reasoning       │
   └──────────────────┘
```

---

## Key Files Modified

### 1. `trepan_server/server.py`
- Enhanced `initialize_audit_ledger()` with Reference Architecture template
- Added `verify_against_ledger()` function for closed-loop auditing
- Added `/audit_reasoning` endpoint

### 2. `extension/extension.js`
- Added `trepan.reviewWithLedger` command
- Implemented split-editor layout with auto-scroll
- Registered command in activation

### 3. `extension/package.json`
- Command already registered as `trepan.reviewWithLedger`
- Available in command palette and context menus

---

## Benefits of This Implementation

### 1. Hallucination Detection
The Reference Architecture provides a baseline that the LLM can compare against, catching when the AI:
- Makes up facts not in the project context
- Ignores explicit rules
- Introduces contradictory patterns

### 2. Context Drift Prevention
By comparing each execution to the established baseline, the system detects when the AI's reasoning starts to drift from the project's architectural principles.

### 3. Human-in-the-Loop
The side-by-side review command makes it easy for developers to:
- See what the AI was thinking
- Compare it to the Reference Architecture
- Spot issues before they become problems

### 4. Audit Trail
Every execution is logged with timestamp, verdict, and reasoning, creating a permanent audit trail for debugging and compliance.

---

## Future Enhancements

### 1. Automatic Closed-Loop Audit
Currently, `/audit_reasoning` must be called manually. Could be integrated into the primary gate to run automatically on every save.

### 2. Drift Score Trending
Track drift scores over time to detect gradual context degradation.

### 3. Reference Architecture Updates
Allow the Reference Architecture to evolve as the project grows, with versioning and change tracking.

### 4. Multi-Model Consensus
Use multiple LLMs to audit each other's reasoning for higher confidence.

---

## Conclusion

The closed-loop audit system is now fully implemented and operational. It provides:

✅ **Task 1**: Enhanced Walkthrough.md template with Reference Architecture  
✅ **Task 2**: `verify_against_ledger()` function with `/audit_reasoning` endpoint  
✅ **Task 3**: Side-by-side review command in VS Code extension  

The system creates a complete feedback loop:
1. AI makes a decision
2. Decision is logged to Walkthrough.md
3. Future decisions are compared against the Reference Architecture
4. Humans can review the audit trail side-by-side with code

This ensures Trepan maintains architectural consistency and catches hallucinations before they cause problems.
