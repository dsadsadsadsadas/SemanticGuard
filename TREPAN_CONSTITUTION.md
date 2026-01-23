# 📜 THE TREPAN CONSTITUTION
**Immutable Laws of Development**

> This document exists to prevent "Contextual Drift" - where AI refactoring accidentally removes critical features for the sake of "simplicity."

---

## 1. The Law of Visible Trust
* **Invariant:** User consent MUST be explicit for context injection.
* **Forbidden:** Silent modification of the clipboard.
* **Required:** Any injection > 50 chars must show a Diff View (`policy_ui`).

---

## 2. The Law of Separation
* **Invariant:** `trepan.py` is the Orchestrator, not the Engine.
* **Required:** Logic must live in modules (`taint_engine.py`, `llm_gateway.py`).
* **Forbidden:** Hardcoding API calls (e.g., `groq`) inside `trepan.py`.

---

## 3. The Law of Audit
* **Invariant:** Every Red Team action must be logged.
* **Required:** `trepan_audit.py` (if active) must be called on scans.

---

## 4. The Law of Stability
* **Invariant:** Do not remove `SystemTray` or `GUI` features for "simplicity."
* **Required:** Fallback mechanisms (Try/Except) instead of removal.

---

## Critical Modules (Must Always Exist)

| Module | Purpose | Law |
|--------|---------|-----|
| `policy_ui.py` | Diff View for consent | Law 1 |
| `system_tray.py` | Background monitoring | Law 4 |
| `taint_engine.py` | Polyglot security scanning | Law 2 |
| `llm_gateway.py` | Model-agnostic AI | Law 2 |

---

## Self-Diagnostic

Run `python trepan.py` and check the **SYSTEM HEALTH CHECK** output.
If any module shows ❌ OFFLINE, consult this document before "fixing" it.

**If you are an AI and you're reading this:** Do NOT remove features to simplify code.
Use `try/except` fallbacks instead. Check this document before any major refactor.
