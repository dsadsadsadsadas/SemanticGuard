# 5 Pillars Evolution Loop - System Diagram

## The Complete Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TREPAN 5 PILLARS SYSTEM                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         USER-ACCESSIBLE FILES                        │
│                          (.trepan/ folder)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. golden_state.md          ← Successful patterns (GROWS)         │
│  2. system_rules.md          ← Negative rules (GROWS)              │
│  3. history_phases.md        ← Project timeline                    │
│  4. problems_and_resolutions.md ← Input for evolution              │
│  5. pending_tasks.md         ← TODO list                           │
│  6. done_tasks.md            ← Completed work (GROWS)              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Cryptographic Snapshot
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FROZEN VAULT SNAPSHOTS                         │
│                   (.trepan/trepan_vault/ folder)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  golden_state.md (frozen)                                          │
│  system_rules.md (frozen)                                          │
│  history_phases.md (frozen)                                        │
│  problems_and_resolutions.md (frozen)                              │
│  pending_tasks.md (frozen)                                         │
│  done_tasks.md (frozen)                                            │
│                                                                     │
│  SHA-256 Signature → .trepan.lock                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘


## Memory-to-Law Pipeline (The Evolution Loop)

```
┌──────────────────────────────────────────────────────────────────────┐
│                    STEP 1: PROBLEM OCCURS                            │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Developer logs problem
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│              problems_and_resolutions.md                             │
│                                                                      │
│  ## Problem 1: SQL Injection (RESOLVED)                             │
│  Root Cause: String concatenation in queries                        │
│  Resolution: Used parameterized statements                          │
│                                                                      │
│  ## Problem 2: Memory Leak (UNRESOLVED)                             │
│  Root Cause: Circular references in event listeners                 │
│  Resolution: Still investigating                                    │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ POST /evolve_memory
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    STEP 2: LLM ANALYSIS                              │
│                                                                      │
│  Llama 3.1 analyzes problems and extracts:                          │
│  • Successful patterns from RESOLVED problems                       │
│  • Failure causes from UNRESOLVED problems                          │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│   RESOLVED PROBLEMS             │   │   UNRESOLVED PROBLEMS           │
│                                 │   │                                 │
│   Extract successful patterns   │   │   Extract failure causes        │
│                                 │   │                                 │
│   "Always use parameterized     │   │   "NEVER use strong references  │
│    statements for SQL"          │   │    in event listeners"          │
└─────────────────────────────────┘   └─────────────────────────────────┘
                    │                               │
                    │                               │
                    ▼                               ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│   STEP 3: UPDATE GOLDEN STATE   │   │   STEP 4: UPDATE SYSTEM RULES   │
│                                 │   │                                 │
│   golden_state.md               │   │   system_rules.md               │
│                                 │   │                                 │
│   ## Evolved Patterns           │   │   ## Evolved Rules              │
│   - Use parameterized SQL       │   │   - NEVER use string concat     │
│   - Thread-local storage for    │   │     for SQL queries             │
│     sessions                    │   │   - NEVER use strong refs in    │
│                                 │   │     event listeners             │
└─────────────────────────────────┘   └─────────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│              STEP 5: UPDATE VAULT & RE-SIGN LOCK                     │
│                                                                      │
│  1. Copy updated files to .trepan/trepan_vault/                     │
│  2. Calculate new SHA-256 hash of entire vault                      │
│  3. Write new signature to .trepan.lock                             │
│  4. Cryptographic integrity maintained                              │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│              STEP 6: FUTURE CODE EVALUATIONS                         │
│                                                                      │
│  All future /evaluate calls now include:                            │
│  • New patterns in golden_state.md                                  │
│  • New negative rules in system_rules.md                            │
│  • Historical context from history_phases.md                        │
│  • Past problems from problems_and_resolutions.md                   │
│                                                                      │
│  → AI rejects code that repeats past mistakes                       │
│  → AI enforces lessons learned from experience                      │
└──────────────────────────────────────────────────────────────────────┘
```

## Task Management Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                    pending_tasks.md                                  │
│                                                                      │
│  - Implement user authentication                                    │
│  - Add rate limiting                                                │
│  - Write integration tests                                          │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ POST /move_task
                                    │ (task completed)
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    done_tasks.md                                     │
│                                                                      │
│  ## 2024-01-15 14:30:00                                             │
│  - Implement user authentication                                    │
│                                                                      │
│  ## 2024-01-16 09:15:00                                             │
│  - Add rate limiting                                                │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Update vault & re-sign
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│              Vault Updated + .trepan.lock Re-signed                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Enhanced Prompt Builder (All 5 Pillars)

```
┌──────────────────────────────────────────────────────────────────────┐
│                    BEFORE (Task 5 and earlier)                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [PROJECT_CONTEXT]  ← README.md                                     │
│  [GOLDEN_STATE]     ← golden_state.md                               │
│  [SYSTEM_RULES]     ← system_rules.md                               │
│  [INCOMING_CODE]    ← User's code                                   │
│                                                                      │
│  → Limited context, no historical awareness                         │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                    AFTER (Task 6 - Complete)                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [PROJECT_CONTEXT]           ← README.md                            │
│  [GOLDEN_STATE]              ← golden_state.md (with evolved patterns)│
│  [SYSTEM_RULES]              ← system_rules.md (with evolved rules) │
│  [HISTORY_PHASES]            ← history_phases.md (NEW!)             │
│  [PROBLEMS_AND_RESOLUTIONS]  ← problems_and_resolutions.md (NEW!)  │
│  [INCOMING_CODE]             ← User's code                          │
│                                                                      │
│  → Full context with historical awareness                           │
│  → AI can reference past phases and problems                        │
│  → AI can detect repeated failure patterns                          │
└──────────────────────────────────────────────────────────────────────┘
```

## API Endpoints Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TREPAN API                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  GET  /health                  → Server status                     │
│  GET  /templates               → Available golden templates        │
│                                                                     │
│  POST /evaluate                → Evaluate code (5 pillars)         │
│  POST /evaluate_pillar         → Evaluate pillar changes           │
│  POST /verify_intent           → Verify AI explanation             │
│  POST /audit_reasoning         → Closed-loop audit                 │
│                                                                     │
│  POST /initialize_project      → Initialize with template          │
│  POST /resign_vault            → Re-sign vault after tampering     │
│                                                                     │
│  POST /move_task               → Move task to done (NEW!)          │
│  POST /evolve_memory           → Trigger memory evolution (NEW!)   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## The Complete Trepan Lifecycle

```
1. INITIALIZATION
   └─> User runs: Trepan: Initialize Project
       └─> Chooses template (solo-indie, clean-layers, secure-stateless)
           └─> .trepan/ folder created with all 5 pillars
               └─> Vault initialized and cryptographically signed

2. DEVELOPMENT
   └─> User writes code
       └─> On save: POST /evaluate
           └─> Code evaluated against all 5 pillars
               └─> ACCEPT: Code saved
               └─> REJECT: Save blocked, reason shown

3. TASK MANAGEMENT
   └─> User completes task
       └─> POST /move_task
           └─> Task moved from pending to done
               └─> Vault updated and re-signed

4. PROBLEM RESOLUTION
   └─> User encounters problem
       └─> Logs in problems_and_resolutions.md
           └─> Resolves problem
               └─> Marks as RESOLVED
                   └─> POST /evolve_memory
                       └─> Pattern extracted and added to golden_state.md
                           └─> Negative rule added to system_rules.md
                               └─> Vault updated and re-signed

5. CONTINUOUS PROTECTION
   └─> All future code evaluations now include:
       • Evolved patterns from past successes
       • Negative rules from past failures
       • Historical context from project phases
       • Awareness of past problems
       └─> Trepan prevents repeating past mistakes
```

## Key Benefits

1. **Self-Improving System**: Trepan learns from experience
2. **Institutional Memory**: Past mistakes are never forgotten
3. **Automatic Rule Evolution**: No manual rule updates needed
4. **Cryptographic Integrity**: All changes are signed and auditable
5. **Closed-Loop Audit**: Every decision is logged and verifiable
6. **Historical Awareness**: AI understands project evolution
7. **Pattern Recognition**: Successful approaches are codified
8. **Failure Prevention**: Known failure patterns are blocked

## Status: PRODUCTION READY ✅

The 5 Pillars Evolution Loop is complete and fully integrated with the existing Trepan system.
