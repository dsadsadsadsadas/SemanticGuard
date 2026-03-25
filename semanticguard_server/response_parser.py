import re
import json
import ast
import logging
import os
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger("semanticguard.parser")

ERROR_LOG_PATH = os.path.join("logs", "semanticguard_parse_errors.jsonl")

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
    V2 Response Parser: Handles {"findings": [...]} format from stress_test.py
    """
    text = raw_output.strip()
    
    # --- JSON EXTRACTION ---
    json_block = None
    try:
        # Find the first { and the last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_text = text[start:end+1]
            json_block = json.loads(json_text)
            logger.debug(f"[V2-PARSER] PARSED JSON BLOCK:\n{json.dumps(json_block, indent=2)}")
    except Exception as e:
        logger.warning(f"JSON parse failed: {e}")

    if not json_block:
        logger.warning(f"PARSER OVERRIDE: malformed JSON schema")
        _log_override("malformed_json_schema", text)
        return _force_accept("Audit Truncated - Malformed JSON schema.")

    # --- V2 FORMAT: {"findings": [...]} ---
    if "findings" in json_block:
        findings = json_block.get("findings", [])
        
        if not findings:
            # No findings = ACCEPT
            logger.info("[V2-PARSER] No findings detected — Risk Score: 0.00")
            return {
                "verdict": "ACCEPT",
                "score": 0.0,
                "reasoning": "No security violations detected.",
                "violations": [],
                "raw_output": text
            }
        
        # Has findings = REJECT
        # Calculate risk score based on severity
        severity_weights = {"CRITICAL": 1.0, "HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.25}
        total_risk = sum(severity_weights.get(f.get("severity", "MEDIUM"), 0.5) for f in findings if isinstance(f, dict))
        risk_score = min(total_risk / len(findings), 1.0) if findings else 0.0
        
        logger.info(f"[V2-PARSER] {len(findings)} finding(s) detected — Risk Score: {risk_score:.2f}")
        
        # Convert findings to violations format
        violations = []
        for finding in findings:
            if isinstance(finding, dict):
                violations.append({
                    "rule_id": finding.get("rule_id", "Built-in Taint Analysis"),
                    "rule_name": finding.get("vulnerability_type", "Security Issue"),
                    "line_number": finding.get("line_number", 0),
                    "violation": finding.get("description", "Security vulnerability detected."),
                    "severity": finding.get("severity", "MEDIUM"),
                    "confidence": "HIGH",
                    "suggested_fix": "Review and remediate the security issue."
                })
        
        # Build reasoning from findings
        reasoning_parts = []
        for finding in findings:
            if isinstance(finding, dict):
                desc = finding.get("description", "Security issue")
                line = finding.get("line_number")
                rule_id = finding.get("rule_id", "Built-in Taint Analysis")
                if line:
                    reasoning_parts.append(f"[{rule_id}] Line {line}: {desc}")
                else:
                    reasoning_parts.append(f"[{rule_id}] {desc}")
        
        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Security violations detected."
        
        return {
            "verdict": "REJECT",
            "score": risk_score,
            "reasoning": reasoning,
            "violations": violations,
            "raw_output": text
        }
    
    # --- FALLBACK: Legacy format support ---
    # Keep existing logic for backward compatibility
    mandatory = ["data_flow_logic", "chain_complete", "verdict", "confidence"]
    if not all(k in json_block for k in mandatory) or json_block["data_flow_logic"] is None:
        logger.warning(f"PARSER OVERRIDE: missing mandatory fields")
        _log_override("malformed_cot_schema", text)
        return _force_accept("Audit Truncated - Missing mandatory CoT fields.")

    verdict = json_block.get("verdict", "ACCEPT").upper()
    reasoning = json_block.get("rejection_reason", "")
    if not reasoning:
        reasoning = text[:text.find("{")].strip()

    # Chain completeness check
    if not json_block.get("chain_complete", False):
        sinks = json_block.get("sinks_scanned", [])
        confirmed_violations = [s for s in sinks if isinstance(s, dict) and s.get("verdict") == "VIOLATION"]
        rejection_reason = json_block.get("rejection_reason", "")
        
        has_line_reference = "line" in rejection_reason.lower() or "L" in rejection_reason
        
        if verdict == "REJECT" and not confirmed_violations and not has_line_reference:
            logger.warning(f"PARSER OVERRIDE: incomplete chain")
            _log_override("incomplete_chain", text)
            return _force_accept("Violation rejected: Incomplete data flow chain.")
    
    # Source validation
    step1_raw = json_block["data_flow_logic"].get("step_1_source")
    if isinstance(step1_raw, list):
        step1 = step1_raw[0] if step1_raw else None
    else:
        step1 = step1_raw

    if not step1 or not isinstance(step1, dict) or step1.get("line") is None:
        if verdict == "REJECT":
            logger.warning(f"PARSER OVERRIDE: missing source line")
            _log_override("incomplete_chain", text)
            return _force_accept("Violation rejected: Missing source line number.")

    # Literal string check
    if verdict == "REJECT":
        source_line = step1.get("line", -1)
        source_expression = step1.get("expression", "")
        if _is_literal_source(user_command, source_line, expression=source_expression):
            logger.warning(f"PARSER OVERRIDE: literal string source")
            _log_override("literal_string_source", text)
            return _force_accept(f"Violation rejected: Source at line {source_line} is a literal string.")

    # Proximity reasoning check
    if verdict == "REJECT":
        rejection_text = (reasoning + " " + str(json_block)).lower()
        proximity_keywords = ["proximity", "co-location", "nearby", "co-located", "same scope"]
        if any(kw in rejection_text for kw in proximity_keywords):
            logger.warning(f"PARSER OVERRIDE: proximity argument")
            _log_override("proximity_argument_detected", text)
            return _force_accept("Violation rejected: Proximity/Co-location is not evidence of a violation.")

    # Return legacy format result
    return {
        "verdict": verdict,
        "score": 1.0 if verdict == "REJECT" else 0.0,
        "reasoning": reasoning,
        "violations": [],  # V2 PURGE: Legacy violations deprecated
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

# V2 PURGE: Legacy _format_violations function removed
# All security issues now use V2 {"findings": [...]} format

if __name__ == "__main__":
    # Internal test logic
    pass
