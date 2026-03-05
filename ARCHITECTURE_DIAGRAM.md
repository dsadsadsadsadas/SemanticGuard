# Trepan Closed-Loop Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TREPAN GATEKEEPER SYSTEM                        │
│                         (Closed-Loop Architecture)                      │
└─────────────────────────────────────────────────────────────────────────┘

                                   ┌──────────┐
                                   │   USER   │
                                   │  Saves   │
                                   │   File   │
                                   └────┬─────┘
                                        │
                                        ▼
                    ┌───────────────────────────────────┐
                    │   VS CODE EXTENSION (Airbag)      │
                    │   extension/extension.js          │
                    └───────────────┬───────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
        ┌───────────────────┐         ┌───────────────────┐
        │  Standard File    │         │  Pillar File      │
        │  (*.py, *.js)     │         │  (.trepan/*.md)   │
        └─────────┬─────────┘         └─────────┬─────────┘
                  │                             │
                  ▼                             ▼
        ┌───────────────────┐         ┌───────────────────┐
        │  POST /evaluate   │         │ POST /evaluate_   │
        │                   │         │      pillar       │
        └─────────┬─────────┘         └─────────┬─────────┘
                  │                             │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  TREPAN SERVER         │
                    │  trepan_server/        │
                    │  server.py             │
                    └────────────┬───────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
    ┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
    │  Read Pillars    │ │  Build       │ │  Load Model  │
    │  - golden_state  │ │  Prompt      │ │  (8B LLM)    │
    │  - system_rules  │ │              │ │              │
    │  - done_tasks    │ │              │ │              │
    └────────┬─────────┘ └──────┬───────┘ └──────┬───────┘
             │                  │                │
             └──────────────────┼────────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │  LLM INFERENCE         │
                    │  model_loader.py       │
                    │  generate(prompt)      │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  RAW OUTPUT            │
                    │  [THOUGHT] ...         │
                    │  [SCORE] 0.15          │
                    │  [ACTION] ACCEPT       │
                    │  (+ possible yap)      │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  GUILLOTINE PARSER     │
                    │  response_parser.py    │
                    │  guillotine_parser()   │
                    └────────────┬───────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
    ┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
    │  Extract         │ │  Validate    │ │  Clean       │
    │  - verdict       │ │  - Use LAST  │ │  - Remove    │
    │  - score         │ │    [ACTION]  │ │    post-     │
    │  - reasoning     │ │  - Override  │ │    action    │
    │                  │ │    if score  │ │    yap       │
    │                  │ │    >= 0.40   │ │              │
    └────────┬─────────┘ └──────┬───────┘ └──────┬───────┘
             │                  │                │
             └──────────────────┼────────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │  PARSED RESULT         │
                    │  {                     │
                    │    verdict: "ACCEPT",  │
                    │    score: 0.15,        │
                    │    reasoning: "..."    │
                    │  }                     │
                    └────────────┬───────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
                ▼                ▼                ▼
    ┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
    │  Append to       │ │  Return to   │ │  Optional:   │
    │  Walkthrough.md  │ │  Extension   │ │  Closed-Loop │
    │                  │ │              │ │  Audit       │
    │  append_audit_   │ │  ACCEPT →    │ │              │
    │  ledger()        │ │  Allow Save  │ │  POST /audit_│
    │                  │ │              │ │  reasoning   │
    │  ## 2026-03-04   │ │  REJECT →    │ │              │
    │  Result: ACCEPT  │ │  Block Save  │ │              │
    │  Thought: ...    │ │              │ │              │
    └────────┬─────────┘ └──────┬───────┘ └──────┬───────┘
             │                  │                │
             │                  │                ▼
             │                  │    ┌──────────────────────┐
             │                  │    │  verify_against_     │
             │                  │    │  ledger()            │
             │                  │    │                      │
             │                  │    │  1. Read first 50    │
             │                  │    │     lines of         │
             │                  │    │     Walkthrough.md   │
             │                  │    │     (Reference       │
             │                  │    │     Architecture)    │
             │                  │    │                      │
             │                  │    │  2. Compare current  │
             │                  │    │     reasoning vs     │
             │                  │    │     reference        │
             │                  │    │                      │
             │                  │    │  3. Detect:          │
             │                  │    │     - Hallucinations │
             │                  │    │     - Rule violations│
             │                  │    │     - Drift          │
             │                  │    └──────────┬───────────┘
             │                  │               │
             │                  │               ▼
             │                  │    ┌──────────────────────┐
             │                  │    │  AUDIT RESULT        │
             │                  │    │  ACCEPT or REJECT    │
             │                  │    └──────────────────────┘
             │                  │
             └──────────────────┼────────────────────────────┐
                                │                            │
                                ▼                            │
                    ┌────────────────────────┐               │
                    │  USER NOTIFICATION     │               │
                    │                        │               │
                    │  ACCEPT:               │               │
                    │  ✅ Save allowed       │               │
                    │  Status bar: green     │               │
                    │                        │               │
                    │  REJECT:               │               │
                    │  🛑 Save blocked       │               │
                    │  Modal error dialog    │               │
                    │  Show reasoning        │               │
                    └────────────┬───────────┘               │
                                 │                           │
                                 ▼                           │
                    ┌────────────────────────┐               │
                    │  HUMAN REVIEW          │               │
                    │  (Optional)            │               │
                    │                        │               │
                    │  Command:              │               │
                    │  "Review Changes vs.   │               │
                    │   Walkthrough"         │               │
                    │                        │               │
                    │  trepan.reviewWith     │               │
                    │  Ledger                │               │
                    └────────────┬───────────┘               │
                                 │                           │
                                 ▼                           │
                    ┌────────────────────────┐               │
                    │  SPLIT EDITOR VIEW     │               │
                    │                        │               │
                    │  ┌──────┬──────────┐   │               │
                    │  │ Code │ Ledger   │   │               │
                    │  │      │          │   │               │
                    │  │ Left │ Right    │   │               │
                    │  │      │ (auto-   │   │               │
                    │  │      │ scrolled)│   │               │
                    │  └──────┴──────────┘   │               │
                    │                        │               │
                    │  User compares:        │               │
                    │  - Code changes        │               │
                    │  - AI reasoning        │               │
                    │  - Reference Arch      │               │
                    └────────────────────────┘               │
                                                             │
                                                             │
┌────────────────────────────────────────────────────────────┘
│
│  WALKTHROUGH.MD STRUCTURE
│
│  ┌─────────────────────────────────────────────────────┐
│  │ # Trepan Architectural Audit & Tutorial             │
│  │                                                      │
│  │ ## Reference Architecture (The Ground Truth)        │
│  │ ┌─────────────────────────────────────────────────┐ │
│  │ │ Core Principles:                                │ │
│  │ │ 1. Contextual Alignment                         │ │
│  │ │ 2. Rule Compliance                              │ │
│  │ │ 3. Architectural Consistency                    │ │
│  │ │ 4. Security First                               │ │
│  │ │                                                 │ │
│  │ │ Perfect Execution Example:                      │ │
│  │ │ [Shows ideal reasoning pattern]                 │ │
│  │ │                                                 │ │
│  │ │ Hallucination Indicators:                       │ │
│  │ │ [Lists red flags to watch for]                  │ │
│  │ └─────────────────────────────────────────────────┘ │
│  │                                                      │
│  │ ---                                                  │
│  │                                                      │
│  │ # Live Audit History                                │
│  │ ┌─────────────────────────────────────────────────┐ │
│  │ │ ## 2026-03-04 14:32:15 | Result: ACCEPT        │ │
│  │ │ **Thought Process:**                            │ │
│  │ │ > The user is adding a new feature...           │ │
│  │ │                                                 │ │
│  │ │ ## 2026-03-04 14:35:22 | Result: REJECT        │ │
│  │ │ **Thought Process:**                            │ │
│  │ │ > The code introduces eval() which violates...  │ │
│  │ │                                                 │ │
│  │ │ ## 2026-03-04 14:40:11 | Result: ACCEPT        │ │
│  │ │ **Thought Process:**                            │ │
│  │ │ > The refactored code now uses parameterized... │ │
│  │ └─────────────────────────────────────────────────┘ │
│  └─────────────────────────────────────────────────────┘
│
└──────────────────────────────────────────────────────────
```

## Data Flow Summary

### 1. Save Event
```
User saves file → Extension intercepts → Sends to server
```

### 2. Primary Gate
```
Server → Read pillars → Build prompt → LLM inference → Parse output → Decision
```

### 3. Logging
```
Decision → Append to Walkthrough.md with timestamp
```

### 4. Closed-Loop Audit (Optional)
```
Reasoning → Compare vs Reference Architecture → Detect drift → Report
```

### 5. Human Review
```
Command → Split editor → Code + Ledger side-by-side → Manual verification
```

## Key Components

### Parser (Guillotine Strategy)
```
Raw LLM Output → Find LAST [ACTION] → Extract verdict/score/reasoning → Clean yap
```

### Audit Ledger (Walkthrough.md)
```
Reference Architecture (lines 1-50) + Live History (lines 51+)
```

### Extension Commands
```
- trepan.openLedger: Open ledger in new tab
- trepan.reviewWithLedger: Split view with auto-scroll
- trepan.askGatekeeper: Interactive query
```

## Security Layers

### Layer 1: Vault Cryptography
```
SHA-256 hash of all pillars → Stored in .trepan.lock → Tamper detection
```

### Layer 2: Primary Gate
```
LLM evaluates code → Checks rules → ACCEPT or REJECT
```

### Layer 3: Closed-Loop Audit
```
LLM compares reasoning → Checks for drift → ACCEPT or REJECT
```

### Layer 4: Human Review
```
Developer reviews ledger → Verifies AI reasoning → Manual override if needed
```

## File Locations

```
Project Root/
├── .trepan/
│   ├── golden_state.md          (Architecture definition)
│   ├── system_rules.md           (Security & style rules)
│   ├── done_tasks.md             (Completed work)
│   ├── pending_tasks.md          (TODO list)
│   ├── history_phases.md         (Project timeline)
│   ├── problems_and_resolutions.md (Known issues)
│   ├── Walkthrough.md            (Audit ledger) ← NEW!
│   ├── .trepan.lock              (Cryptographic signature)
│   └── trepan_vault/             (Frozen snapshots)
│       ├── golden_state.md
│       ├── system_rules.md
│       └── ...
├── trepan_server/
│   ├── server.py                 (FastAPI server) ← UPDATED!
│   ├── response_parser.py        (Guillotine parser) ← UPDATED!
│   ├── model_loader.py           (LLM interface)
│   └── prompt_builder.py         (Prompt construction)
└── extension/
    ├── extension.js              (VS Code extension) ← UPDATED!
    └── package.json              (Extension manifest)
```

## API Endpoints

```
GET  /health                      → Server status
POST /evaluate                    → Evaluate code save
POST /evaluate_pillar             → Evaluate pillar save
POST /verify_intent               → Verify AI explanation
POST /audit_reasoning             → Closed-loop audit ← NEW!
POST /resign_vault                → Re-sign vault after manual fix
```

## Configuration

### VS Code Settings
```json
{
  "trepan.serverUrl": "http://127.0.0.1:8000",
  "trepan.enabled": true,
  "trepan.timeoutMs": 30000,
  "trepan.excludePatterns": [
    "**/node_modules/**",
    "**/.git/**",
    "**/*.md",
    "**/*.json"
  ]
}
```

### Server Configuration
```python
# In server.py
PILLARS = [
    "golden_state.md",
    "done_tasks.md",
    "pending_tasks.md",
    "history_phases.md",
    "system_rules.md",
    "problems_and_resolutions.md",
]

# Drift threshold
DRIFT_THRESHOLD = 0.40  # Scores >= 0.40 trigger REJECT
```

## Performance Metrics

### Typical Response Times
```
Primary Gate:     2-5 seconds
Closed-Loop Audit: 2-4 seconds
Parser:           <1 millisecond
Vault Hash:       <10 milliseconds
```

### Resource Usage
```
Model Memory:     ~8GB RAM (8B parameter model)
Server CPU:       1-2 cores during inference
Extension:        <50MB RAM
```

## Error Handling

### Fail-Open Strategy
```
If server offline → Allow save (log warning)
If timeout → Allow save (log warning)
If parse error → Return WARN verdict (score 1.0)
```

### Failsafe Mechanisms
```
1. Missing [ACTION] tag → WARN verdict
2. High score + ACCEPT → Override to REJECT
3. Vault compromised → Block all pillar saves
4. Model not loaded → Return 503 (retry)
```

## Monitoring & Debugging

### Server Logs
```bash
# View real-time logs
tail -f trepan_server.log

# Search for REJECT verdicts
grep "REJECT" trepan_server.log

# Check parser warnings
grep "Parser failsafe" trepan_server.log
```

### Extension Logs
```
VS Code → Help → Toggle Developer Tools → Console
Filter: "TREPAN"
```

### Audit Trail
```bash
# View all audit entries
cat .trepan/Walkthrough.md

# Count ACCEPT vs REJECT
grep -c "Result: ACCEPT" .trepan/Walkthrough.md
grep -c "Result: REJECT" .trepan/Walkthrough.md

# Show recent entries
tail -n 50 .trepan/Walkthrough.md
```

---

## Summary

The Trepan Closed-Loop Architecture provides:

1. **Automatic Gating**: Every save is evaluated against project rules
2. **Audit Trail**: Every decision is logged with timestamp and reasoning
3. **Drift Detection**: Reasoning is compared against Reference Architecture
4. **Human Review**: Side-by-side view for manual verification
5. **Fail-Safe**: Multiple layers of validation with graceful degradation

This creates a complete feedback loop that catches hallucinations, prevents architectural drift, and maintains a permanent audit trail for compliance and debugging.
