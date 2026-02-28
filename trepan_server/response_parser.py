"""
🛡️ Trepan — Response Parser (Guillotine Strategy)

Parses the raw model output text into a structured AnalysisResult.
Uses hard string-splitting (the "Guillotine") to physically sever everything
after the [ACTION] tag — no trailing yap survives.

Expected model output format (cornered prompt):
[THOUGHT] <analysis>
[SCORE] <0.00-1.00>
[ACTION] <ACCEPT or REJECT>
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger("trepan.parser")


@dataclass
class AnalysisResult:
    action: str          # "ACCEPT", "REJECT", or "ERROR"
    drift_score: float   # 0.0 – 1.0
    raw_output: str      # Clean reasoning text for the sidebar display


def parse_response(raw_output: str) -> AnalysisResult:
    """
    Guillotine Parser: physically chops off everything after [ACTION].

    Steps:
        1. Find [ACTION] tag index — sever anything below it
        2. Capture 'ACCEPT' or 'REJECT' immediately following [ACTION]
        3. Extract [SCORE] float from the text above the guillotine
        4. Extract [THOUGHT] text as the clean reasoning
        5. If no [ACTION] tag → ERROR failsafe
    """
    text = raw_output.strip()
    upper = text.upper()

    # ── 1. The Guillotine: find and cut at [ACTION] ───────────────────────────
    action_tag_idx = upper.find("[ACTION]")

    if action_tag_idx == -1:
        # No [ACTION] tag at all — model hallucinated
        logger.warning("Parser failsafe: no [ACTION] tag found in model output.")
        return AnalysisResult(
            action="ERROR",
            drift_score=1.0,
            raw_output=(
                "Parser failed: model produced no [ACTION] tag.\n\n"
                f"Raw output:\n{raw_output}"
            ),
        )

    # Everything before [ACTION] is the body we care about
    body = text[:action_tag_idx]
    # The verdict is whatever immediately follows [ACTION]
    after_action = text[action_tag_idx + len("[ACTION]"):].strip()

    # ── 2. Extract ACCEPT / REJECT from the first word after [ACTION] ─────────
    verdict_match = re.match(r":?\s*(ACCEPT|REJECT)", after_action, re.IGNORECASE)
    if verdict_match:
        action = verdict_match.group(1).upper()
    else:
        # Fallback: scan the whole body for bare ACCEPT/REJECT
        if "REJECT" in upper[:action_tag_idx]:
            action = "REJECT"
        elif "ACCEPT" in upper[:action_tag_idx]:
            action = "ACCEPT"
        else:
            logger.warning("Parser failsafe: [ACTION] tag exists but verdict unclear.")
            return AnalysisResult(
                action="ERROR",
                drift_score=1.0,
                raw_output=(
                    "Parser failed: [ACTION] tag found but no ACCEPT/REJECT verdict.\n\n"
                    f"Raw output:\n{raw_output}"
                ),
            )

    # ── 3. Extract SCORE from the body (before the guillotine) ───────────────
    score_match = re.search(r'\[SCORE\]\s*:?\s*([0-9]*\.?[0-9]+)', body, re.IGNORECASE)
    drift_score = 0.0
    if score_match:
        try:
            drift_score = float(score_match.group(1))
        except ValueError:
            pass

    # ── 4. Extract THOUGHT as clean reasoning ─────────────────────────────────
    thought_match = re.search(
        r'\[THOUGHT\]\s*(.*?)(?=\[SCORE\]|\[ACTION\]|$)',
        body, re.IGNORECASE | re.DOTALL
    )
    clean_reasoning = thought_match.group(1).strip() if thought_match else body.strip()

    # ── 5. Hard override: high score but said ACCEPT ──────────────────────────
    if drift_score >= 0.40 and action == "ACCEPT":
        logger.warning(f"Score override: drift_score={drift_score:.2f} → forced REJECT")
        action = "REJECT"

    logger.info(f"Parsed → action={action}  score={drift_score:.2f}  reasoning={clean_reasoning[:80]!r}")

    return AnalysisResult(
        action=action,
        drift_score=drift_score,
        raw_output=clean_reasoning,  # Only the clean THOUGHT — guillotine discards the rest
    )
