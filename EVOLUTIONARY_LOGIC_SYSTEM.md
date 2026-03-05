# Trepan Evolutionary Logic System

## Overview

The Trepan Evolutionary Logic System implements a self-learning feedback loop where the 5 Pillars automatically evolve based on project experience. This eliminates manual copy-paste of rules and patterns.

## The 4 Evolutionary Logic Gates

### GATE 1: Pillar Prioritization Hierarchy

The system enforces a strict priority order:

1. **system_rules.md = THE LAW** (Highest Priority)
   - Violations trigger immediate REJECT
   - Overrides ALL AI suggestions and preferences
   - Example: If system_rules.md says "NO eval()", then eval() is forbidden

2. **golden_state.md = THE VISION** (Design Template)
   - All new code should follow patterns from golden_state.md
   - New patterns are flagged for review
   - Defines the "correct way" to write code

3. **problems_and_resolutions.md = THE MEMORY** (Failure Prevention)
   - Checked before accepting any solution
   - Prevents repeating past mistakes
   - If method X failed before, it's rejected again

### GATE 2: Problem Detection & Routing

Automatic problem classification and routing:

**IF user describes a struggle/error:**
- Record it in `problems_and_resolutions.md`
- Mark as "UNRESOLVED" initially

**IF user pivots or gives up:**
- Generate NEGATIVE RULE: "NEVER use X because it causes Y"
- Add to `system_rules.md` automatically
- Example: "User tried async/await in sync context → Rule: NEVER mix async/await in synchronous Flask routes"

**IF solution works after struggle:**
- Extract SUCCESS PATTERN: "Use X for Y because Z"
- Add to `golden_state.md` automatically
- Mark problem as "RESOLVED" in `problems_and_resolutions.md`

### GATE 3: History-Phase Chain

Automatic history tracking with problem links:

**WHEN task moves from pending → done:**
- Create `history_phases.md` entry with:
  - Date and completion timestamp
  - What was accomplished
  - Problems encountered (if any)
  - Link to `problems_and_resolutions.md`
- Example: "Phase 3: Authentication - Encountered async issue (see Problem #5), resolved with sync approach"

### GATE 4: Contextual Drift Detection

Prevents architectural drift:

1. **Tech Stack Enforcement**: Reject frameworks not in golden_state.md
2. **Context Relevance**: Reject code that doesn't match project context
3. **Historical Consistency**: Reject changes contradicting past decisions
4. **Problem Awareness**: Reject solutions that repeat known failures

## Automatic Pillar Synchronization

### The `/evolve_memory` Endpoint

Automatically processes `problems_and_resolutions.md` and updates all pillars:

```python
POST /evolve_memory
{
  "project_path": "C:/path/to/project"
}
```

**What it does:**
1. Scans `problems_and_resolutions.md` for patterns
2. RESOLVED problems → Success Patterns → `golden_state.md`
3. UNRESOLVED problems → Negative Rules → `system_rules.md`
4. Lessons learned → `history_phases.md`
5. Syncs all changes to vault and re-signs

**No manual intervention needed!**

### The `/move_task` Endpoint

Automatically updates history when tasks complete:

```python
POST /move_task
{
  "task_description": "Implement user authentication",
  "project_path": "C:/path/to/project",
  "problems_encountered": "Had to switch from async to sync approach"
}
```

**What it does:**
1. Moves task from `pending_tasks.md` to `done_tasks.md`
2. Creates `history_phases.md` entry with timestamp
3. Links to problems if any were encountered
4. Syncs to vault and re-signs

## Prompt Builder Integration

The `prompt_builder.py` now includes evolutionary logic instructions:

```python
from trepan_server.prompt_builder import build_prompt

prompt = build_prompt(
    golden_state=golden_state_content,
    system_rules=system_rules_content,
    user_command=user_code,
    readme_content=readme_content,
    history_phases=history_content,
    problems_and_resolutions=problems_content
)
```

The LLM receives:
- Pillar Prioritization Hierarchy
- Problem Detection & Routing instructions
- History-Phase Chain requirements
- Evolutionary Actions format

## Response Format

The LLM now returns evolutionary actions:

```
[THOUGHT]
(Analysis following the 4 gates)

[EVOLUTIONARY_ACTIONS]
- ADD_TO_PROBLEMS: User struggled with async/await in Flask
- ADD_NEGATIVE_RULE: NEVER use async/await in synchronous Flask routes
- ADD_SUCCESS_PATTERN: Use threading for background tasks in Flask
- UPDATE_HISTORY: Completed authentication system with sync approach
- MARK_RESOLVED: Problem #5 resolved with threading solution

[SCORE]
0.15

[ACTION]
ACCEPT
```

## Benefits

1. **Zero Manual Work**: Rules and patterns evolve automatically
2. **Prevents Repeated Failures**: Memory prevents trying failed approaches
3. **Enforces Consistency**: Hierarchy ensures rules are always followed
4. **Tracks Evolution**: History shows how project learned over time
5. **Self-Improving**: System gets smarter with each problem solved

## Example Workflow

1. **User encounters problem**: "Async/await not working in Flask"
2. **System records**: Added to `problems_and_resolutions.md` as UNRESOLVED
3. **User tries solution**: Switches to threading
4. **Solution works**: System extracts pattern
5. **Automatic updates**:
   - `golden_state.md`: "Pattern: Use threading for background tasks in Flask"
   - `system_rules.md`: "NEVER use async/await in synchronous Flask routes"
   - `history_phases.md`: "Phase 2: Resolved async issue with threading"
   - `problems_and_resolutions.md`: Problem marked RESOLVED
6. **Future prevention**: If user tries async/await again, system rejects with reference to past failure

## Testing the System

### Test 1: Problem Recording
```bash
# Add a problem to problems_and_resolutions.md
echo "## Problem 1: Async/await in Flask (UNRESOLVED)" >> .trepan/problems_and_resolutions.md
echo "Tried using async/await but Flask is synchronous" >> .trepan/problems_and_resolutions.md

# Run evolution
curl -X POST http://localhost:8000/evolve_memory \
  -H "Content-Type: application/json" \
  -d '{"project_path": "C:/path/to/project"}'

# Check system_rules.md for new negative rule
```

### Test 2: Task Completion with Problems
```bash
curl -X POST http://localhost:8000/move_task \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Implement background jobs",
    "project_path": "C:/path/to/project",
    "problems_encountered": "Had to switch from async to threading"
  }'

# Check history_phases.md for entry with problem link
```

### Test 3: Success Pattern Extraction
```bash
# Mark problem as resolved in problems_and_resolutions.md
echo "## Problem 1: Async/await in Flask (RESOLVED)" >> .trepan/problems_and_resolutions.md
echo "Solution: Used threading.Thread for background tasks" >> .trepan/problems_and_resolutions.md

# Run evolution
curl -X POST http://localhost:8000/evolve_memory \
  -H "Content-Type: application/json" \
  -d '{"project_path": "C:/path/to/project"}'

# Check golden_state.md for new success pattern
```

## Status: IMPLEMENTED ✅

All 4 evolutionary logic gates are now active:
- ✅ Pillar Prioritization Hierarchy in prompt_builder.py
- ✅ Problem Detection & Routing in evolve_memory endpoint
- ✅ History-Phase Chain in move_task endpoint
- ✅ Contextual Drift Detection in prompt template

The system now learns from experience automatically without manual intervention.
