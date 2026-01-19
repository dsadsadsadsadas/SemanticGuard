# Implementation Plan - Phase 4: Awareness & Automation

# [Goal Description]
Enhance Kodkod with "Active Window Awareness" to valid context injection only when working in the IDE, and automate Loop Detection by analyzing clipboard content (detecting if the user is copying AI responses) instead of requiring manual paste to file.

## User Review Required
> [!IMPORTANT]
> **Clipboard Loop Detection Logic Change:**
> Instead of manually pasting to `ai_trace.txt`, Kodkod will now analyze CLIPBOARD content.
> - If Clipboard starts with typical AI phrases ("Here is the code", "I understand", "Certainly") OR looks like a big Markdown block -> It treats it as an **AI Response** and checks for loops.
> - If Clipboard looks like a User Prompt -> It treats it as a **Prompt** and generates rules (Phase 3).
> **This unifies everything into the Clipboard.** No more `ai_trace.txt` needed!

## Proposed Changes

### [kodkod.py]
#### [MODIFY] [kodkod.py](file:///c:/Users/ethan/Documents/Projects/KodKod/kodkod.py)
1.  **Window Awareness (`get_active_window_title`)**:
    *   Add `ctypes` based function to get foreground window title.
    *   In `ClipboardBrain.monitor`, check if title contains keywords: `['Antigravity', 'Cursor', 'Code', 'Manager', 'Windsurf']`.
    *   If NOT in IDE -> Ignore clipboard (prevent cross-app pollution).

2.  **Automated Loop Detection**:
    *   Modify `ClipboardBrain`:
        *   **IF** text looks like an AI Response (Heuristics: "Here's the fix", Markdown blocks, >80% code) -> **Send to LoopSniffer**.
        *   **IF** LoopSniffer finds duplicate -> Trigger Emergency.
        *   **ELSE** -> Cache it in memory (cleared on exit).
    *   Remove file-based `LoopSniffer` watching `ai_trace.txt`.

3.  **Enhanced Console Logging**:
    *   **Prompt**: "📝 [PROMPT] Saved to context: 'Fix bug...'"
    *   **AI Response**: "🤖 [AI RESPONSE] Cached for loop detection (Length: 1500)"
    *   **Ignored**: "🚫 [IGNORED] (Not unrelated / Not in IDE)"

## Verification Plan
### Automated Tests
- Mock `pyperclip` and `ctypes` to simulate:
    - User in "Chrome" -> Kodkod ignores copy.
    - User in "GoodGame - Antigravity" -> Kodkod accepts copy.
    - Loop Check: Copy same AI response 3 times -> Emergency trigger.

### Manual Verification
1.  Run Kodkod.
2.  Focus Browser -> Copy text -> Rules NOT updated.
3.  Focus IDE -> Copy Prompt -> Rules updated.
4.  Focus IDE -> Copy AI Response twice -> "LOOP DETECTED" warning.
