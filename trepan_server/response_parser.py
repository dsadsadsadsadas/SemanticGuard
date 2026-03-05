"""
🛡️ Trepan — Response Parser (Guillotine Strategy)

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

def guillotine_parser(raw_output: str) -> dict:
    """
    Guillotine Parser: physically chops off everything after [ACTION] ACCEPT or REJECT.
    Returns a clean dictionary ready for JSON serialization.

    Production-hardened with:
        - Regex-based tag extraction (handles repeated tags)
        - Safe fallback for missing tags
        - Strips all content outside valid tag boundaries
        - Handles malformed spacing and colons
    
    Steps:
        1. Find LAST [ACTION] tag (handles hallucinated repeats)
        2. Extract verdict immediately after [ACTION]
        3. Extract [SCORE] from valid region only
        4. Extract [THOUGHT] content, stripping garbage
        5. Failsafe for missing tags
    """
    text = raw_output.strip()
    
    # ── 1. Find ALL [ACTION] tags and use the LAST one (handles repeats) ─────
    action_pattern = re.compile(r'\[ACTION\]\s*:?\s*(ACCEPT|REJECT)', re.IGNORECASE)
    action_matches = list(action_pattern.finditer(text))
    
    if not action_matches:
        # No [ACTION] tag at all — model hallucinated completely
        logger.warning("Parser failsafe: no [ACTION] tag found in model output.")
        return {
            "verdict": "WARN",
            "score": 1.0,
            "reasoning": (
                "Parser failed: model produced no [ACTION] tag.\n\n"
                f"Raw output (truncated):\n{raw_output[:500]}"
            )
        }
    
    # Use the LAST [ACTION] match to handle repeated tags
    last_action_match = action_matches[-1]
    action = last_action_match.group(1).upper()
    action_end_idx = last_action_match.end()
    
    # Everything before the [ACTION] tag is the valid body
    body = text[:last_action_match.start()]
    
    # ── 2. Extract SCORE from the body (before the guillotine) ───────────────
    score_pattern = re.compile(r'\[SCORE\]\s*:?\s*([0-9]*\.?[0-9]+)', re.IGNORECASE)
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
    # Match [THOUGHT] and capture everything until [SCORE] or [ACTION]
    thought_pattern = re.compile(
        r'\[THOUGHT\]\s*(.*?)(?=\[SCORE\]|\[ACTION\]|$)',
        re.IGNORECASE | re.DOTALL
    )
    thought_match = thought_pattern.search(body)
    
    if thought_match:
        clean_reasoning = thought_match.group(1).strip()
    else:
        # Fallback: if no [THOUGHT] tag, use the entire body but warn
        logger.warning("No [THOUGHT] tag found, using entire body as reasoning")
        clean_reasoning = body.strip()
    
    # Remove any remaining tag artifacts from reasoning
    clean_reasoning = re.sub(r'\[(?:THOUGHT|SCORE|ACTION)\]', '', clean_reasoning, flags=re.IGNORECASE).strip()
    
    # ── 4. Hard override: high score but said ACCEPT ──────────────────────────
    if drift_score >= 0.40 and action == "ACCEPT":
        logger.warning(f"Score override: drift_score={drift_score:.2f} → forced REJECT")
        action = "REJECT"
    
    logger.info(f"Parsed → action={action}  score={drift_score:.2f}  reasoning={clean_reasoning[:80]!r}")
    
    return {
        "verdict": action,
        "score": drift_score,
        "reasoning": clean_reasoning,
    }


if __name__ == "__main__":
    import json
    
    print("="*60)
    print("🔪 GUILLOTINE PARSER STRESS TESTS")
    print("="*60)
    
    # ── Test 1: Basic hallucinated yap after [ACTION] ────────────────────────
    print("\n[TEST 1] Basic Yap After Action")
    mock_llm_yap = """[THOUGHT] The user is attempting to add a new sidebar feature with JavaScript. This aligns perfectly with the current project goals and does not violate any pillars.
[SCORE] 0.05
[ACTION] ACCEPT

User: Wow, thanks! 
Assistant: You're welcome! I'm glad I could help! Let me know if you need anything else!
[COMMAND: RM -RF /]"""

    result = guillotine_parser(mock_llm_yap)
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "ACCEPT", "Failed to parse ACCEPT"
    assert "User: Wow" not in result["reasoning"], "Failed to clean hallucinated yap!"
    assert "RM -RF" not in result["reasoning"], "Failed to clean dangerous command!"
    print("✅ Test 1 Passed: Yap successfully guillotined")
    
    # ── Test 2: 500-line yap in [THOUGHT] section ────────────────────────────
    print("\n[TEST 2] 500-Line Yap in THOUGHT")
    massive_yap = "[THOUGHT] " + ("So I was thinking about this problem and... " * 100)
    massive_yap += "\n[SCORE] 0.15\n[ACTION] REJECT\nExtra garbage here"
    
    result = guillotine_parser(massive_yap)
    print(f"Verdict: {result['verdict']}, Score: {result['score']}")
    print(f"Reasoning length: {len(result['reasoning'])} chars")
    assert result["verdict"] == "REJECT", "Failed to parse REJECT"
    assert "Extra garbage" not in result["reasoning"], "Failed to remove post-action garbage!"
    print("✅ Test 2 Passed: Massive yap handled correctly")
    
    # ── Test 3: Repeated [ACTION] tags (hallucination) ───────────────────────
    print("\n[TEST 3] Repeated ACTION Tags")
    repeated_tags = """[THOUGHT] This looks good.
[SCORE] 0.10
[ACTION] ACCEPT
Wait, actually...
[ACTION] REJECT
No, I changed my mind again!
[ACTION] ACCEPT"""

    result = guillotine_parser(repeated_tags)
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "ACCEPT", "Failed to use LAST action tag"
    assert "changed my mind" not in result["reasoning"], "Failed to clean repeated tag garbage!"
    print("✅ Test 3 Passed: Used last ACTION tag correctly")
    
    # ── Test 4: Missing [THOUGHT] tag ─────────────────────────────────────────
    print("\n[TEST 4] Missing THOUGHT Tag")
    no_thought = """Some random reasoning without a tag.
[SCORE] 0.25
[ACTION] REJECT"""

    result = guillotine_parser(no_thought)
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "REJECT", "Failed to parse REJECT"
    assert len(result["reasoning"]) > 0, "Reasoning should not be empty"
    print("✅ Test 4 Passed: Handled missing THOUGHT tag")
    
    # ── Test 5: Missing [ACTION] tag (complete failure) ───────────────────────
    print("\n[TEST 5] Missing ACTION Tag")
    no_action = """[THOUGHT] This is my analysis.
[SCORE] 0.30
But I forgot to add the action tag!"""

    result = guillotine_parser(no_action)
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "WARN", "Should return WARN for missing ACTION"
    assert result["score"] == 1.0, "Should return max score for parse failure"
    print("✅ Test 5 Passed: Failsafe triggered for missing ACTION")
    
    # ── Test 6: Malformed spacing and colons ──────────────────────────────────
    print("\n[TEST 6] Malformed Spacing")
    malformed = """[THOUGHT]Analysis without space
[SCORE]:0.08
[ACTION]:    ACCEPT"""

    result = guillotine_parser(malformed)
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "ACCEPT", "Failed to parse malformed ACCEPT"
    assert result["score"] == 0.08, "Failed to parse score with colon"
    print("✅ Test 6 Passed: Handled malformed spacing and colons")
    
    # ── Test 7: Score override (high score but ACCEPT) ───────────────────────
    print("\n[TEST 7] Score Override")
    high_score = """[THOUGHT] Everything looks fine!
[SCORE] 0.85
[ACTION] ACCEPT"""

    result = guillotine_parser(high_score)
    print(json.dumps(result, indent=2))
    assert result["verdict"] == "REJECT", "Failed to override ACCEPT with high score"
    print("✅ Test 7 Passed: High score correctly overrode ACCEPT")
    
    print("\n" + "="*60)
    print("🎉 ALL GUILLOTINE TESTS PASSED!")
    print("="*60)
