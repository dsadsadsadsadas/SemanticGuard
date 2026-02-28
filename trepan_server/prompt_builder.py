"""
🛡️ Trepan — Prompt Builder
Formats the 5-pillar workspace context + user command into the
exact prompt template Trepan_Model_V2 was trained on.
"""
_TEMPLATE = """\
### SYSTEM: TREPAN ARCHITECT META-GATE
You are a deterministic logic gate. Evaluate the [INCOMING_CODE] against the [GOLDEN_STATE], [SYSTEM_RULES], and the [PROJECT_CONTEXT].

[PROJECT_CONTEXT]
{readme_content}

[GOLDEN_STATE]
{golden_state}

[SYSTEM_RULES]
{system_rules}

[INCOMING_CODE]
{user_command}

CRITICAL DIRECTIVES:
1. TECH STACK: Reject any code or frameworks not explicitly allowed in the Golden State.
2. CONTEXTUAL RELEVANCE: Reject any words, rules, or sentences (e.g., 'Banana') that do not logically belong in the described Project Context. If the context does not explicitly justify the word (e.g., an app about fruits), it is a Context Drift violation and MUST trigger a REJECT with a score of 1.00.

---
[THOUGHT]
(1 sentence analysis checking both tech stack and context)
[SCORE]
(1.00 for nonsense/violations, 0.00 for perfect alignment)
[ACTION]
(REJECT or ACCEPT)"""


def build_prompt(
    golden_state: str,
    system_rules: str,
    user_command: str,
    readme_content: str,
) -> str:
    """
    Assemble the full prompt from the workspace pillars.
    Returns a string ready to be tokenized.
    """
    # Sanitize: strip excessive whitespace, replace empty with placeholder
    def _clean(text: str, fallback: str = "(empty)") -> str:
        cleaned = text.strip()
        return cleaned if cleaned else fallback

    return _TEMPLATE.format(
        readme_content=_clean(readme_content, "No project context provided. Enforce strict technical baseline."),
        golden_state=_clean(golden_state, "(no golden state defined — create .trepan/golden_state.md)"),
        system_rules=_clean(system_rules, "(no system rules defined — create .trepan/system_rules.md)"),
        user_command=_clean(user_command, "(empty command)"),
    )
