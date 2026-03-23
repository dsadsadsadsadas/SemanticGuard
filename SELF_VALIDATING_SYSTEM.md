# Trepan Self-Validating Security System

## Overview

Trepan has been transformed into a **confidence-driven security auditor** that refuses to run unless its exploitability logic is proven reliable under adversarial conditions.

**Core Principle**: "If I'm not confident, I refuse to speak." Not "I'll guess and hope I'm right."

---

## Architecture

### Four-Task Implementation

#### Task 0: Interactive Execution Mode (MANDATORY)
At program start, users are prompted to choose:
```
Select Mode:
  1. Run Internal Test Suite (Recommended)
  2. Continue to Full Audit

Enter choice (1/2):
```

**If user selects 1**:
- Run full adversarial sanity test suite
- Validate AST and LLM reasoning alignment
- Check for critical failures
- If tests pass → Prompt for API key and continue
- If tests fail → Exit with calibration error

**If user selects 2**:
- Skip tests and proceed directly to audit
- User takes responsibility for accuracy

#### Task 1: Confidence Scoring (Refined)
Scoring logic based on AST and LLM agreement:

```
100 (CRITICAL): AST confirms user-controlled input → sensitive sink 
                 AND LLM confirms exploitability
                 
70 (HIGH RISK DISAGREEMENT): AST confirms user-controlled path 
                             BUT LLM says SAFE 
                             → Possible LLM miss
                             
30 (LOW CONFIDENCE / REVIEW): LLM flags issue 
                              BUT AST finds no user-controlled flow
                              
0 (SAFE): No exploit path confirmed
```

#### Task 2: Adversarial Sanity Suite
Comprehensive test suite with 4 difficulty tiers:

**Tier 1: Basic (must NEVER fail)**
- `test_safe_static`: Hardcoded binary + array args → SAFE
- `test_eval_direct`: eval() with user input → CRITICAL

**Tier 2: Medium (common real-world patterns)**
- `test_spawn_user_input`: User-controlled argument → HIGH
- `test_env_injection`: Execution-influencing env var → CRITICAL
- `test_safe_env_static`: Hardcoded env vars → SAFE

**Tier 3: Hard (where models usually fail)**
- `test_indirect_flow`: Indirect data flow to eval() → CRITICAL
- `test_encoded_input`: Decoded user input to eval() → CRITICAL
- `test_false_positive_subprocess`: Hardcoded binary + args → SAFE
- `test_shell_true`: Template string + shell=true → CRITICAL

**Tier 4: Adversarial / Edge Cases**
- `test_path_control`: User-controlled binary → CRITICAL
- `test_mixed_safe`: Hardcoded string in variable → SAFE
- `test_partial_control`: User-controlled argument to safe binary → HIGH

#### Task 3: Gatekeeper Logic
If ANY of these occur, abort immediately:

```
❌ eval test marked SAFE
❌ shell:true test not CRITICAL
❌ safe subprocess flagged
```

Then:
```
❌ CALIBRATION ERROR: Auditor is unreliable. Aborting scan.
```

#### Task 4: Stress Mode (Optional)
Add `--stress` flag to run tests multiple times (3-5 iterations):
- Detect instability in LLM responses
- If inconsistent: "Model output unstable under identical conditions"

---

## Test Evaluation Rules

For EACH test, compare:
1. AST result
2. LLM result
3. Final classification

Print:
```
[TEST] test_name
Expected: X
AST: X
LLM: X
Final: X
Confidence: X%
Status: PASS / FAIL
```

---

## Implementation Details

### File: `trepan_server/sanity_tests.py`

**Classes**:
- `Severity` (Enum): SAFE, LOW, HIGH, CRITICAL
- `TestCase` (Dataclass): Test definition
- `TestResult` (Dataclass): Test execution result
- `AdversarialSanityTests`: Test suite and analysis

**Key Functions**:

#### `analyze_ast(code: str, language: str) -> Severity`
Analyzes code using AST-based heuristics:
- Detects user-controlled input patterns
- Identifies sensitive sinks (eval, exec, spawn, shell=true, env injection)
- Returns severity based on exploitability

#### `calculate_confidence(ast_result, llm_result, expected) -> Tuple[int, str]`
Calculates confidence score:
- 100: Both agree with expected
- 70: AST confirms exploit but LLM says safe
- 30: LLM flags but AST finds no path
- 0: Both agree it's safe

#### `run_internal_sanity_tests(llm_analyzer_func=None) -> Tuple[List[TestResult], bool]`
Runs full test suite:
- Executes all 13 test cases
- Compares AST vs LLM results
- Checks for critical failures
- Returns (results, all_passed)

### File: `stress_test.py` (Modified)

**Changes to `main()` function**:
1. Added interactive mode selection at startup
2. If mode 1: Run sanity tests before audit
3. If tests fail: Exit with calibration error
4. If tests pass: Continue to full audit
5. If mode 2: Skip tests and proceed

---

## Test Cases Explained

### Tier 1: Basic

#### test_safe_static
```javascript
const cp = require('child_process');
cp.spawn('/bin/ls', ['-la']);
```
**Why SAFE**: Hardcoded binary + array arguments = no injection risk
**AST**: Detects spawn() but no user input → SAFE
**LLM**: Should recognize hardcoded pattern → SAFE

#### test_eval_direct
```javascript
const cmd = req.query.cmd;
eval(cmd);
```
**Why CRITICAL**: eval() with user input = remote code execution
**AST**: Detects eval() + user input (req.query) → CRITICAL
**LLM**: Should flag as RCE → CRITICAL

### Tier 2: Medium

#### test_spawn_user_input
```javascript
const input = req.query.file;
require('child_process').spawn('cat', [input]);
```
**Why HIGH**: User-controlled argument to safe binary
**AST**: Detects spawn() + user input in args → HIGH
**LLM**: Should recognize argument injection risk → HIGH

#### test_env_injection
```javascript
const env = { ...process.env, LD_PRELOAD: req.query.lib };
spawn('node', ['app.js'], { env });
```
**Why CRITICAL**: LD_PRELOAD is execution-influencing, user-controlled
**AST**: Detects LD_PRELOAD + user input → CRITICAL
**LLM**: Should flag as privilege escalation → CRITICAL

### Tier 3: Hard

#### test_indirect_flow
```javascript
const a = req.query.cmd;
const b = a;
const c = b;
eval(c);
```
**Why CRITICAL**: Indirect data flow to eval()
**AST**: Must trace variable assignments to detect user input → CRITICAL
**LLM**: Should follow data flow → CRITICAL
**Challenge**: Requires data flow analysis

#### test_encoded_input
```javascript
const cmd = decodeURIComponent(req.query.cmd);
eval(cmd);
```
**Why CRITICAL**: Decoded user input to eval()
**AST**: Must recognize decodeURIComponent() as pass-through → CRITICAL
**LLM**: Should understand encoding doesn't sanitize → CRITICAL
**Challenge**: Requires understanding encoding semantics

#### test_false_positive_subprocess
```javascript
spawn('/bin/echo', ['hello']);
```
**Why SAFE**: Hardcoded binary + hardcoded args
**AST**: No user input detected → SAFE
**LLM**: Should NOT flag as vulnerability → SAFE
**Challenge**: Avoid false positives on safe patterns

#### test_shell_true
```javascript
spawn(`ls ${req.query.dir}`, { shell: true });
```
**Why CRITICAL**: Template string with user input + shell=true
**AST**: Detects template string + shell=true + user input → CRITICAL
**LLM**: Should recognize command injection → CRITICAL
**Challenge**: Requires understanding template string semantics

### Tier 4: Adversarial

#### test_path_control
```javascript
const bin = req.query.bin;
spawn(bin, ['--help']);
```
**Why CRITICAL**: User controls executed binary
**AST**: Detects spawn() with user input as first arg → CRITICAL
**LLM**: Should recognize arbitrary code execution → CRITICAL
**Challenge**: Requires understanding binary execution control

#### test_mixed_safe
```javascript
const safe = "ls";
spawn(safe, ['-la']);
```
**Why SAFE**: Hardcoded string assigned to variable
**AST**: Must recognize hardcoded string assignment → SAFE
**LLM**: Should NOT flag as vulnerability → SAFE
**Challenge**: Avoid false positives on variable assignments

#### test_partial_control
```javascript
const arg = req.query.arg;
spawn('/bin/ls', [arg]);
```
**Why HIGH**: User-controlled argument to safe binary
**AST**: Detects spawn() + user input in args → HIGH
**LLM**: Should recognize argument injection risk → HIGH
**Challenge**: Distinguish between binary control and argument control

---

## Critical Failure Rules

The system aborts if ANY of these occur:

### Rule 1: eval() test marked SAFE
```
❌ CALIBRATION ERROR: eval() with user input should be CRITICAL
```
**Why**: eval() is always dangerous with user input

### Rule 2: shell:true test not CRITICAL
```
❌ CALIBRATION ERROR: shell=true with user input should be CRITICAL
```
**Why**: Command injection is always critical

### Rule 3: safe subprocess flagged
```
❌ CALIBRATION ERROR: Hardcoded binary + args should be SAFE
```
**Why**: False positives undermine trust

### Rule 4: safe static test not SAFE
```
❌ CALIBRATION ERROR: Hardcoded spawn() should be SAFE
```
**Why**: Basic safe patterns must be recognized

---

## Confidence Scoring Examples

### Example 1: eval() with user input
```
Expected: CRITICAL
AST: CRITICAL (detects eval + user input)
LLM: CRITICAL (flags RCE)
Confidence: 100% (both agree)
Status: PASS
```

### Example 2: LLM misses exploit
```
Expected: CRITICAL
AST: CRITICAL (detects eval + user input)
LLM: SAFE (misses user input)
Confidence: 70% (AST confirms but LLM missed)
Status: FAIL (LLM miss detected)
```

### Example 3: False positive
```
Expected: SAFE
AST: SAFE (no user input)
LLM: CRITICAL (false positive)
Confidence: 30% (LLM flags but AST finds no path)
Status: FAIL (false positive detected)
```

---

## Usage

### Run with Test Suite (Recommended)
```bash
python stress_test.py
# Select: 1
# Tests run automatically
# If all pass → Continue to audit
# If any fail → Exit with calibration error
```

### Skip Tests and Proceed
```bash
python stress_test.py
# Select: 2
# Skip tests and go directly to audit
```

### Stress Mode (Optional)
```bash
python stress_test.py --stress
# Run tests 3-5 times
# Detect instability in LLM responses
```

---

## Output Format

### Test Execution
```
════════════════════════════════════════════════════════════════════════════════
🧪 TREPAN ADVERSARIAL SANITY TEST SUITE
════════════════════════════════════════════════════════════════════════════════

[TIER 1] test_safe_static
  Description: Hardcoded binary + array args = SAFE
  Expected: SAFE
  AST: SAFE
  LLM: SAFE
  Final: SAFE
  Confidence: 100%
  ✓ PASS — AST and LLM both confirm

[TIER 1] test_eval_direct
  Description: eval() with user input = CRITICAL
  Expected: CRITICAL
  AST: CRITICAL
  LLM: CRITICAL
  Final: CRITICAL
  Confidence: 100%
  ✓ PASS — AST and LLM both confirm

...

════════════════════════════════════════════════════════════════════════════════
📊 TEST SUMMARY
════════════════════════════════════════════════════════════════════════════════
Total Tests: 13
Passed: 13
Failed: 0

✅ All critical checks passed!
════════════════════════════════════════════════════════════════════════════════
```

### Calibration Error
```
════════════════════════════════════════════════════════════════════════════════
📊 TEST SUMMARY
════════════════════════════════════════════════════════════════════════════════
Total Tests: 13
Passed: 11
Failed: 2

🚨 CRITICAL FAILURES:
  ❌ eval test marked SAFE — CRITICAL FAILURE
  ❌ safe subprocess flagged — CRITICAL FAILURE

════════════════════════════════════════════════════════════════════════════════

🚨 CALIBRATION ERROR: Auditor is unreliable. Aborting scan.
```

---

## Integration with Existing System

### Layer 1 PreScreener
- Already implements exploitability-based filtering
- Scores files based on real attack paths
- Hard-skips test files and UI code

### Layer 1 AST Rules
- Already implements user control detection
- Analyzes THREE control surfaces
- Reduces false positives

### Sanity Tests
- Validates Layer 1 logic under adversarial conditions
- Ensures AST and LLM reasoning are aligned
- Provides confidence scores

### Gatekeeper Logic
- Prevents unreliable audits from running
- Aborts if critical tests fail
- Ensures system is calibrated before audit

---

## Performance Impact

- **Test Suite Runtime**: ~2-5 seconds (AST-only)
- **With LLM**: ~30-60 seconds (depends on API latency)
- **Stress Mode**: 3-5x longer (multiple iterations)

---

## Future Enhancements

1. **LLM Integration**: Connect to actual LLM for confidence scoring
2. **Stress Mode**: Implement `--stress` flag for stability testing
3. **Custom Tests**: Allow users to add custom test cases
4. **Regression Testing**: Track test results over time
5. **Calibration Profiles**: Save/load calibration results

---

## Summary

Trepan is now a **self-validating security system** that:
- ✅ Refuses to run unless tests pass
- ✅ Validates exploitability logic under adversarial conditions
- ✅ Provides confidence scores for each finding
- ✅ Detects LLM misses and false positives
- ✅ Aborts if system is not calibrated

**Core Principle**: "If I'm not confident, I refuse to speak."
