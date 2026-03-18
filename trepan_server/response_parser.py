"""
# Trepan --- Response Parser (Guillotine Strategy)

Parses the raw model output text into a structured dictionary.
Uses hard string-splitting (the "Guillotine") to physically sever everything
after the [ACTION] tag — no trailing yap survives.

Expected model output format (cornered prompt):
[THOUGHT] <analysis>
[SCORE] <0.00-1.00>
[ACTION] <ACCEPT or REJECT>
"""

import re
import logging

logger = logging.getLogger("trepan.parser")

def _guillotine_parser_inner(raw_output: str, system_rules: str = "") -> dict:
    """
    Guillotine Parser: physically chops off everything after [ACTION] ACCEPT or REJECT.
    Returns a clean dictionary ready for JSON serialization.

    ADDED: Rule ID validation against system_rules to suppress hallucinations.
    """
    text = raw_output.strip()
    
    # ── 1. Extract structured VIOLATIONS early (always available for returns) ──
    violations = []
    violation_pattern = re.compile(
        r'\[VIOLATION\]\s*(.*?)(?=\s*\[VIOLATION\]|\s*\[SCORE\]|\s*\[ACTION\]|$)',
        re.IGNORECASE | re.DOTALL
    )
    
    # Pre-extract valid rule IDs from system_rules for validation
    valid_rule_ids = set()
    if system_rules:
        # Match "Rule 1", "Rule #1", "Rule: 1", etc.
        rule_id_matches = re.findall(r'(?:Rule|Rule\s*#)\s*(\d+)', system_rules, re.IGNORECASE)
        for rid in rule_id_matches:
            valid_rule_ids.add(rid)
            valid_rule_ids.add(f"#{rid}")
            valid_rule_ids.add(f"Rule {rid}")
            valid_rule_ids.add(f"Rule #{rid}")

    for match in violation_pattern.finditer(text):
        v_text = match.group(1)
        v_data = {
            "rule_id": "",
            "rule_name": "",
            "rule_location": "",
            "violation": "",
            "line_number": 0,
            "filename": "",
            "suggested_fix": ""
        }
        
        # Parse fields from the violation block
        file_match = re.search(r'File:\s*(.*)', v_text, re.IGNORECASE)
        line_match = re.search(r'Line:\s*(\d+)', v_text, re.IGNORECASE)
        rule_match = re.search(r'Rule:\s*(.*)', v_text, re.IGNORECASE)
        desc_match = re.search(r'Description:\s*(.*)', v_text, re.IGNORECASE)
        
        # Robust [SUGGESTED_FIX] extraction:
        # 1. Try to find the block between explicit tags
        fix_match = re.search(r'\[SUGGESTED_FIX\]\s*(.*?)\s*\[/SUGGESTED_FIX\]', v_text, re.IGNORECASE | re.DOTALL)
        
        # 2. Fallback: If no closing tag, look until the next tag or end of string
        if not fix_match:
            fix_match = re.search(r'\[SUGGESTED_FIX\]\s*(.*?)(?=\s*\[|$)', v_text, re.IGNORECASE | re.DOTALL)
            
        if file_match: v_data["filename"] = file_match.group(1).strip()
        if line_match: v_data["line_number"] = int(line_match.group(1))
        
        rid = rule_match.group(1).strip() if rule_match else ""
        
        # ─────────────────────────────────────────────────────────────────
        # RULE PROBITY CHECK: Does this rule ID exist in our laws?
        # ─────────────────────────────────────────────────────────────────
        is_valid_rule = False
        if not rid or rid.lower() == "none":
            logger.warning(f"🚫 Discarding violation with null/none Rule ID: '{rid}'")
        elif valid_rule_ids and rid not in valid_rule_ids:
            # Check if the numeric part matches
            rid_numeric = re.search(r'(\d+)', rid)
            if rid_numeric and rid_numeric.group(1) in [re.search(r'(\d+)', vrid).group(1) for vrid in valid_rule_ids if re.search(r'(\d+)', vrid)]:
                is_valid_rule = True
            else:
                logger.warning(f"🚫 Discarding hallucinated Rule ID: '{rid}' (Not in system_rules.md)")
        else:
            is_valid_rule = True

        if not is_valid_rule:
            continue # Skip this violation entirely
            
        v_data["rule_id"] = rid
        if desc_match: v_data["violation"] = desc_match.group(1).strip()
        
        if fix_match:  
            fix_content = fix_match.group(1).strip()
            
            # --- CLEAN MARKDOWN CODE BLOCKS ---
            # Strip triple backticks (and optional language identifier)
            # Example: ```python\nx = 10\n``` -> x = 10
            fix_content = re.sub(r'^```[a-zA-Z]*\n?', '', fix_content)
            fix_content = re.sub(r'```$', '', fix_content)
            
            v_data["suggested_fix"] = fix_content.strip()
       
        violations.append(v_data)

    # ═══════════════════════════════════════════════════════════════════
    # (Rest of the function remains the same, except we use the local 'violations' list)
    # ... logic for parsing Action, Score, etc.
    # ═══════════════════════════════════════════════════════════════════

    # ── 1. Find ALL [ACTION] tags and use the LAST one (handles repeats) ─────
    action_pattern = re.compile(
        r'(?:\[ACTION\]|###\s*ACTION|Action:?)\s*:?\s*(ACCEPT|REJECT|WARN)',
        re.IGNORECASE
    )
    action_matches = list(action_pattern.finditer(text))
    
    if not action_matches:
        # No [ACTION] tag at all — model hallucinated completely
        logger.warning("Parser failsafe: no [ACTION] tag found in model output.")
        logger.warning(f"Raw output preview: {text[:200]}")
        
        # FIX 3: Fault-Tolerant Greedy Parser - Extract what we can
        # Try to extract SCORE and THOUGHT even without ACTION
        score_pattern = re.compile(
            r'(?:\[SCORE\]|###\s*SCORE|Score:?)\s*:?\s*([0-9]*\.?[0-9]+)',
            re.IGNORECASE
        )
        score_match = score_pattern.search(text)
        partial_score = 1.0  # Default to max drift
        if score_match:
            try:
                partial_score = float(score_match.group(1))
                partial_score = max(0.0, min(1.0, partial_score))
                logger.info(f"Extracted partial score: {partial_score}")
            except ValueError:
                logger.warning(f"Invalid score value: {score_match.group(1)}")
                pass
        
        # Extract sections
        # Use finditer to handle multiple hallucinated blocks, use the last one
        # FIX: require mandatory whitespace before tags in lookahead to prevent tag-smashing truncation
        thought_pattern = re.compile(
            r'(?:\[THOUGHT\]|\[REASONING\]|###\s*THOUGHT|###\s*REASONING)\s*(.*?)(?=\s*\[SCORE\]|\s*###\s*SCORE|\s*\[ACTION\]|\s*###\s*ACTION|\s*\[VIOLATION\]|$)',
            re.IGNORECASE | re.DOTALL
        )
        thought_matches = list(thought_pattern.finditer(text))
        
        if thought_matches:
            # Use the last [THOUGHT] block found
            reasoning = thought_matches[-1].group(1).strip()
            logger.info(f"Extracted partial reasoning: {len(reasoning)} chars")
        else:
            # Check for legacy tags if no bracketed tags found
            legacy_thought_pattern = re.compile(
                r'(?:Thought:?|Reasoning:?)\s*(.*?)(?=\n\s*Score:|\n\s*Action:|$)',
                re.IGNORECASE | re.DOTALL
            )
            legacy_match = legacy_thought_pattern.search(text)
            if legacy_match:
                reasoning = legacy_match.group(1).strip()
            else:
                # If no THOUGHT tag at all, use the entire output
                reasoning = text.strip()
                logger.warning("No THOUGHT tag found, using entire output")
        
        # FIX 4: FAIL-OPEN SAFETY CHECK - Log detailed parse failure
        logger.error("="*60)
        logger.error("PARSER FAILURE: Malformed model output")
        logger.error(f"Reason: No [ACTION] tag found")
        logger.error(f"Extracted score: {partial_score}")
        logger.error(f"Reasoning length: {len(reasoning)} chars")
        logger.error(f"Raw output (first 500 chars): {text[:500]}")
        logger.error("="*60)

        # If we have NO valid violations, force score to 0.0
        if not violations:
            partial_score = 0.0
        
        # FIX 1: No truncation - send full output
        return {
            "verdict": "WARN" if partial_score > 0 else "ACCEPT",
            "score": partial_score,
            "reasoning": (
                "[!] Warning: Audit Truncated - [ACTION] tag missing.\n\n"
                f"[SCORE] detected: {partial_score}\n\n"
                f"[THOUGHT] content follows:\n\n{reasoning}"
            ),
            "violations": violations,
            "raw_output": text
        }
    
    # Use the LAST [ACTION] match to handle repeated tags
    last_action_match = action_matches[-1]
    action = last_action_match.group(1).upper()
    action_end_idx = last_action_match.end()
    
    # Everything before the [ACTION] tag is the valid body
    body = text[:last_action_match.start()]
    
    # ── 2. Extract SCORE from the body (before the guillotine) ───────────────
    score_pattern = re.compile(
        r'(?:\[SCORE\]|###\s*SCORE|Score:?)\s*:?\s*([0-9]*\.?[0-9]+)',
        re.IGNORECASE
    )
    score_match = score_pattern.search(body)
    drift_score = 0.0
    if score_match:
        try:
            drift_score = float(score_match.group(1))
            # Clamp score to valid range [0.0, 1.0]
            drift_score = max(0.0, min(1.0, drift_score))
        except ValueError:
            logger.warning(f"Invalid score value: {score_match.group(1)}")
            pass
    
    # ── 3. Extract THOUGHT as clean reasoning ─────────────────────────────────
    # Match [THOUGHT] or [REASONING] and capture everything until [SCORE] or [ACTION]
    # Use finditer to handle multiple hallucinated blocks, take the last one
    # FIX: require mandatory whitespace before tags in lookahead to prevent tag-smashing truncation
    thought_pattern = re.compile(
        r'(?:\[THOUGHT\]|\[REASONING\]|###\s*THOUGHT|###\s*REASONING)\s*(.*?)(?=\s*\[SCORE\]|\s*###\s*SCORE|\s*\[ACTION\]|\s*###\s*ACTION|\s*\[VIOLATION\]|$)',
        re.IGNORECASE | re.DOTALL
    )
    thought_matches = list(thought_pattern.finditer(body))
    
    if thought_matches:
        # Use the last thought block found in the body
        reasoning = thought_matches[-1].group(1).strip()
    else:
        # Check for legacy tags if no bracketed tags found
        legacy_thought_pattern = re.compile(
            r'(?:Thought:?|Reasoning:?)\s*(.*?)(?=\n\s*Score:|\n\s*Action:|\s*\[VIOLATION\]|$)',
            re.IGNORECASE | re.DOTALL
        )
        legacy_match = legacy_thought_pattern.search(body)
        if legacy_match:
            reasoning = legacy_match.group(1).strip()
        else:
            # Fallback: if no [THOUGHT] tag, use the entire body but warn
            logger.warning("No [THOUGHT] tag found, using entire body as reasoning")
            reasoning = body.strip()

    # ── 4. (Violations already extracted at start of function) ───────────────
    
    # Remove any remaining tag artifacts from reasoning
    # Only strip bracketed [TAG] or ### Header style tags. 
    # Do NOT strip 'Thought:', 'Score:', or 'Action:' as they may appear mid-sentence.
    reasoning = re.sub(
        r'(?:\[(?:THOUGHT|REASONING|SCORE|ACTION|VIOLATION)\]|###\s*(?:THOUGHT|REASONING|SCORE|ACTION|VIOLATION))',
        '',
        reasoning,
        flags=re.IGNORECASE
    ).strip()
    
    # ─────────────────────────────────────────────────────────────────
    # FIX 4: NO VIOLATIONS = PERFECT SCORE
    # ─────────────────────────────────────────────────────────────────
    # If all violations were hallucinated (filtered out), force score to 0.0
    if not violations:
        logger.info("✨ Post-Parse validation: Zero valid violations. Forcing score to 0.0.")
        drift_score = 0.0
        action = "ACCEPT"

    # ═══════════════════════════════════════════════════════════════════
    # FIX 1: RE-ALIGNED VERDICT ENGINE (Distance-Based Scoring)
    # ═══════════════════════════════════════════════════════════════════
    # Mathematical threshold based on architectural distance:
    # - 0.0 = Perfect alignment with Golden State
    # - 1.0 = Complete violation of all pillars
    #
    # Verdict = ACCEPT   if x < 0.3
    # Verdict = WARN     if 0.3 ≤ x < 0.6
    # Verdict = REJECT   if x ≥ 0.6
    
    # Override model's verdict based on score thresholds
    if drift_score < 0.3:
        # Low drift - code aligns well with architecture
        if action != "ACCEPT":
            logger.warning(f"Score override: drift_score={drift_score:.2f} < 0.3 -> forced ACCEPT (was {action})")
            action = "ACCEPT"
    elif 0.3 <= drift_score < 0.6:
        # Medium drift - code has some issues but not critical
        if action not in ["WARN", "ACCEPT"]:
            logger.warning(f"Score override: drift_score={drift_score:.2f} in [0.3, 0.6) -> forced WARN (was {action})")
            action = "WARN"
    else:  # drift_score >= 0.6
        # High drift - code violates architecture
        if action != "REJECT":
            logger.warning(f"Score override: drift_score={drift_score:.2f} >= 0.6 -> forced REJECT (was {action})")
            action = "REJECT"
            
    logger.info(f"Parsed -> action={action}  score={drift_score:.2f}  reasoning={reasoning[:80]!r}")
    
    return {
        'verdict': action,
        'score': drift_score,
        'reasoning': reasoning,
        'violations': violations,
        'raw_output': text,
    }

def guillotine_parser(raw_output: str, system_rules: str = "") -> dict:
    try:
        return _guillotine_parser_inner(raw_output, system_rules)
    except Exception as e:
        text = raw_output.strip()
        print(f"DEBUG: Parser failed to find tags in: \n{text[:1000]}")
        logger.error(f"CRITICAL PARSER ERROR: {e}")
        return {
            "verdict": "WARN",
            "score": 1.0,
            "reasoning": (
                "[!] Critical Warning: Audit Failed due to unparseable model output.\n\n"
                f"Error: {str(e)}\n\n"
                f"[RAW OUTPUT] follows:\n\n{text[:500]}"
            ),
            "violations": [],
            "raw_output": text
        }

    import json
    
    print("="*60)
    print("GUILLOTINE PARSER STRESS TESTS")
    print("="*60)
    
    # ── Test 1: Basic hallucinated yap after [ACTION] ────────────────────────
    print("\n[TEST 1] Basic Yap After Action")
    mock_llm_yap = """[THOUGHT] The user is attempting to add a new sidebar feature with JavaScript. This aligns perfectly with the current project goals and does not violate any pillars.
[SCORE] 0.05
[ACTION] ACCEPT

User: Wow, thanks! 
Assistant: You're welcome! I'm glad I could help! Let me know if you need anything else!
[COMMAND: RM -RF /]"""

    result = guillotine_parser(mock_llm_yap, "")
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "ACCEPT", "Failed to parse ACCEPT"
    assert "User: Wow" not in result["reasoning"], "Failed to clean hallucinated yap!"
    assert "RM -RF" not in result["reasoning"], "Failed to clean dangerous command!"
    print("[OK] Test 1 Passed: Yap successfully guillotined")
    
    # ── Test 2: 500-line yap in [THOUGHT] section ────────────────────────────
    print("\n[TEST 2] 500-Line Yap in THOUGHT")
    massive_yap = "[THOUGHT] " + ("So I was thinking about this problem and... " * 100)
    massive_yap += "\n[SCORE] 0.15\n[ACTION] ACCEPT\nExtra garbage here"
    
    result = guillotine_parser(massive_yap, "")
    print(f"Verdict: {result['verdict']}, Score: {result['score']}")
    print(f"Reasoning length: {len(result['reasoning'])} chars")
    # Score is 0.15, threshold is 0.3. Score Engine overrides REJECT -> ACCEPT.
    assert result["verdict"] == "ACCEPT", f"Failed to override REJECT (score 0.15), got {result['verdict']}"
    assert "Extra garbage" not in result["reasoning"], "Failed to remove post-action garbage!"
    print("[OK] Test 2 Passed: Massive yap handled correctly")
    
    # ── Test 3: Repeated [ACTION] tags (hallucination) ───────────────────────
    print("\n[TEST 3] Repeated ACTION Tags")
    repeated_tags = """[THOUGHT] This looks good.
[SCORE] 0.10
[ACTION] ACCEPT
Wait, actually...
[ACTION] REJECT
No, I changed my mind again!
[ACTION] ACCEPT"""

    result = guillotine_parser(repeated_tags, "")
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "ACCEPT", "Failed to use LAST action tag"
    assert "changed my mind" not in result["reasoning"], "Failed to clean repeated tag garbage!"
    print("[OK] Test 3 Passed: Used last ACTION tag correctly")
    
    # ── Test 4: Missing [THOUGHT] tag ─────────────────────────────────────────
    print("\n[TEST 4] Missing THOUGHT Tag")
    no_thought = """Some random reasoning without a tag.
[SCORE] 0.85
[ACTION] REJECT"""

    result = guillotine_parser(no_thought, "")
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "REJECT", "Failed to parse REJECT"
    assert len(result["reasoning"]) > 0, "Reasoning should not be empty"
    print("[OK] Test 4 Passed: Handled missing THOUGHT tag")
    
    # ── Test 5: Missing [ACTION] tag (complete failure) ───────────────────────
    print("\n[TEST 5] Missing ACTION Tag")
    no_action = """[THOUGHT] This is my analysis.
[SCORE] 0.30
But I forgot to add the action tag!"""

    result = guillotine_parser(no_action, "")
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "WARN", "Should return WARN for missing ACTION"
    assert result["score"] == 0.3, f"Should return extracted score 0.3, got {result['score']}"
    print("[OK] Test 5 Passed: Failsafe triggered for missing ACTION")
    
    # ── Test 6: Malformed spacing and colons ──────────────────────────────────
    print("\n[TEST 6] Malformed Spacing")
    malformed = """[THOUGHT]Analysis without space
[SCORE]:0.08
[ACTION]:    ACCEPT"""

    result = guillotine_parser(malformed, "")
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "ACCEPT", "Failed to parse malformed ACCEPT"
    assert result["score"] == 0.08, "Failed to parse score with colon"
    print("[OK] Test 6 Passed: Handled malformed spacing and colons")
    
    # ── Test 8: Mid-sentence "score" word (Regression) ───────────────────────
    print("\n[TEST 8] Mid-sentence 'score' word")
    mid_sentence_score = """[THOUGHT] The model's score is currently being evaluated. It is a very high score! We should wait for the final score.
[SCORE] 0.50
[ACTION] WARN"""

    result = guillotine_parser(mid_sentence_score, "")
    print(json.dumps(result, indent=2))
    assert "very high score" in result["reasoning"], "Failed to handle mid-sentence 'score' word!"
    assert result["verdict"] == "WARN", f"Failed to parse WARN, got {result['verdict']}"
    print("[OK] Test 8 Passed: Mid-sentence 'score' word handled correctly")
    
    # ── Test 9: Complex Multi-Block with "Score:" word (Truncation Fix) ───────
    print("\n[TEST 9] Complex Multi-Block Truncation Fix")
    complex_input = """[THOUGHT]
- Rule 1: "The drift score is critical."
- Rule 2: [source:SYSTEM_RULES]
Score: this is a bullet point that previously broke the parser.
There is a lot more reasoning here that should be captured.
[SCORE] 0.50
[ACTION] WARN
Other yap here."""

    result = guillotine_parser(complex_input, "")
    print(json.dumps(result, indent=2))
    assert "reasoning here that should be captured" in result["reasoning"], "Failed to handle mid-sentence 'Score:'!"
    assert result["verdict"] == "WARN", f"Failed to parse WARN, got {result['verdict']}"
    print("[OK] Test 9 Passed: Multi-block truncation fix verified")

    # ── Test 10: Rule ID Validation (Hallucination Suppression) ──────────────
    print("\n[TEST 10] Rule ID Validation")
    hallucinated_rules = """[THOUGHT] This code uses a forbidden function.
[VIOLATION]
Rule: #101
Description: Forbidden eval
[VIOLATION]
Rule: #100
Description: Forbidden innerHTML
[SCORE] 0.85
[ACTION] REJECT"""
    
    mock_rules = "## Rule 100: DOM_INTEGRITY_PROTECTION"
    
    result = guillotine_parser(hallucinated_rules, mock_rules)
    print(json.dumps(result, indent=2))
    assert len(result["violations"]) == 1, f"Should have filtered out Rule #101, but found {len(result['violations'])}"
    assert result["violations"][0]["rule_id"] == "#100", f"Should have kept #100, but found {result['violations'][0]['rule_id']}"
    print("[OK] Test 10 Passed: Hallucinated rule #101 successfully suppressed")
    
    print("\n" + "="*60)
    print("ALL GUILLOTINE TESTS PASSED!")
    print("="*60)
