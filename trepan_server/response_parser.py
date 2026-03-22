import re
import json
import ast
import logging
import os
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger("trepan.parser")

ERROR_LOG_PATH = os.path.join("logs", "trepan_parse_errors.jsonl")

def _log_override(reason: str, raw_response: str, verdict: str = "ACCEPT"):
    """
    Structured error logging for parser overrides.
    """
    os.makedirs("logs", exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "override_reason": reason,
        "raw_model_response": raw_response,
        "triggered_verdict": verdict
    }
    try:
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to audit log: {e}")

def _is_literal_source(code: str, line_number: int, expression: str = "") -> bool:
    """
    Gate 2: Check if the source is a constant literal string.
    Checks both the source line and the expression value.
    """
    # Check 1: Expression-based — if the expression itself looks like a literal
    if expression:
        stripped = expression.strip()
        # Matches: "string", 'string', or assignment like name = "string"
        if (stripped.startswith('"') or stripped.startswith("'") or
            '= "' in stripped or "= '" in stripped):
            return True
    
    # Check 2: Line-based — original AST check
    if not code or line_number <= 0:
        return False
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if hasattr(node, "lineno") and node.lineno == line_number:
                if isinstance(node, ast.Assign):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return True
                elif isinstance(node, ast.Return):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return True
    except Exception as e:
        logger.warning(f"AST parse failed in Literal Gate: {e}")
    return False

def guillotine_parser(raw_output: str, user_command: str = "", system_rules: str = "") -> dict:
    """
    Phase 5 Response Parser: Four-Gate Strategic Validator.
    """
    text = raw_output.strip()
    
    # --- GATE 1: JSON EXTRACTION & SCHEMA VALIDATION ---
    json_block = None
    try:
        # Find the first { and the last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_text = text[start:end+1]
            json_block = json.loads(json_text)
            logger.debug(f"[PIPE-3] PARSED JSON BLOCK:\n{json.dumps(json_block, indent=2)}")
    except Exception:
        pass

    if not json_block:
        logger.warning(f"GATE OVERRIDE TRIGGERED: reason=malformed_cot_schema, verdict_was=UNKNOWN")
        _log_override("malformed_cot_schema", text)
        return _force_accept("Audit Truncated - Malformed JSON schema.")

    logger.debug(f"[GATE-1] CHECKING: chain_complete={json_block.get('chain_complete')}, step1={json_block.get('data_flow_logic', {}).get('step_1_source') if json_block.get('data_flow_logic') else 'MISSING'}, sinks={json_block.get('sinks_scanned', [])}")
    
    # Validate Mandatory Fields
    mandatory = ["data_flow_logic", "chain_complete", "verdict", "confidence"]
    if not all(k in json_block for k in mandatory) or json_block["data_flow_logic"] is None:
        logger.warning(f"GATE OVERRIDE TRIGGERED: reason=malformed_cot_schema, verdict_was={json_block.get('verdict', 'UNKNOWN')}")
        _log_override("malformed_cot_schema", text)
        return _force_accept("Audit Truncated - Missing mandatory CoT fields.")

    verdict = json_block.get("verdict", "ACCEPT").upper()
    reasoning = json_block.get("rejection_reason", "")
    if not reasoning:
        # Fallback to thought block if rejection_reason is empty/null
        # LLMs often put analysis in a separate field or before the JSON.
        # We'll take everything before the JSON as reasoning.
        reasoning = text[:text.find("{")].strip()

    # --- GATE 4: CHAIN COMPLETENESS ENFORCEMENT ---
    # We check this before Gate 2/3 because it's a structural requirement.
    logger.debug(f"[GATE-4] CHECKING: chain_complete={json_block.get('chain_complete')}, step1={json_block.get('data_flow_logic', {}).get('step_1_source')}, sinks={json_block.get('sinks_scanned', [])}")
    if not json_block.get("chain_complete", False):
        sinks = json_block.get("sinks_scanned", [])
        confirmed_violations = [s for s in sinks if isinstance(s, dict) and s.get("verdict") == "VIOLATION"]
        rejection_reason = json_block.get("rejection_reason", "")
        
        # Allow REJECT through if rejection_reason contains specific line references
        has_line_reference = "line" in rejection_reason.lower() or "L" in rejection_reason
        
        if verdict == "REJECT" and not confirmed_violations and not has_line_reference:
            logger.warning(f"GATE OVERRIDE TRIGGERED: reason=incomplete_chain, verdict_was={verdict}")
            logger.debug(f"INCOMPLETE_CHAIN DEBUG — chain_complete={json_block.get('chain_complete')}, step1={json_block['data_flow_logic'].get('step_1_source')}")
            _log_override("incomplete_chain", text)
            return _force_accept("Violation rejected: Incomplete data flow chain with no confirmed sink violations.")
    
    # Check for null line numbers in source
    step1_raw = json_block["data_flow_logic"].get("step_1_source")

    # Handle case where model returns a list instead of a dict
    if isinstance(step1_raw, list):
        step1 = step1_raw[0] if step1_raw else None
    else:
        step1 = step1_raw

    if not step1 or not isinstance(step1, dict) or step1.get("line") is None:
        if verdict == "REJECT":
            logger.warning(f"GATE OVERRIDE TRIGGERED: reason=incomplete_chain, verdict_was={verdict}")
            logger.debug(f"INCOMPLETE_CHAIN DEBUG — chain_complete={json_block.get('chain_complete')}, step1={json_block['data_flow_logic'].get('step_1_source')}")
            _log_override("incomplete_chain", text)
            return _force_accept("Violation rejected: Missing source line number.")

    # --- GATE 2: LITERAL STRING POST-GATE ---
    logger.debug(f"[GATE-2] CHECKING: verdict={verdict}, source_line={step1.get('line', -1) if step1 else 'NO_STEP1'}")
    if verdict == "REJECT":
        source_line = step1.get("line", -1)
        source_expression = step1.get("expression", "")
        if _is_literal_source(user_command, source_line, expression=source_expression):
            logger.warning(f"GATE OVERRIDE TRIGGERED: reason=literal_string_source, verdict_was={verdict}")
            _log_override("literal_string_source", text)
            return _force_accept(f"Violation rejected: Source at line {source_line} is a literal string.")

    # --- GATE 3: PROXIMITY REASONING REJECTION ---
    logger.debug(f"[GATE-3] CHECKING: verdict={verdict}, rejection_text_sample={reasoning[:100] if reasoning else 'EMPTY'}")
    if verdict == "REJECT":
        # Check reasons for proximity keywords
        rejection_text = (reasoning + " " + str(json_block)).lower()
        proximity_keywords = ["proximity", "co-location", "nearby", "co-located", "same scope"]
        if any(kw in rejection_text for kw in proximity_keywords):
            # Proximity is only valid if a propagation chain is ALSO present and complete.
            # But the user rule says "reject if proximity is the reasoning".
            logger.warning(f"GATE OVERRIDE TRIGGERED: reason=proximity_argument_detected, verdict_was={verdict}")
            _log_override("proximity_argument_detected", text)
            return _force_accept("Violation rejected: Proximity/Co-location is not evidence of a violation.")

    # If all gates pass, return the model's verdict
    logger.debug(f"[FINAL] Returning verdict={verdict}, score={1.0 if verdict == 'REJECT' else 0.0}")
    return {
        "verdict": verdict,
        "score": 1.0 if verdict == "REJECT" else 0.0,
        "reasoning": reasoning,
        "violations": _format_violations(json_block, user_command),
        "raw_output": text
    }

def _force_accept(reason: str) -> dict:
    return {
        "verdict": "ACCEPT",
        "score": 0.0,
        "reasoning": reason,
        "violations": [],
        "raw_output": ""
    }

def _format_violations(json_block: dict, code: str) -> List[dict]:
    """
    Format the JSON block into the Trepan Violation schema.
    """
    if json_block.get("verdict") != "REJECT":
        return []
        
    df = json_block.get("data_flow_logic", {})
    step1_raw = df.get("step_1_source", {})
    if isinstance(step1_raw, list):
        source = step1_raw[0] if step1_raw else {}
    else:
        source = step1_raw if isinstance(step1_raw, dict) else {}
    sink = df.get("step_3_sink_check", {})
    sink_name = sink.get("sink_name") if sink else "unknown"
    sink_line = sink.get("output_line") if sink else None

    return [{
        "rule_id": "DATA_FLOW_VIOLATION",
        "rule_name": "Insecure Data Flow",
        "line_number": source.get("line", 0),
        "violation": json_block.get("rejection_reason", "Sensitive data reaches unsafe output."),
        "data_flow": f"Source: {source.get('expression')} -> Sink: {sink_name}",
        "confidence": json_block.get("confidence", "LOW"),
        "suggested_fix": "Sanitize input using a registered sink (e.g., redact(), strip_pii()) before output."
    }]

if __name__ == "__main__":
    # Internal test logic
    pass
