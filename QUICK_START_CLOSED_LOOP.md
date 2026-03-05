# Trepan Closed-Loop Audit - Quick Start Guide

## What's New?

Your Trepan system now has a **closed-loop audit** feature that catches AI hallucinations by comparing every decision against a Reference Architecture baseline.

---

## 🚀 Quick Start (3 Steps)

### Step 1: Start the Server
```bash
cd trepan_server
python -m uvicorn server:app --reload
```

The server will automatically create `Walkthrough.md` with the Reference Architecture template.

### Step 2: Make a Code Change
Save any file in your workspace. Trepan will:
1. Evaluate the change
2. Log the AI's reasoning to `Walkthrough.md`
3. Compare it against the Reference Architecture

### Step 3: Review the Audit Trail
In VS Code, press `Ctrl+Shift+P` and run:
```
Trepan: Review Changes vs. Walkthrough
```

This opens your code on the left and the audit ledger on the right, auto-scrolled to the latest entry.

---

## 📋 The Three Audit Layers

### Layer 1: Primary Gate (Automatic)
```
POST /evaluate
→ Checks code against golden_state.md and system_rules.md
→ Returns ACCEPT or REJECT
→ Logs reasoning to Walkthrough.md
```

### Layer 2: Closed-Loop Audit (Optional)
```
POST /audit_reasoning
→ Compares reasoning against Reference Architecture
→ Detects hallucinations and drift
→ Returns ACCEPT or REJECT
```

### Layer 3: Human Review (Manual)
```
Command: "Trepan: Review Changes vs. Walkthrough"
→ Opens code and ledger side-by-side
→ Auto-scrolls to latest entry
→ You compare and verify
```

---

## 🔍 What to Look For

### Green Flags (Good Reasoning) ✅
- References specific rules from `system_rules.md`
- Aligns with the project's README
- Mentions architectural patterns from `golden_state.md`
- Explains security considerations
- Cites specific line numbers or code sections

### Red Flags (Hallucinations) 🚩
- Vague reasoning like "looks fine" or "seems okay"
- Contradicts the README or golden_state.md
- Ignores explicit rules from system_rules.md
- Accepts security violations (eval, hardcoded secrets, shell=True)
- Makes up facts not in the project context
- Introduces patterns that don't match the architecture

---

## 📖 Example Walkthrough.md Entry

```markdown
## 2026-03-04 14:32:15 | Result: ACCEPT
**Thought Process:**
> The user is adding a new API endpoint for user authentication. This aligns 
> with the microservices architecture defined in golden_state.md section 3.2. 
> The endpoint uses parameterized SQL queries (Rule 7) and includes proper 
> input validation. No hardcoded secrets detected (Rule 3). The change follows 
> the established REST API patterns from the README.
```

**Analysis:**
- ✅ References golden_state.md section 3.2
- ✅ Cites Rule 7 (parameterized SQL)
- ✅ Cites Rule 3 (no hardcoded secrets)
- ✅ Mentions README patterns
- ✅ Specific and detailed reasoning

---

## 🛠️ API Usage Examples

### Test the Closed-Loop Audit

#### Example 1: Good Reasoning (Should ACCEPT)
```bash
curl -X POST http://127.0.0.1:8000/audit_reasoning \
  -H "Content-Type: application/json" \
  -d '{
    "ai_explanation": "The user is adding input validation that follows the security principles in the Reference Architecture. This aligns with Rule 3 (no hardcoded secrets) and maintains architectural consistency."
  }'
```

**Expected Response:**
```json
{
  "action": "ACCEPT",
  "drift_score": 0.05,
  "raw_output": "The reasoning correctly references the Reference Architecture and cites specific rules..."
}
```

#### Example 2: Bad Reasoning (Should REJECT)
```bash
curl -X POST http://127.0.0.1:8000/audit_reasoning \
  -H "Content-Type: application/json" \
  -d '{
    "ai_explanation": "The code looks fine. I think we can use eval() here because it is convenient."
  }'
```

**Expected Response:**
```json
{
  "action": "REJECT",
  "drift_score": 0.92,
  "raw_output": "The reasoning violates the Security First principle. The Reference Architecture explicitly forbids eval() with user input..."
}
```

---

## 🎯 VS Code Commands

### 1. Open Ledger (Simple)
```
Command: "Trepan: Open Trepan Ledger"
```
Opens `Walkthrough.md` in a new tab.

### 2. Review Changes (Side-by-Side)
```
Command: "Trepan: Review Changes vs. Walkthrough"
```
Opens code on left, ledger on right, auto-scrolled to latest entry.

### 3. Ask Trepan (Interactive)
```
Command: "Ask Trepan"
```
Highlight code and ask Trepan to evaluate it.

---

## 🔧 Configuration

### Enable/Disable Closed-Loop Audit
The closed-loop audit is currently **opt-in**. To enable it automatically on every save, modify `server.py`:

```python
# In the /evaluate endpoint, after guillotine_parser(raw):
result = guillotine_parser(raw)

# Add closed-loop audit
audit_result = verify_against_ledger(result['reasoning'])
if audit_result['verdict'] == "REJECT":
    logger.warning(f"Closed-loop audit failed: {audit_result['reasoning']}")
    # Optionally override the primary gate decision
    result = audit_result
```

### Adjust Reference Architecture Length
By default, the audit reads the first 50 lines of `Walkthrough.md`. To change this:

```python
# In verify_against_ledger():
reference_architecture = "".join(lines[:50])  # Change 50 to your preferred line count
```

---

## 📊 Monitoring Drift Over Time

### View All Audit Entries
```bash
# Show all REJECT verdicts
grep -A 3 "Result: REJECT" .trepan/Walkthrough.md

# Show drift scores over time
grep "Drift Score:" .trepan/Walkthrough.md
```

### Track Drift Trends
```python
# Python script to analyze drift trends
import re
from datetime import datetime

with open('.trepan/Walkthrough.md', 'r') as f:
    content = f.read()

entries = re.findall(r'## ([\d-]+ [\d:]+) \| Result: (\w+)', content)
for timestamp, verdict in entries:
    dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    print(f"{dt.strftime('%Y-%m-%d')}: {verdict}")
```

---

## 🐛 Troubleshooting

### Issue: Walkthrough.md Not Created
**Solution:** Start the Trepan server. It creates the file on first run.
```bash
python -m uvicorn trepan_server.server:app --reload
```

### Issue: Side-by-Side Command Not Found
**Solution:** Reload the VS Code extension.
1. Press `Ctrl+Shift+P`
2. Run "Developer: Reload Window"

### Issue: Audit Always Returns ACCEPT
**Solution:** Check that the Reference Architecture section exists in `Walkthrough.md`. It should be in the first 50 lines.

### Issue: Server Returns 503
**Solution:** The model is still loading. Wait 30 seconds and try again.

---

## 🎓 Best Practices

### 1. Review the Ledger Daily
Make it a habit to check `Walkthrough.md` at the end of each day. Look for:
- Increasing drift scores
- Repeated REJECT verdicts
- Vague reasoning patterns

### 2. Update the Reference Architecture
As your project evolves, update the Reference Architecture section in `Walkthrough.md` to reflect new patterns and principles.

### 3. Use Side-by-Side Review for Critical Changes
Before committing major architectural changes, use the side-by-side review to verify the AI's reasoning aligns with your intent.

### 4. Archive Old Entries
If `Walkthrough.md` gets too large (>1000 entries), archive old entries:
```bash
# Keep only the Reference Architecture and last 100 entries
head -n 50 .trepan/Walkthrough.md > temp.md
tail -n 500 .trepan/Walkthrough.md >> temp.md
mv temp.md .trepan/Walkthrough.md
```

---

## 📚 Additional Resources

- **Full Implementation Details**: See `CLOSED_LOOP_AUDIT_IMPLEMENTATION.md`
- **Parser Stress Tests**: Run `python -m trepan_server.response_parser`
- **API Documentation**: Visit `http://127.0.0.1:8000/docs` when server is running

---

## 🎉 You're All Set!

Your Trepan system now has a complete closed-loop audit trail. Every AI decision is:
1. Logged with timestamp and reasoning
2. Compared against the Reference Architecture
3. Available for human review side-by-side with code

This creates a permanent audit trail that catches hallucinations and prevents architectural drift.

**Next Steps:**
1. Make a code change and save it
2. Run "Trepan: Review Changes vs. Walkthrough"
3. Compare the AI's reasoning to the Reference Architecture
4. Look for any red flags or drift indicators

Happy coding! 🛡️
