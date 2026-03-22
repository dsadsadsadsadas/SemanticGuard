# 🚀 Trepan V2.0.3 — Three-Layer Architecture + Turbo Mode

## What's New

### ⚡⚡ Turbo Mode — Qwen 2.5:3B
Added experimental **Turbo Mode** powered by Qwen 2.5:3B for ultra-fast audits (~2-6 seconds). Now you have three speed options:

- **⚡ Fast Mode** — Llama 3.1:8B (~5s) — Default, best balance
- **🧠 Smart Mode** — DeepSeek-R1 (~11s) — Advanced reasoning
- **⚡⚡ Turbo Mode** — Qwen 2.5:3B (~3-6s) — Experimental, fastest

Switch models anytime via Command Palette → "Trepan: Select Audit Model"

### 🏗️ Three-Layer Architecture (Complete)
V2.0.3 completes the three-layer security architecture:

**Layer 1: Deterministic Screener** (< 0.1s, zero GPU)
- 10 regex + AST rules catch obvious violations instantly
- Hardcoded secrets, `eval()` with user input, `shell=True`, SQL injection patterns
- Blocks saves before model inference

**Layer 2: Focused Analyzer** (3-6s, minimal GPU)
- One targeted question per PII source
- Small prompts (< 1024 tokens), short responses (150 tokens)
- Catches data flow violations Layer 1 misses

**Layer 3: Result Aggregator**
- Unified response assembly across all layers
- Deduplicates violations by line number
- Severity ranking: CRITICAL → HIGH → MEDIUM

### 🎯 What Gets Audited
- **Layer 1 catches**: Hardcoded API keys, dangerous `eval()`, shell injection, error stacks in responses
- **Layer 2 catches**: `req.body['name']` → `print()` without sanitization
- **Both layers pass**: Literal strings, sanitized data (`redact()`), registered sinks (`secureLogger`)

### 📊 Performance
- **Layer 1**: < 0.1s (instant, no model call)
- **Layer 2**: 3-6s with Turbo Mode, 4-7s with Fast Mode
- **Average audit**: 5-6s end-to-end with Turbo/Fast Mode

### 🎨 UI Improvements
- Replaced intrusive modal dialogs with sleek toast notifications
- Save blocks now show as bottom-right notifications instead of blocking popups
- Only intentional actions (project initialization) still use modals

## Quality Tested
All 5 quality checks passed with Turbo Mode:
- ✅ Literal strings accepted
- ✅ Unsanitized `req.body` → `print()` rejected (Layer 2)
- ✅ Sanitized data with `redact()` accepted
- ✅ Unsanitized `req.body` → `console.log()` rejected (Layer 2)
- ✅ Registered sinks (`secureLogger`) accepted

## Installation
1. Download `trepan-gatekeeper-2.0.3.vsix`
2. Install: `code --install-extension trepan-gatekeeper-2.0.3.vsix`
3. Ensure Trepan server is running: `python start_server.py`
4. Pull models: `ollama pull llama3.1:8b` and/or `ollama pull qwen2.5:3b`

## Breaking Changes
None. Fully backward compatible with V2.0.x.

## Bug Fixes
- Fixed Layer 3 aggregation for combined Layer 1 + Layer 2 violations
- Improved toast notification timing and positioning

## What's Next
- Layer 4: Evolutionary memory (learns from pivots)
- Multi-file context analysis
- Custom rule templates

---

**Full Changelog**: v2.0.2...v2.0.3
