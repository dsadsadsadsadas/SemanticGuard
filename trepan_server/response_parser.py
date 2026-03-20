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

def _is_literal_source(code: str, line_number: int) -> bool:
    """
    Gate 2: Use AST to check if the source line is a constant literal string.
    """
    if not code or line_number <= 0:
        return False
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if hasattr(node, "lineno") and node.lineno == line_number:
                # Check for v = "literal" or return "literal"
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
    except Exception:
        pass

    if not json_block:
        _log_override("malformed_cot_schema", text)
        return _force_accept("Audit Truncated - Malformed JSON schema.")

    # Validate Mandatory Fields
    mandatory = ["data_flow_logic", "chain_complete", "verdict", "confidence"]
    if not all(k in json_block for k in mandatory) or json_block["data_flow_logic"] is None:
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
    if not json_block.get("chain_complete", False):
        if verdict == "REJECT":
            _log_override("incomplete_chain", text)
            return _force_accept("Violation rejected: Incomplete data flow chain.")
    
    # Check for null line numbers in source
    step1 = json_block["data_flow_logic"].get("step_1_source")
    if not step1 or step1.get("line") is None:
        if verdict == "REJECT":
            _log_override("incomplete_chain", text)
            return _force_accept("Violation rejected: Missing source line number.")

    # --- GATE 2: LITERAL STRING POST-GATE ---
    if verdict == "REJECT":
        source_line = step1.get("line", -1)
        if _is_literal_source(user_command, source_line):
            _log_override("literal_string_source", text)
            return _force_accept(f"Violation rejected: Source at line {source_line} is a literal string.")

    # --- GATE 3: PROXIMITY REASONING REJECTION ---
    if verdict == "REJECT":
        # Check reasons for proximity keywords
        rejection_text = (reasoning + " " + str(json_block)).lower()
        proximity_keywords = ["proximity", "co-location", "nearby", "co-located", "same scope"]
        if any(kw in rejection_text for kw in proximity_keywords):
            # Proximity is only valid if a propagation chain is ALSO present and complete.
            # But the user rule says "reject if proximity is the reasoning".
            _log_override("proximity_argument_detected", text)
            return _force_accept("Violation rejected: Proximity/Co-location is not evidence of a violation.")

    # If all gates pass, return the model's verdict
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
    source = df.get("step_1_source", {})
    sink = df.get("step_3_sink_check", {})
    
    return [{
        "rule_id": "DATA_FLOW_VIOLATION",
        "rule_name": "Insecure Data Flow",
        "line_number": source.get("line", 0),
        "violation": json_block.get("rejection_reason", "Sensitive data reaches unsafe output."),
        "data_flow": f"Source: {source.get('expression')} -> Sink: {sink.get('sink_name')}",
        "confidence": json_block.get("confidence", "LOW"),
        "suggested_fix": "Sanitize input using a registered sink (e.g., redact(), strip_pii()) before output."
    }]

if __name__ == "__main__":
    # Internal test logic
    pass
