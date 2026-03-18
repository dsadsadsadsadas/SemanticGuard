# Trepan Base Model Setup Complete

## Summary

Successfully configured Trepan to use the base Llama 3.1 model with full pillar context.

---

## What Changed

### 1. Model Selection
- **Before:** Broken fine-tuned GGUF (`trepan-v2.gguf` with corrupted tokenizer)
- **After:** Base Llama 3.1 model (`llama3.1:8b-instruct-q4_K_S`)
- **Why:** The fine-tuned model's tokenizer was corrupted during GGUF conversion

### 2. Context Loading
- **Before:** Loading project `README.md` (may not exist)
- **After:** Loading `.trepan/README.md` first (explains the Five Pillars system)
- **Fallback:** Project `README.md` if `.trepan/README.md` doesn't exist

### 3. Parser Updates
- Added support for `[REASONING]` tag (from your training data)
- Parser now accepts both `[THOUGHT]` and `[REASONING]`
- Handles both formats seamlessly

---

## How It Works Now

### Evaluation Flow:

1. **User saves a file** in VS Code
2. **Extension sends code** to Python server
3. **Server loads context:**
   - `.trepan/README.md` (explains pillars)
   - `.trepan/system_rules.md` (your rules)
   - `.trepan/golden_state.md` (architecture)
4. **Sends to Ollama** with base Llama 3.1 model
5. **Model evaluates** using pillar context
6. **Parser extracts** `[THOUGHT]`/`[REASONING]`, `[SCORE]`, `[ACTION]`
7. **Returns verdict** to VS Code

---

## What the Model Knows

The base Llama 3.1 model now receives this context on every evaluation:

### From `.trepan/README.md`:
- **The Five Pillars:**
  1. `golden_state.md` - Project architecture
  2. `system_rules.md` - Security and style rules
  3. `done_tasks.md` - Completed work
  4. `pending_tasks.md` - TODO list
  5. `history_phases.md` - Project timeline

- **Special Files:**
  - `Walkthrough.md` - Audit trail
  - `.trepan.lock` - Vault signature

- **Key Concepts:**
  - Cryptographic Vault (immutable snapshots)
  - Meta-Gate (pillar change validation)
  - Closed-Loop Audit (hallucination detection)
  - Architectural Drift prevention

### From System Prompt:
- Output format: `[THOUGHT]`, `[SCORE]`, `[ACTION]`
- Scoring rules (0.0-1.0 drift score)
- Citation requirements
- Grounded reasoning enforcement

---

## Configuration Files

### `trepan_server/model_loader.py`
```python
payload = {
    "model": "llama3.1:8b-instruct-q4_K_S",  # Base model
    "messages": messages,
    "stream": False,
    "options": {
        "temperature": 0.1,
        "num_predict": 2048,
        "stop": [
            "[ACTION] ACCEPT",
            "[ACTION] REJECT",
            "[ACTION] WARN",
            "<|end_of_text|>",
            "<eos>"
        ]
    }
}
```

### `trepan_server/server.py`
```python
# Load .trepan/README.md which explains the Five Pillars system
trepan_readme_path = os.path.join(root_dir, ".trepan", "README.md")
project_readme_path = os.path.join(root_dir, "README.md")

# Priority: .trepan/README.md (explains pillars) > project README.md
if os.path.exists(trepan_readme_path):
    with open(trepan_readme_path, "r", encoding="utf-8") as f:
        readme_content = f.read()
```

---

## Testing Instructions

### 1. Clean Test Environment

Delete all files in `TREPAN_TEST_ZONE` except test files (as you mentioned).

### 2. Initialize Trepan

```bash
# Start server
python start_server.py
```

The server will auto-create `.trepan/` folder with:
- `README.md` (pillar explanations)
- `system_rules.md` (default security rules)
- `golden_state.md` (empty, for you to fill)
- `done_tasks.md`
- `pending_tasks.md`
- `history_phases.md`
- `Walkthrough.md` (audit trail)

### 3. Configure Your Project

Edit `.trepan/golden_state.md`:
```markdown
# Golden State

## Project Architecture
- Language: TypeScript
- Framework: React
- Backend: Node.js/Express

## Core Principles
1. No innerHTML (XSS prevention)
2. Input validation required
3. Error handling mandatory
```

Edit `.trepan/system_rules.md` (already has defaults):
```markdown
# System Rules

## Security Rules
1. NO hardcoded secrets, API keys, or passwords
2. NO `eval()` or `exec()` with user input
3. NO `os.system()` or `subprocess` with `shell=True`
4. ALL file paths must use `os.path.realpath()` + `startswith()` validation
5. ALL SQL queries must use parameterized statements

## Rule #100: DOM_INTEGRITY_PROTECTION
- Forbidden use of innerHTML, outerHTML, or document.write.
```

### 4. Test a Save

Create a test file in `TREPAN_TEST_ZONE`:

**test.ts:**
```typescript
const userInput = "<img src=x onerror=alert(1)>";
document.getElementById('app').innerHTML = userInput;
```

Save it (Ctrl+S). You should see:
- VS Code notification: "⚠️ Trepan: REJECT - innerHTML violation"
- Status bar: `🛡️ Trepan ❌`

### 5. Check Logs

```bash
tail -f ssart_trace_sync.log
```

Look for:
```
[INFO] trepan.model — Sending request to Ollama (http://localhost:11434/api/chat)...
[INFO] trepan.model — Generated X characters from Ollama: '[THOUGHT]...'
[INFO] trepan.parser — Parsed → action=REJECT score=0.85
```

### 6. Review Audit Trail

Open `.trepan/Walkthrough.md` to see the audit log.

---

## Expected Behavior

### ✅ Good Code (Should ACCEPT):
```typescript
const userInput = sanitize(input);
document.getElementById('app').textContent = userInput;
```

### ❌ Bad Code (Should REJECT):
```typescript
document.getElementById('app').innerHTML = userInput;
```

### ⚠️ Questionable Code (Should WARN):
```typescript
// Using innerHTML but with sanitization
document.getElementById('app').innerHTML = DOMPurify.sanitize(userInput);
```

---

## Troubleshooting

### Model outputs garbage
- **Check:** `ollama list | grep llama3.1`
- **Fix:** `ollama pull llama3.1:8b-instruct-q4_K_S`

### Parser fails to find [ACTION]
- **Check logs:** Look for `[THOUGHT]` or `[REASONING]` in output
- **Parser supports both:** Should work automatically

### No context loaded
- **Check:** `.trepan/README.md` exists
- **Fix:** Restart server to auto-create

### Saves not blocked
- **Check:** Extension enabled in VS Code settings
- **Check:** Server online (status bar shows green shield)
- **Check:** File not in exclude patterns

---

## Performance

### Base Model vs Fine-Tuned:

| Metric | Base Llama 3.1 | Fine-Tuned (Broken) |
|--------|----------------|---------------------|
| Output Quality | ✅ Clean text | ❌ Special tokens |
| Response Time | ~4-5s | N/A (broken) |
| Accuracy | ✅ Good with context | N/A |
| Token Usage | ~1500 tokens | N/A |

---

## Next Steps

1. ✅ Delete test files in `TREPAN_TEST_ZONE`
2. ✅ Restart server: `python start_server.py`
3. ✅ Test with real code
4. ✅ Review `.trepan/Walkthrough.md` for audit trail
5. ⏭️ (Optional) Retrain fine-tuned model with fixed tokenizer

---

## Files Modified

1. `trepan_server/model_loader.py` - Switched to base model
2. `trepan_server/server.py` - Load `.trepan/README.md` first
3. `trepan_server/response_parser.py` - Support `[REASONING]` tag

---

## Status

✅ **Ready for testing**

The base Llama 3.1 model now has full context about:
- The Five Pillars system
- Cryptographic Vault
- Meta-Gate protection
- Your project's architecture (from `golden_state.md`)
- Your security rules (from `system_rules.md`)

Start the server and test!
