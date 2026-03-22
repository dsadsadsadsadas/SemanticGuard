# Trepan v2.0.0 Release Notes

## 🚀 Major Release: Layer 1 Deterministic Pre-Screener

This is a major architectural upgrade introducing a two-layer security analysis system.

---

## 🎯 What's New

### Layer 1: Deterministic Pre-Screener (NEW)
Trepan now catches obvious security violations instantly using regex and AST pattern matching - no model inference required, zero GPU usage, sub-100ms response time.

**Performance Impact:**
- Obvious violations: < 0.1 seconds (20-50x faster)
- Clean code: Same speed as before (passes through to model)
- Zero false negatives (Layer 1 only catches confirmed violations)

**10 Security Rules Implemented:**

**CRITICAL Severity:**
- L1-001: Hardcoded secrets/API keys
- L1-002: eval() with user input (RCE risk)
- L1-003: subprocess with shell=True (command injection)
- L1-008: pickle.load() with user input (arbitrary code execution)

**HIGH Severity:**
- L1-004: SQL string concatenation (SQL injection)
- L1-005: console.log() with sensitive data
- L1-006: print() with sensitive data
- L1-007: Error stack traces in API responses

**MEDIUM Severity:**
- L1-009: Assert statements for security checks
- L1-010: Bare except clauses (silent failures)

### Architecture: Two-Layer System

```
File Save
    ↓
┌─────────────────────────────────┐
│ LAYER 1: Deterministic Screener │ ← NEW
│ - Regex + AST pattern matching   │
│ - < 100ms response time          │
│ - Zero GPU usage                 │
└─────────────────────────────────┘
    ↓
    ├─ REJECT? → Block save immediately
    │
    └─ ACCEPT? → Continue to Layer 2
                     ↓
              ┌──────────────────┐
              │ LAYER 2: Model   │ ← Existing
              │ - Llama 3.1:8b   │
              │ - DeepSeek R1    │
              │ - Complex logic  │
              └──────────────────┘
```

---

## 🔧 Improvements from v1.1.0

### Model Configuration
- **Default Model**: Llama 3.1:8b (better out-of-box experience)
- **DeepSeek R1 Fix**: Increased token budget to 4000 (was 800) to accommodate thinking blocks
- **JSON Schema Enforcement**: Models can no longer hallucinate invalid fields

### Prompt Engineering
- Separated prompt strategies: minimal for Llama, detailed for DeepSeek
- Universal JSON reminder for all models
- Pre-analysis hints to reduce false positives on clean code

### Gate Logic Enhancements
- **Gate 2**: Dual-check system (AST + expression-based) for literal detection
- **Gate 4**: Allows specific REJECTs with line references while blocking vague rejections

### Developer Experience
- Rate-limited health check logging (once per 60 seconds)
- Improved console output clarity
- Better error messages

---

## 📊 Test Coverage

**Total Tests**: 40 (all passing)
- 15 Layer 1 unit tests
- 25 existing tests (no regressions)

**Test Execution Time**: 0.12 seconds

---

## 🎬 Demo

See Layer 1 in action catching violations instantly:

![Trepan catching violations](images/Screen%20Recording%202026-03-22%20051920.mp4)

---

## 📦 Installation

### From VSIX
```bash
code --install-extension trepan-gatekeeper-2.0.0.vsix
```

Or in VS Code: Extensions → ... → Install from VSIX

### Requirements
- Python 3.11+
- Ollama with llama3.1:8b model
- 8GB RAM minimum (16GB recommended)

---

## 🔄 Upgrade Notes

### From v1.1.0
No breaking changes. Simply install the new version and restart VS Code.

### Configuration
All existing settings are preserved. No configuration changes required.

### Models
- Default model is now `llama3.1:8b` (was `deepseek-r1:latest`)
- You can switch models via Command Palette: "Trepan: Select Audit Model"

---

## 🐛 Bug Fixes

- Fixed DeepSeek R1 returning 0 characters (token budget issue)
- Fixed Llama 3.1:8b returning prose instead of JSON
- Fixed syntax error in start_server.py
- Fixed Gate 4 blocking valid REJECTs with specific reasons
- Enhanced Gate 2 literal string detection

---

## 🔍 Technical Details

### Files Modified
- `trepan_server/server.py` - Layer 1 integration
- `trepan_server/model_loader.py` - Model configuration & JSON schema enforcement
- `trepan_server/prompt_builder.py` - Prompt strategy separation
- `trepan_server/response_parser.py` - Enhanced gate logic
- `extension/extension.js` - Default model selection

### New Files
- `trepan_server/engine/layer1/screener.py` - Layer 1 implementation
- `trepan_server/tests/test_layer1_screener.py` - Layer 1 tests

---

## 📈 Performance Comparison

### Before v2.0.0
- Every file: 2-5 seconds (GPU) or 10-30 seconds (CPU)
- Obvious violations: Still require full model inference

### After v2.0.0
- Obvious violations: < 0.1 seconds (Layer 1 catches instantly)
- Clean code: 2-5 seconds (same as before, passes to model)
- Complex violations: 2-5 seconds (same as before, requires model)

**Expected Speedup**: 20-50x for files with deterministic violations

---

## 🙏 Acknowledgments

Thanks to all users who reported issues and provided feedback on v1.1.0.

---

## 📝 Full Changelog

**Added:**
- Layer 1 deterministic pre-screener with 10 security rules
- 15 new unit tests for Layer 1
- JSON schema enforcement at Ollama API level
- Pre-analysis hints for clean code
- Enhanced literal string detection (dual-check system)

**Changed:**
- Default model from DeepSeek R1 to Llama 3.1:8b
- DeepSeek R1 token budget increased to 4000
- Prompt strategies separated by model type
- Gate 4 logic to allow specific REJECTs

**Fixed:**
- DeepSeek R1 0-character output issue
- Llama 3.1:8b JSON format compliance
- start_server.py syntax error
- Gate 2 literal detection edge cases
- Gate 4 blocking valid specific REJECTs

**Performance:**
- 20-50x speedup for obvious violations
- Sub-100ms response time for Layer 1 catches
- Zero GPU usage for deterministic violations

---

## 🔗 Links

- **GitHub**: https://github.com/dsadsadsadsadas/Trepan
- **Issues**: https://github.com/dsadsadsadsadas/Trepan/issues
- **Documentation**: See README.md

---

**Version**: 2.0.0  
**Release Date**: March 22, 2026  
**License**: AGPL-3.0-only
