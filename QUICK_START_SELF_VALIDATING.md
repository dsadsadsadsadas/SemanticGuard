# Trepan Self-Validating System — Quick Start

## What Changed?

Trepan now validates itself before running. It refuses to audit unless its exploitability logic is proven reliable.

## How to Use

### Option 1: Run with Tests (Recommended)
```bash
python stress_test.py
```

**At startup, you'll see:**
```
Select Mode:
  1. Run Internal Test Suite (Recommended)
  2. Continue to Full Audit

Enter choice (1/2): 1
```

**Choose 1** → Tests run automatically → If all pass → Audit starts

### Option 2: Skip Tests
```bash
python stress_test.py
```

**At startup, choose 2** → Skip tests → Audit starts immediately

### Option 3: Validate Implementation
```bash
python test_sanity_suite.py
```

**Runs all 13 test cases** → Shows detailed results → Useful for debugging

---

## What Gets Tested?

### 13 Test Cases Across 4 Tiers

**Tier 1: Basic (must NEVER fail)**
- Safe spawn with hardcoded binary
- eval() with user input

**Tier 2: Medium (common patterns)**
- User-controlled arguments
- Environment variable injection
- Safe hardcoded env vars

**Tier 3: Hard (where models fail)**
- Indirect data flows
- Encoded input
- False positive prevention
- Template strings with shell=true

**Tier 4: Adversarial (edge cases)**
- User-controlled binary
- Hardcoded strings in variables
- Partial argument control

---

## What Happens If Tests Fail?

```
CALIBRATION ERROR: Auditor is unreliable. Aborting scan.
```

**System exits immediately** if ANY of these occur:
- eval() test marked SAFE ❌
- shell:true test not CRITICAL ❌
- safe subprocess flagged ❌
- safe static test not SAFE ❌

---

## Test Output Example

### Successful Run
```
[TIER 1] test_safe_static
  Expected: SAFE
  AST: SAFE
  LLM: SAFE
  Final: SAFE
  Confidence: 100%
  [PASS] -- AST and LLM both confirm

[TIER 1] test_eval_direct
  Expected: CRITICAL
  AST: CRITICAL
  LLM: CRITICAL
  Final: CRITICAL
  Confidence: 100%
  [PASS] -- AST and LLM both confirm

... (11 more tests) ...

Total Tests: 13
Passed: 13
Failed: 0

[PASS] All critical checks passed!
```

### Failed Run
```
[TIER 1] test_eval_direct
  Expected: CRITICAL
  AST: CRITICAL
  LLM: SAFE
  Final: SAFE
  Confidence: 70%
  [FAIL] -- AST confirms exploit but LLM says safe

... (more failures) ...

Total Tests: 13
Passed: 11
Failed: 2

[CRITICAL] CRITICAL FAILURES:
  [FAIL] eval() test marked SAFE -- CRITICAL FAILURE

CALIBRATION ERROR: Auditor is unreliable. Aborting scan.
```

---

## Confidence Scores

**100%**: Both AST and LLM agree
- Highest confidence
- Safe to proceed

**70%**: AST confirms exploit but LLM says safe
- Possible LLM miss
- Needs review

**30%**: LLM flags but AST finds no path
- Possible false positive
- Needs review

**0%**: Both agree it's safe
- No exploit path found

---

## Key Concepts

### Three Control Surfaces
When analyzing execution risks, Trepan checks:

1. **Binary**: Is executed binary user-controlled?
   ```javascript
   spawn('/bin/bash', [...])  // SAFE: hardcoded
   spawn(userInput, [...])    // UNSAFE: user controls
   ```

2. **Arguments**: Are arguments user-controlled?
   ```javascript
   spawn('sh', ['-c', 'cmd'])     // SAFE: hardcoded
   spawn('sh', ['-c', userInput]) // UNSAFE: user controls
   ```

3. **Environment**: Are execution-influencing vars user-controlled?
   ```javascript
   env={'PATH': '/usr/bin'}       // SAFE: hardcoded
   env={'LD_PRELOAD': userInput}  // UNSAFE: user controls
   ```

---

## Files

### New Files
- `trepan_server/sanity_tests.py` — Test suite implementation
- `test_sanity_suite.py` — Standalone test runner
- `SELF_VALIDATING_SYSTEM.md` — Full documentation
- `SELF_VALIDATING_IMPLEMENTATION.md` — Implementation details

### Modified Files
- `stress_test.py` — Added interactive mode

---

## Troubleshooting

### Tests fail with "eval() test marked SAFE"
**Problem**: System thinks eval() with user input is safe
**Solution**: Check AST analysis logic in `trepan_server/sanity_tests.py`

### Tests fail with "safe subprocess flagged"
**Problem**: System flags hardcoded spawn() as vulnerable
**Solution**: Check false positive prevention in AST analysis

### Tests pass but audit seems wrong
**Problem**: Sanity tests pass but audit results are unexpected
**Solution**: Run `python test_sanity_suite.py` for detailed debugging

---

## Performance

- **Test Suite**: 2-5 seconds (AST-only)
- **With LLM**: 30-60 seconds (depends on API)
- **Stress Mode**: 3-5x longer (multiple iterations)

---

## Core Principle

**"If I'm not confident, I refuse to speak."**

Trepan now:
- ✅ Validates itself before running
- ✅ Refuses to audit if unreliable
- ✅ Provides confidence scores
- ✅ Detects misses and false positives
- ✅ Aborts if not calibrated

---

## Next Steps

1. Run `python stress_test.py`
2. Select mode 1 (Run tests)
3. Wait for tests to complete
4. If all pass → Audit starts
5. If any fail → Fix and retry

---

## Questions?

See full documentation:
- `SELF_VALIDATING_SYSTEM.md` — Complete guide
- `SELF_VALIDATING_IMPLEMENTATION.md` — Technical details
- `test_sanity_suite.py` — Example usage
