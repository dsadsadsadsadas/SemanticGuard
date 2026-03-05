# Fix: Missing Pillar Files in .trepan Folder

## Problem

When the Trepan server starts, it creates the `.trepan` folder with:
- ✅ `trepan_vault/` (vault directory)
- ✅ `.trepan.lock` (cryptographic signature)
- ✅ `README.md` (auto-generated documentation)
- ✅ `Walkthrough.md` (audit ledger)

But it's **missing the 5 pillar files**:
- ❌ `golden_state.md`
- ❌ `system_rules.md`
- ❌ `done_tasks.md`
- ❌ `pending_tasks.md`
- ❌ `history_phases.md`
- ❌ `problems_and_resolutions.md`

## Root Cause

The `init_vault()` function was designed to:
1. Copy pillar files from `.trepan/` to `.trepan/trepan_vault/`
2. Load them into memory

But it **never created the pillar files in the first place**! It assumed they already existed.

## Solution

Added a new function `create_default_pillars()` that creates default pillar files if they don't exist.

### Changes Made

#### 1. New Function: `create_default_pillars()`

**Location**: `trepan_server/server.py` (before `init_vault()`)

**What it does**:
- Checks if each pillar file exists in `.trepan/`
- If missing, creates it with default content
- Logs which files were created

**Default Content**:
- `golden_state.md` - Basic architecture template
- `system_rules.md` - Security and quality rules (with Trepan mandatory defaults)
- `done_tasks.md` - Empty completed tasks log
- `pending_tasks.md` - Empty TODO list
- `history_phases.md` - Project history with initialization timestamp
- `problems_and_resolutions.md` - Empty problems log with usage instructions

#### 2. Updated `init_vault()`

Added call to `create_default_pillars()` at the beginning:

```python
def init_vault():
    # ... setup code ...
    
    # NEW: Create default pillar files if they don't exist
    create_default_pillars(trepan_dir)
    
    # ... rest of initialization ...
```

## How to Test

### Option 1: Delete and Restart (Recommended)

1. **Stop the Trepan server** (if running)

2. **Delete the .trepan folder**:
   ```bash
   rm -rf C:\Users\ethan\Documents\Projects\Trepan_Test_Zone\.trepan
   ```
   Or manually delete it in File Explorer

3. **Start the Trepan server**:
   ```bash
   start_trepan.bat
   ```
   Or:
   ```bash
   python -m uvicorn trepan_server.server:app --reload
   ```

4. **Check the .trepan folder**:
   You should now see:
   ```
   .trepan/
   ├── trepan_vault/
   │   ├── golden_state.md
   │   ├── system_rules.md
   │   ├── done_tasks.md
   │   ├── pending_tasks.md
   │   ├── history_phases.md
   │   └── problems_and_resolutions.md
   ├── .trepan.lock
   ├── README.md
   ├── Walkthrough.md
   ├── golden_state.md          ← NEW!
   ├── system_rules.md           ← NEW!
   ├── done_tasks.md             ← NEW!
   ├── pending_tasks.md          ← NEW!
   ├── history_phases.md         ← NEW!
   └── problems_and_resolutions.md ← NEW!
   ```

### Option 2: Manual Creation (If You Don't Want to Delete)

If you don't want to delete the existing `.trepan` folder, you can manually create the missing files or just restart the server - it will create any missing pillars automatically.

## Expected Server Output

When you start the server, you should see:

```
==================================================
SHADOW VAULT INITIALIZATION STARTING...
Target Root: C:\Users\ethan\Documents\Projects\Trepan_Test_Zone
Source .trepan: C:\Users\ethan\Documents\Projects\Trepan_Test_Zone\.trepan (Exists? True)
Target Vault: C:\Users\ethan\Documents\Projects\Trepan_Test_Zone\.trepan\trepan_vault

[PILLAR CREATION] Checking for missing pillar files...
  [CREATED] golden_state.md
  [CREATED] system_rules.md
  [CREATED] done_tasks.md
  [CREATED] pending_tasks.md
  [CREATED] history_phases.md
  [CREATED] problems_and_resolutions.md
[PILLAR CREATION] Created 6 default pillar files

[LEDGER] Initializing Trepan Audit Ledger (Walkthrough.md)...
[LEDGER] Walkthrough.md created successfully.

[RULE GUARDIAN] Scanning system_rules.md for mandatory defaults...
  [OK]      NO hardcoded secrets, API keys, or passwords
  [OK]      NO `eval()` or `exec()`
  [OK]      NO `os.system()` or `subprocess`
  [OK]      ALL file paths must use `os.path.realpath()`
  [OK]      ALL SQL queries must use parameterized statements
  [OK]      YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock
  [OK]      Strict Contextual Synchronization
[RULE GUARDIAN] All mandatory rules are present. No injection needed.

[README GUARDIAN] Initializing Trepan README.md...
[README GUARDIAN] README.md created successfully

[VAULT LOCK] First-time vault seeded with 6 files.
[VAULT LOCK] Lock written to: ...
✅ Ollama connection verified — server accepting requests
```

## What the Default Files Contain

### golden_state.md
- Basic architecture template
- Placeholder for technology stack
- Placeholder for architectural patterns
- Note about using `Trepan: Initialize Project` for templates

### system_rules.md
- Security rules (no hardcoded secrets, no eval, etc.)
- Code quality rules (descriptive names, error handling)
- Trepan system rules (don't touch vault, contextual sync)
- Note about using `Trepan: Initialize Project` for mode-specific rules

### done_tasks.md
- Empty with usage instructions
- Example format for completed tasks

### pending_tasks.md
- Empty with usage instructions
- Example format for TODO items

### history_phases.md
- Phase 1: Initialization entry with timestamp
- Usage instructions
- Example format for documenting phases

### problems_and_resolutions.md
- Empty with usage instructions
- Example format for documenting problems
- Note about `/evolve_memory` endpoint

## Using the Initialize Project Command

The default pillar files are minimal. For a complete setup with mode-specific rules and LLM-generated examples, use:

1. **Open Command Palette**: `Ctrl+Shift+P`
2. **Run**: `Trepan: Initialize Project`
3. **Choose a template**:
   - Solo-Indie (The Speedster)
   - Clean-Layers (The Architect)
   - Secure-Stateless (The Fortress)

This will:
- Replace `system_rules.md` with mode-specific rules
- Generate `golden_state.md` with LLM-generated "Perfect Execution" example
- Initialize all other pillars
- Create vault snapshots
- Sign the vault

## Verification

After the fix, verify all files exist:

```bash
ls C:\Users\ethan\Documents\Projects\Trepan_Test_Zone\.trepan\
```

You should see:
- ✅ `golden_state.md`
- ✅ `system_rules.md`
- ✅ `done_tasks.md`
- ✅ `pending_tasks.md`
- ✅ `history_phases.md`
- ✅ `problems_and_resolutions.md`
- ✅ `README.md`
- ✅ `Walkthrough.md`
- ✅ `.trepan.lock`
- ✅ `trepan_vault/` (folder)

## Status: FIXED ✅

The pillar files will now be automatically created on first server startup. No manual intervention needed.
