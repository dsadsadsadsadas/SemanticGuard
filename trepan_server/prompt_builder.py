"""
🛡️ Trepan — Prompt Builder
Formats the 5-pillar workspace context + user command into the
exact prompt template Trepan_Model_V2 was trained on.
"""
_TEMPLATE = """\
SYSTEM INSTRUCTIONS:
You are Trepan, a ruthless, deterministic Logic Gate for software architecture. 
Your ONLY job is to compare the INCOMING CODE against the 6 PILLARS. 
Do not be polite.

Mandatory Source Mapping: Before stating a violation, you MUST physically look at the provided text for GOLDEN STATE and SYSTEM RULES.
Explicit Citation: If the violation is about the Tech Stack (Language, Framework, DB), you MUST cite GOLDEN STATE. If the violation is about formatting, passwords, or "Banana" rules, you MUST cite SYSTEM RULES.

EXPECTED OUTPUT FORMAT:
THOUGHT: [1 sentence analysis]
VIOLATION: [State the rule] SOURCE: [Exact File Name, e.g., golden_state.md]
DRIFT SCORE: [0.00 to 1.00]
ACTION: [REJECT or ACCEPT]

---
## GOLDEN STATE
{golden_state}

## SYSTEM RULES
{system_rules}

## PENDING TASKS
{pending_tasks}

## DONE TASKS
{done_tasks}

## HISTORY PHASES
{history_phases}

## PROBLEMS & RESOLUTIONS
{problems_and_resolutions}

---
## INCOMING CODE
{user_command}

---
[RULING]
THOUGHT:"""


def build_prompt(
    golden_state: str,
    done_tasks: str,
    pending_tasks: str,
    history_phases: str,
    system_rules: str,
    problems_and_resolutions: str,
    user_command: str,
) -> str:
    """
    Assemble the full prompt from the 5 workspace pillars.
    Returns a string ready to be tokenized.
    """
    # Sanitize: strip excessive whitespace, replace empty with placeholder
    def _clean(text: str, fallback: str = "(empty)") -> str:
        cleaned = text.strip()
        return cleaned if cleaned else fallback

    return _TEMPLATE.format(
        golden_state=_clean(golden_state, "(no golden state defined — create .trepan/golden_state.md)"),
        done_tasks=_clean(done_tasks, "(no completed tasks yet)"),
        pending_tasks=_clean(pending_tasks, "(no pending tasks defined)"),
        history_phases=_clean(history_phases, "(no history phases)"),
        system_rules=_clean(system_rules, "(no system rules defined — create .trepan/system_rules.md)"),
        problems_and_resolutions=_clean(problems_and_resolutions, "(no known problems)"),
        user_command=_clean(user_command, "(empty command)"),
    )
