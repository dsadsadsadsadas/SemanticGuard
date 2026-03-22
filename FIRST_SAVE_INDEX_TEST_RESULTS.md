# First-Save Indexing Test Results

## Test 1 — Large file first save (160 lines)
**Expected**: Index silently, skip audit, show status bar message
**File**: trepan_perf_test.py (160 lines)
**Steps**: 
1. Clear VS Code cache (close and reopen file)
2. Save with Ctrl+S
3. Check console for indexing message
4. Verify no server request fires

**Result**: PENDING

## Test 2 — Large file second save (diff engine)
**Expected**: Diff engine fires, audit completes
**File**: trepan_perf_test.py (after first save)
**Steps**:
1. Make one line change
2. Save with Ctrl+S
3. Verify diff engine fires
4. Record audit time and verdict

**Result**: PENDING

## Test 3 — Small file first save (under 120 lines)
**Expected**: Audit fires normally
**File**: Create new file with <120 lines
**Steps**:
1. Create new Python file with ~100 lines
2. Save with Ctrl+S
3. Verify audit fires
4. Record audit time and verdict

**Result**: PENDING
