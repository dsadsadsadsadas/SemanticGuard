# TREPAN MASTER DESIGN DOCUMENT
**Role:** DevSecOps Enforcer & Policy Guardrails
**Version:** 3.0 (Enterprise Readiness Edition)
**Date:** January 19, 2026

---

## 1. Core Philosophy: Enterprise Readiness

### 1.1 The Shift to DevSecOps
Legacy productivity tools rely on fragile Regex patterns and constant, noisy AI chatter. Trepan creates a new category: **The DevSecOps Enforcer**.
We move beyond simple "coding assistance" to provide architectural assurance. Our primary directive is **Privacy First**: No proprietary code leaves the local environment without explicit, granular user action (Opt-in).

### 1.2 "Blind AI" vs. Policy Enforcement
Instead of trusting the AI to behave, Trepan enforces security context deterministically.
*   **Old Way:** "Hope the AI knows security."
*   **New Way:** Local AST analysis enforces hard rules before code is ever committed.

---

## 2. Feature Specification (Revised)

### A. The AST Engine (Foundation)
*   **Technology:** Python `ast` Module (Abstract Syntax Tree).
*   **Priority:** 10/10 (Critical Path).
*   **Logic:** Unlike Regex, which simply scans for text patterns, the AST engine understands the *structure* and *logic* of the code.
*   **Capabilities:**
    *   Detects **Hardcoded Secrets** assigned to variables.
    *   Identifies **Unsafe Logging** (print statements leaking PII).
    *   Trace data flow to find unvalidated inputs.

### B. Supply Chain Sentinel
*   **Target:** `requirements.txt`, `package.json`, `pyproject.toml`.
*   **Policy:** **Warn & Block**.
*   **Constraint:** ALWAYS user-mediated. **NEVER auto-delete** files.
*   **Logic:**
    *   Scans dependencies against known vulnerability databases (CVEs).
    *   Detects **Typosquatting** attacks.
    *   Alerts the user and prevents installation/commit until resolved.

### C. Shadow Red Teamer (On-Demand)
*   **Trigger:** **Manual Only** (e.g., Command: "Trepan, attack this function").
*   **Role:** AI-Assisted Threat Modeling.
*   **Privacy:** Solves GDPR and IP concerns by sending *only* the specific function context when explicitly requested.
*   **Output:** Generates **Theoretical Attack Vectors** (e.g., "This logic enables a Race Condition via...") rather than just script chaos.
*   **UX:** Prevents "Alert Fatigue" by remaining silent until summoned.

---

## 3. Architecture & Data Flow

### 3.1 Architecture Overview
The system is designed as a **Local-First** enforcement layer with an optional cloud extension.

```text
[ Developer Machine ]
      |
      +--- [ Local File System ] <--- (Watchdog) ---+
      |                                             |
      +--- [ AST Engine ] --------------------------+---> ( 1. Structural Analysis )
      |    (Python 'ast' / Local Policy DB)         |
      |                                             +---> [ Policy Enforcer ]
      |                                             |     (Block/Warn/Inject Context)
      +--- [ Supply Chain Sentinel ] ---------------+
      |
      |
      +--- [ On-Demand Bridge ] ---> (Explicit User Trigger Only)
                |
                v
      [ Secure Cloud Gateway ]
                |
                v
      [ LLM (Llama-3-70b) ] ---> ( 2. Shadow Red Team Analysis )
```

### 3.2 Key Components
*   **Local AST Engine:** The core brain. fast, private, and deterministic. Run completely offline.
*   **Local Policy DB:** A curated set of security rules (OWASP, CWE) mapped to AST patterns.
*   **Cloud Gateway (Optional):** The "Shadow Red Teamer" that provides deep reasoning only when explicitly invited.

---

## 4. Why This Matters (The Enterprise Pitch)
*   **Compliance Ready:** Designed for GDPR/SOC2 environments where data exfiltration is a hard blocker.
*   **No False Positives:** AST analysis drastically reduces the noise associated with Regex-based linters.
*   **The "Human in the Loop":** We empower the senior engineer, we don't try to replace them or annoy them with constant chatter.

---

## 5. Implementation Progress

### Phase 5: Polyglot Taint Analysis Engine ✅ (2026-01-20)
**Status:** Complete - All 3 Steps Finished

#### Step 1: Infrastructure Skeleton ✅ (2026-01-20)
- [x] Created `taint_engine.py` - PolyglotTaintEngine class with language detection
- [x] Created `parsers/base_parser.py` - Abstract BaseSecurityParser interface
- [x] Created `parsers/js_parser.py` - JavascriptParser with source/sink patterns
- [x] Verified all imports and basic functionality

#### Step 2: Parser Logic (Pending)
- [ ] Implement full taint flow tracking
- [ ] Add tree-sitter integration for accurate AST
- [ ] Connect Python analysis via ast_engine.py

#### Step 2: Heuristic Taint Logic ✅ (2026-01-20)
- [x] Implemented `scan()` method with 3-step analysis
- [x] Step A: Source Discovery - Tracks tainted variables
- [x] Step B: Sink Detection - Finds dangerous operations
- [x] Step C: Taint Connection - Links tainted data to sinks
- [x] Added sanitization detection to reduce false positives
- [x] Tested: 3 critical issues found, sanitized input correctly skipped

#### Step 3: Integration ✅ (2026-01-20)
- [x] Integrated PolyglotTaintEngine into trepan.py file watcher
- [x] TREPANEventHandler now scans .py, .js, .ts, .jsx, .tsx files
- [x] Python files: Legacy AST scan + Polyglot engine
- [x] JavaScript files: Full heuristic taint analysis
- [x] Tested: 3 vulnerabilities found in test_vuln.js (RCE, XSS, PATH_TRAVERSAL)

### Phase 9: Package Sentinel ✅ (2026-01-20)
- [x] Implemented `package_sentinel.py` - Supply chain security
- [x] Typosquatting detection (Levenshtein distance)
- [x] Package age/reputation checks
- [x] Blocklist/Allowlist support
- [x] All tests passed (5/5)

