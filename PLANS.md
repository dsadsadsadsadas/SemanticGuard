# 🦅 Project Kodkod - Development Roadmap

Folder Main Name should be : KodKod

## Phase 1: The Observer (Dynamic Injection MVP)
**Goal:** Build a Python script (`kodkod.py`) that watches the file system and updates the AI's instructions in real-time based on the file being edited.

- [x] **Setup Environment**
    - [x] Create project folder `Kodkod`.
    - [x] Initialize git repository.
    - [x] Create virtual environment and install `watchdog` library.
    - [x] Create dummy file `.cursorrules` (target for injection).

- [x] **Core Logic Implementation (`kodkod.py`)**
    - [x] Import `watchdog` observers and event handlers.
    - [x] Define the `CONTEXT_RULES` dictionary (create prompts for: 'Security', 'GUI', 'Database', and 'Default').
    - [x] Implement `inject_context(filename)` function to determine which rule to pick based on file extension/name.
    - [x] Implement `FileSystemEventHandler` to trigger injection on file modification.

- [x] **Testing & Verification**
    - [x] Run the script locally.
    - [x] Create a test file `test_gui.css` and verify `.cursorrules` updates to "GUI Mode".
    - [x] Create a test file `test_secure.py` and verify `.cursorrules` updates to "Security Mode".

## Phase 2: The Watchdog (Loop Detection Logic)
**Goal:** Give Kodkod the ability to detect when the AI is repeating itself and forcefully break the loop.
**Mechanism:** Kodkod will monitor a specific file (`ai_trace.txt`). When text is added there, Kodkod analyzes it for repetition against a local history buffer.

- [x] **Memory Infrastructure**
    - [x] Update `kodkod.py` to include a `deque` (from collections) to store the last 3-5 AI responses (Short-Term Memory).
    - [x] Create a helper function `calculate_similarity(text1, text2)` using `difflib.SequenceMatcher`.

- [x] **The "Sniffer" Implementation**
    - [x] Create a new file `ai_trace.txt` in the root (this is where we will feed AI responses to be checked).
    - [x] Add a new specific watcher in `kodkod.py` that listens ONLY to `ai_trace.txt`.
    - [x] Implement `on_ai_response(text)`:
        - Check similarity against memory.
        - If Similarity > 85%: TRIGGER "EMERGENCY_BREAK" mode in `.cursorrules`.
        - If Similarity < 85%: Add to memory and stay in current mode.

- [x] **Define Emergency Protocol**
    - [x] Add a new context key `EMERGENCY_LOOP` to the `CONTEXT_RULES` dictionary.
    - [x] Content: "STOP. YOU ARE LOOPING. DISCARD PREVIOUS STRATEGY. CRITICAL RESET REQUIRED."

- [x] **Testing**
    - [x] Paste the same text 3 times into `ai_trace.txt` and verify `.cursorrules` switches to EMERGENCY LOOP mode.

## Phase 3: The Clipboard Brain (Smart & Safe)
**Goal:** Allow the user to "inject" context by copying their prompt to the clipboard. Kodkod analyzes it with Groq AI and updates `.cursorrules`.
**Model:** `llama-3.3-70b-versatile` on Groq (high intelligence + low latency).

- [x] **Setup**
    - [x] Create `requirements.txt` with pyperclip, groq, python-dotenv.
    - [x] Create `.env` with Groq API key and model.
    - [x] Install new dependencies.

- [x] **Core Implementation**
    - [x] Add `get_project_map()` helper function for project context.
    - [x] Implement `ClipboardBrain` class with threading.
    - [x] Add AI Gatekeeper with Groq - distinguishes prompts from code/AI responses.
    - [x] Implement "Echo" filter (>2000 chars = auto-ignore).
    - [x] **Antigravity Compatibility**: Switched from `.cursorrules` to `GEMINI.md`.
    - [x] **Optimization**: Added `ClipboardBrain` LRU Cache (Exact & 95% Fuzzy Match).
    - [x] **Smart Filter**: Increased char limit to 25k + Added "Project Relevance" check.

- [x] **Phase 4: Awareness & Automation**
    - [x] **Window Awareness**: Added `ctypes` check to only activate in IDEs (Antigravity/Cursor/etc).
    - [x] **Auto-Loop Detection**: Removed `ai_trace.txt`. Now analyzes Clipboard for AI Responses automatically.
    - [x] **Enhanced Logging**: Categorized logs (PROMPT / AI RESPONSE / IGNORED).

- [x] **Testing**
    - [x] Verify prompt detection vs code snippet ignore.
