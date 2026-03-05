# AI Assistant Autonomy - Flow Diagram

## Complete System Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER WRITES CODE                                │
│                    (with AI Assistant help)                             │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             │ Ctrl+S (Save)
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    VS CODE EXTENSION                                    │
│                  (extension/extension.js)                               │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ onWillSaveTextDocument Event                                     │  │
│  │ - Check if Trepan enabled                                        │  │
│  │ - Check if file excluded                                         │  │
│  │ - Check if server online                                         │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ event.waitUntil(evaluateSave())           │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ evaluateSave()                                                   │  │
│  │ - Read 5 pillars from .trepan/                                   │  │
│  │ - Extract code snippet (first 3000 chars)                        │  │
│  │ - Build payload with pillars + code                              │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
                              │ POST /evaluate
                              │ {golden_state, system_rules, user_command, ...}
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      TREPAN SERVER                                      │
│                   (trepan_server/server.py)                             │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ /evaluate Endpoint                                               │  │
│  │ - Receive code + 5 pillars                                       │  │
│  │ - Call build_prompt() with all context                           │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ build_prompt(...)                         │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ prompt_builder.py                                                │  │
│  │ - Format pillars into prompt template                            │  │
│  │ - Include AI Assistant Autonomy Protocol                         │  │
│  │ - Include 4 Evolutionary Logic Gates                             │  │
│  │ - Include [AI_ASSISTANT_ACTIONS] format                          │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ Full prompt with autonomy instructions    │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ generate_with_ollama()                                           │  │
│  │ - Send prompt to Ollama API                                      │  │
│  │ - Model: llama3.1:8b                                             │  │
│  │ - URL: http://localhost:11434                                    │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
                              │ Prompt with autonomy protocol
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    LLAMA 3.1 (via Ollama)                               │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ LLM Processing                                                   │  │
│  │ 1. Analyze code against pillars                                  │  │
│  │ 2. Check system_rules.md for violations                          │  │
│  │ 3. Compare against golden_state.md patterns                      │  │
│  │ 4. Search problems_and_resolutions.md for past failures          │  │
│  │ 5. Detect if this is error/solution/completion                   │  │
│  │ 6. Generate [AI_ASSISTANT_ACTIONS] if needed                     │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ Generate response                         │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Response Format:                                                 │  │
│  │                                                                  │  │
│  │ [THOUGHT]                                                        │  │
│  │ Analysis of code against pillars...                              │  │
│  │                                                                  │  │
│  │ [AI_ASSISTANT_ACTIONS]                                           │  │
│  │ APPEND_TO_FILE: .trepan/problems_and_resolutions.md             │  │
│  │ CONTENT: |                                                       │  │
│  │   ## Problem #7: Description (UNRESOLVED)                        │  │
│  │   **Date**: 2026-03-04                                           │  │
│  │   ...                                                            │  │
│  │                                                                  │  │
│  │ APPEND_TO_FILE: .trepan/system_rules.md                          │  │
│  │ CONTENT: |                                                       │  │
│  │   ## AI-Learned Rule #8                                          │  │
│  │   **NEVER** [approach] because [reason]                          │  │
│  │   ...                                                            │  │
│  │                                                                  │  │
│  │ [SCORE]                                                          │  │
│  │ 0.85                                                             │  │
│  │                                                                  │  │
│  │ [ACTION]                                                         │  │
│  │ REJECT                                                           │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
                              │ Return response
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      TREPAN SERVER                                      │
│                   (trepan_server/server.py)                             │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ guillotine_parser()                                              │  │
│  │ - Parse [ACTION] tag (ACCEPT/REJECT)                             │  │
│  │ - Parse [SCORE] tag (drift score)                                │  │
│  │ - Extract [THOUGHT] section (reasoning)                          │  │
│  │ - Keep full response for [AI_ASSISTANT_ACTIONS]                  │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ Return JSON                               │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Response JSON:                                                   │  │
│  │ {                                                                │  │
│  │   "verdict": "REJECT",                                           │  │
│  │   "score": 0.85,                                                 │  │
│  │   "reasoning": "[THOUGHT]\n...\n[AI_ASSISTANT_ACTIONS]\n..."    │  │
│  │ }                                                                │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
                              │ HTTP 200 OK
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    VS CODE EXTENSION                                    │
│                  (extension/extension.js)                               │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ evaluateSave() - Response Handler                                │  │
│  │ - Parse response JSON                                            │  │
│  │ - Extract verdict, score, reasoning                              │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ Call executeAIAssistantActions()          │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ executeAIAssistantActions(reasoning)                             │  │
│  │                                                                  │  │
│  │ 1. Extract [AI_ASSISTANT_ACTIONS] section using regex           │  │
│  │    Pattern: /\[AI_ASSISTANT_ACTIONS\]([\s\S]*?)(?:\[|$)/        │  │
│  │                                                                  │  │
│  │ 2. Parse APPEND_TO_FILE commands using regex                     │  │
│  │    Pattern: /APPEND_TO_FILE:\s*(.+?)\nCONTENT:\s*\|?\n(...)     │  │
│  │                                                                  │  │
│  │ 3. For each command:                                             │  │
│  │    - Resolve full file path                                      │  │
│  │    - Check if file exists                                        │  │
│  │    - Read existing content                                       │  │
│  │    - Append new content with proper newlines                     │  │
│  │    - Log success/failure                                         │  │
│  │                                                                  │  │
│  │ 4. Show notification if any commands executed                    │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ File operations complete                  │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Pillar Files Updated:                                            │  │
│  │ - .trepan/problems_and_resolutions.md (new problem added)        │  │
│  │ - .trepan/system_rules.md (new rule added)                       │  │
│  │ - .trepan/golden_state.md (new pattern added)                    │  │
│  │ - .trepan/history_phases.md (new entry added)                    │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ Send to sidebar                           │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ trepanSidebarProvider.sendMessage()                              │  │
│  │ - Display audit result in sidebar                                │  │
│  │ - Show verdict (ACCEPT/REJECT)                                   │  │
│  │ - Show drift score                                               │  │
│  │ - Show reasoning (collapsible)                                   │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
│                             │                                           │
│                             │ Handle verdict                            │
│                             ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ IF verdict === "REJECT":                                         │  │
│  │   - Show modal error dialog                                      │  │
│  │   - Block save (throw error)                                     │  │
│  │   - Offer "Override & Save Anyway"                               │  │
│  │   - Offer "Open system_rules.md"                                 │  │
│  │                                                                  │  │
│  │ IF verdict === "ACCEPT":                                         │  │
│  │   - Allow save to proceed                                        │  │
│  │   - Show green checkmark in status bar                           │  │
│  │   - Log success                                                  │  │
│  └──────────────────────────┬───────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
                              │ Show notification
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER NOTIFICATION                               │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 🤖 Trepan AI Autonomy: Executed 2 pillar update(s)              │  │
│  │                                                                  │  │
│  │ [View Changes]                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Console Logs:                                                          │
│  [TREPAN AI AUTONOMY] Found actions section: APPEND_TO_FILE...         │
│  [TREPAN AI AUTONOMY] Executing: APPEND_TO_FILE .trepan/problems...    │
│  [TREPAN AI AUTONOMY] ✅ Successfully appended to problems...           │
│  [TREPAN AI AUTONOMY] Executing: APPEND_TO_FILE .trepan/system_rules...│
│  [TREPAN AI AUTONOMY] ✅ Successfully appended to system_rules...       │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              │ User clicks "View Changes"
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         GIT SOURCE CONTROL                              │
│                                                                         │
│  Modified Files:                                                        │
│  M .trepan/problems_and_resolutions.md                                  │
│  M .trepan/system_rules.md                                              │
│                                                                         │
│  User can:                                                              │
│  - Review diffs                                                         │
│  - Commit changes                                                       │
│  - Revert if needed                                                     │
│  - Edit manually                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Extension Action Executor
- **Location**: `extension/extension.js`
- **Function**: `executeAIAssistantActions()`
- **Purpose**: Parse and execute file operations from LLM response

### 2. Prompt Builder
- **Location**: `trepan_server/prompt_builder.py`
- **Function**: `build_prompt()`
- **Purpose**: Format pillars and include AI Autonomy Protocol

### 3. LLM Evaluation
- **Location**: Ollama (http://localhost:11434)
- **Model**: llama3.1:8b
- **Purpose**: Analyze code and generate autonomous actions

### 4. Response Parser
- **Location**: `trepan_server/response_parser.py`
- **Function**: `guillotine_parser()`
- **Purpose**: Extract verdict, score, and reasoning

## Autonomous Actions

### Action Type 1: Problem Recording
```
APPEND_TO_FILE: .trepan/problems_and_resolutions.md
CONTENT: |
  ## Problem #N: Description (UNRESOLVED)
  **Date**: YYYY-MM-DD
  **AI Generated**: Yes
  **Description**: What failed
  **Status**: UNRESOLVED
```

### Action Type 2: Negative Rule Generation
```
APPEND_TO_FILE: .trepan/system_rules.md
CONTENT: |
  ## AI-Learned Rule #N
  **NEVER** [approach] because [reason]
  **Context**: [when this applies]
  **Learned**: YYYY-MM-DD
```

### Action Type 3: Success Pattern Extraction
```
APPEND_TO_FILE: .trepan/golden_state.md
CONTENT: |
  ## AI-Discovered Pattern: [name]
  **Learned**: YYYY-MM-DD
  **Use Case**: [when to use]
  **Implementation**: [how it works]
  **Why It Works**: [explanation]
```

### Action Type 4: History Update
```
APPEND_TO_FILE: .trepan/history_phases.md
CONTENT: |
  ## AI Task: YYYY-MM-DD
  **Completed**: [what was done]
  **Approach**: [how it was done]
  **Problems**: [link to problems if any]
  **Outcome**: [result]
```

## Error Handling Flow

```
executeAIAssistantActions()
  │
  ├─ No [AI_ASSISTANT_ACTIONS] section?
  │  └─ Log: "No actions section found" → Return
  │
  ├─ No workspace folder?
  │  └─ Log: "No workspace open" → Return
  │
  ├─ For each APPEND_TO_FILE command:
  │  │
  │  ├─ File not found?
  │  │  └─ Log: "File not found - skipping" → Continue
  │  │
  │  ├─ Permission denied?
  │  │  └─ Log: "Permission denied" → Continue
  │  │
  │  └─ Success?
  │     └─ Log: "✅ Successfully appended" → Continue
  │
  └─ Show notification if any commands executed
```

## Status Indicators

### Status Bar
- **Online**: `$(shield) Trepan ✅` (green)
- **Checking**: `$(shield) Trepan 🔄` (yellow)
- **Accepted**: `$(shield) Trepan ✅` (blue highlight)
- **Offline**: `$(shield) Trepan ⚫` (gray)

### Sidebar
- **Scanning**: Spinner animation while evaluating
- **Accept**: Green checkmark with reasoning
- **Reject**: Red stop sign with reasoning + revert button
- **Error**: Orange warning with reasoning

### Notifications
- **Pillar Updates**: `🤖 Trepan AI Autonomy: Executed N pillar update(s)`
- **Save Blocked**: `🛑 Trepan Blocked Save — Drift Score: X.XX`
- **Save Accepted**: Status bar turns blue briefly

## Benefits Summary

1. **Zero Manual Work**: AI maintains pillars automatically
2. **Self-Learning**: System gets smarter with each interaction
3. **Prevents Mistakes**: Negative rules block repeated failures
4. **Extracts Patterns**: Success patterns become templates
5. **Tracks Evolution**: History shows project learning
6. **Transparent**: All changes visible in Git
7. **Reversible**: Can revert any automatic update
8. **Fail-Safe**: Errors don't block saves (fail-open)

---

**The AI coding assistants are now truly autonomous!** 🤖🛡️
