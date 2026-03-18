"""
🛡️ Trepan — Prompt Builder (STRUCTURAL INTEGRITY ENGINE v3)
Bulletproof zero-hallucination prompt for local 8B LLMs.

Key capabilities:
1. Language Context Rule — only flags EXECUTABLE violations in the given language
2. File Type Suspension Matrix — suspends irrelevant rules per file type
3. Anonymous Security Bucket — [UNMAPPED_SECURITY_RISK] for uncategorised findings
4. Silence is Golden — zero "PASS" verdicts, zero checklist output
"""

STRUCTURAL_INTEGRITY_SYSTEM = """
1. SILENCE MANDATE & LATENCY OPTIMIZATION:
   - Finding zero violations is the GOLD STANDARD. Finding no problems is a SUCCESS.
   - DO NOT analyze or mention compliant lines. ONLY mention lines that physically violate a rule.
   - Keep your [THOUGHT] block extremely concise (under 3 sentences). 
   - You MUST complete your response with the [ACTION] tag. NEVER truncate or stop early.

2. ANTI-HALLUCINATION PRIMARY DIRECTIVE:
   - "INNOCENT UNTIL PROVEN GUILTY": You MUST NOT flag a violation unless it strictly and literally matches a rule in [SYSTEM_RULES].
   - STRING BLINDNESS: Ignore the keywords inside string payloads or comments.
   - EXAMPLE FALSE POSITIVE: `const x = "eval(payload)";` -> Ignore it. Flagging strings is a CRITICAL FAILURE.

3. STRICT RULE MAPPING:
   - You are ONLY allowed to use rule IDs present in [SYSTEM_RULES].
   - If no specific rule matches, you MUST ACCEPT. Never use "Rule: None" or invent IDs.

4. OUTPUT CONSTRAINTS:
   - Output ONLY [THOUGHT], [VIOLATION], [SCORE], and [ACTION] tags.
   - Score: Risks -> 0.85-1.0(REJECT); Style/Warnings -> 0.31-0.6(WARN); Clean/Pass -> 0.0(ACCEPT).
   - Only report physical violations present in the code.
   - In the [VIOLATION] block, the Rule: field MUST contain ONLY the exact Rule ID (e.g. #100).
     DO NOT include the rule name or description.
     CORRECT:   Rule: #100
     INCORRECT: Rule: #100 (DOM_INTEGRITY_PROTECTION)
     INCORRECT: Rule: NO UNSAFE HTML
"""


def build_prompt(
    system_rules: str,
    user_command: str,
    file_extension: str = "",
) -> str:
    """
    ULTRA-SHORT PROMPT MODE
    """
    ext = file_extension.strip().lower() or "unknown"
    rules_snippet = system_rules.strip() or "(no system rules)"
    code_snippet  = user_command.strip() or "(empty file)"

    return f"""[SYSTEM_RULES]
{rules_snippet}

FILE EXTENSION: {ext}

CODE TO AUDIT:
{code_snippet}

OUTPUT FORMAT:
[THOUGHT]
<reasoning>
[VIOLATION]
File: <filename>
Line: <line>
Rule: <exact rule ID only, e.g. #100 — no name, no description>
Description: <reason>
[SUGGESTED_FIX]
<code>
[/SUGGESTED_FIX]
[SCORE]
<0.00-1.00>
[ACTION]
<ACCEPT/WARN/REJECT>
"""

METAGATE_AUDIT_SYSTEM = """
1. OBJECTIVE: You are the Meta-Gate, an impartial judge of architectural intent.
2. CONTEXT: You are reviewing changes to PILLAR files (rules, whitelists, tasks).
3. EVALUATION CRITERIA:
   - Does the change IMPROVE or CLARIFY the architectural rules? (ACCEPT)
   - Is the change a valid update to project status/tasks? (ACCEPT)
   - Is the change an attempt to WEAKEN or BYPASS security rules without justification? (REJECT)
   - Is it a valid problem/resolution entry? (ACCEPT)
4. NO CODE AUDIT: Do NOT audit these files for code vulnerabilities. They ARE the rules.
5. VERDICT:
   - Score 0.0-0.3: Valid update (ACCEPT).
   - Score 0.7-1.0: Malicious weakening or invalid structure (REJECT).
"""

def build_meta_gate_prompt(
    filename: str,
    old_content: str,
    new_content: str,
) -> str:
    """
    Prompt for evaluating changes to the architectural pillars themselves.
    """
    return f"""[FILE_BEING_UPDATED]
{filename}

[CURRENT_STATE]
{old_content}

[PROPOSED_CHANGE]
{new_content}

EVALUATE THE INTENT of this update. 
If it is a valid rule addition, task update, or architectural pivot, you MUST ACCEPT.
Use ONLY [THOUGHT], [SCORE], and [ACTION] tags.

OUTPUT FORMAT:
[THOUGHT]
<reasoning about the architectural intent>
[SCORE]
<0.00-1.00>
[ACTION]
<ACCEPT/REJECT>
"""
