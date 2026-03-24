#!/usr/bin/env python3
"""
🛡️ SemantGuard Prompt Optimization V2 - API Model Prompt Builder

Reduces hallucinations and over-flagging in API/enterprise models (Claude, DeepSeek, etc.)
by enforcing strict reasoning constraints, context awareness, and structured output.

Core Principle: Pattern detection → Context validation → Controlled verdict
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("semantguard.api_prompt_builder")

# ── V2 CONSTRAINED SYSTEM PROMPT ────────────────────────────────────────────

API_SYSTEM_PROMPT_V2 = """You are a security auditor that must minimize false positives. You ONLY flag issues that are realistically exploitable in the given context.

HARD CONSTRAINTS (CRITICAL - FOLLOW EXACTLY):
1. Do NOT assume user input unless explicitly shown
2. Do NOT assume shell=True unless explicitly present
2b. Environment variables used in SQL queries ARE a real injection risk — treat as REJECT
3. Treat hardcoded constants as SAFE unless proven otherwise
   EXCEPTION: Hardcoded credentials (API keys, passwords, tokens, secrets) are ALWAYS CRITICAL regardless of being constants
4. Prefer FALSE NEGATIVE over FALSE POSITIVE when uncertain
5. If unsure → classify as LOW, not HIGH/CRITICAL

CRITICAL SECURITY PATTERNS (ALWAYS FLAG):
- Hardcoded credentials: API keys (AWS, OpenAI, etc.), passwords, tokens, secrets
  Pattern: Strings matching [A-Z0-9]{20,} or containing "key", "secret", "password", "token" in variable name
- Sensitive data in output sinks: print(), console.log(), logger.debug(), logger.info()
  If password, credit card, SSN, or PII reaches ANY output → CRITICAL
- SQL injection: String concatenation or f-strings in SQL queries
  Includes: WHERE, FROM, LIKE, ORDER BY clauses with dynamic values

REQUIRED REASONING STEPS (MANDATORY ORDER):
1. Detect risky pattern (e.g., subprocess, eval, SQL, hardcoded credential, logging sensitive data)
2. Check for user-controlled input (YES / NO)
   NOTE: Environment variables CAN be attacker-controlled in some contexts
3. Check execution context:
   - shell=True? (YES / NO)
   - argument list vs string?
   - Is sensitive data being logged/printed?
4. Determine exploitability:
   - Can attacker influence execution? (YES / NO)
   - Is credential exposed in code? (YES / NO)
   - Is PII/password reaching output? (YES / NO)
5. Only then assign severity

If steps are skipped → response is INVALID

OUTPUT SCHEMA (STRICT JSON ONLY):
{
    "pattern_detected": "description of risky pattern found",
    "user_controlled_input": true/false,
    "uses_shell": true/false,
    "argument_type": "list/string/none",
    "exploitability": "real/theoretical/none",
    "severity": "CRITICAL/HIGH/MEDIUM/LOW/NONE",
    "confidence": 0.0-1.0,
    "reasoning": "step-by-step explanation following the 5 required steps"
}

ANTI-HALLUCINATION GUARD:
If the code does not explicitly show a vulnerability, you MUST NOT infer one.

VALIDATION RULES:
- If user_controlled_input = false BUT hardcoded credential detected → severity = CRITICAL
- If sensitive data (password, SSN, credit card) in print/log → severity = CRITICAL
- If uses_shell = false AND argument_type = "list" → severity ≤ LOW
- If exploitability = "none" AND no credential exposure → severity = NONE
- If pattern_detected = "none" → all other fields should reflect no risk"""

API_SYSTEM_PROMPT_V2_FAST = """You are a security auditor. Minimize false positives. Only flag realistically exploitable issues.

CONSTRAINTS:
- No user input shown → cannot be CRITICAL
- shell=False + list args → LOW max
- Exploitability=none → severity=NONE
- Hardcoded strings ARE suspicious if they look like keys/passwords
- Logging sensitive data (passwords, tokens, PII) to ANY sink is CRITICAL
- env vars in SQL queries = real SQL injection risk

REASON IN ORDER:
1. Risky pattern?
2. User/env controlled?
3. Exploitable?
4. Severity?

OUTPUT (JSON only, 4 fields):
{"severity":"CRITICAL|HIGH|MEDIUM|LOW|NONE","exploitability":"real|theoretical|none","user_controlled":true|false,"reason":"one sentence"}"""

API_SYSTEM_PROMPT_V1_LEGACY = """You are SemantGuard, a security-focused code auditor. Analyze the provided code for security violations and architectural drift.

Return ONLY valid JSON in this exact format:
{
    "action": "ACCEPT or REJECT",
    "drift_score": 0.0 to 1.0,
    "reasoning": "Brief explanation",
    "violations": [
        {
            "rule_id": "string",
            "line_number": number,
            "violation": "description",
            "confidence": "HIGH or LOW"
        }
    ]
}

CRITICAL SECURITY RULES:
- REJECT if hardcoded secrets, API keys, or passwords are found
- REJECT if eval() or exec() is used with user input
- REJECT if subprocess/os.system is used with shell=True
- REJECT if SQL queries use string concatenation
- REJECT if sensitive data reaches print/console.log without sanitization"""

# ── PROMPT BUILDER FUNCTIONS ────────────────────────────────────────────────

def build_api_prompt_v2(filename: str, code_snippet: str) -> Dict[str, str]:
    """
    Build the new V2 constrained prompt for API models.
    
    Args:
        filename: Name of the file being analyzed
        code_snippet: Code content to analyze
        
    Returns:
        Dict with 'system' and 'user' prompt content
    """
    
    user_prompt = f"""Analyze this code for security violations following the required reasoning steps:

Filename: {filename}

Code:
```
{code_snippet}
```

Follow the 5 required reasoning steps in order:
1. Pattern Detection: What risky patterns do you see?
2. Input Analysis: Is there user-controlled input?
3. Context Analysis: How is the risky pattern used?
4. Exploitability: Can an attacker actually exploit this?
5. Severity Assignment: Based on real exploitability

Provide your analysis in the required JSON format."""

    return {
        "system": API_SYSTEM_PROMPT_V2,
        "user": user_prompt
    }

def build_api_prompt_v2_fast(filename: str, code_snippet: str) -> Dict[str, str]:
    """
    V2 Fast — same reasoning discipline as V2 but compressed output.
    Targets under 0.7s average response time while maintaining V2 accuracy.
    """
    user_prompt = f"Audit: {filename}\n```\n{code_snippet.strip()}\n```\nJSON only."
    
    return {
        "system": API_SYSTEM_PROMPT_V2_FAST,
        "user": user_prompt
    }

def build_api_prompt_v1_legacy(filename: str, code_snippet: str) -> Dict[str, str]:
    """
    Build the legacy V1 prompt for comparison testing.
    
    Args:
        filename: Name of the file being analyzed
        code_snippet: Code content to analyze
        
    Returns:
        Dict with 'system' and 'user' prompt content
    """
    
    user_prompt = f"""Analyze this code for security violations:

Filename: {filename}

Code:
```
{code_snippet}
```

Provide your analysis in JSON format."""

    return {
        "system": API_SYSTEM_PROMPT_V1_LEGACY,
        "user": user_prompt
    }

# ── RESPONSE VALIDATION ─────────────────────────────────────────────────────

def validate_v2_response(response_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate V2 API response for logical consistency and completeness.
    
    Args:
        response_json: Parsed JSON response from API model
        
    Returns:
        Dict with validation results and potentially corrected response
    """
    
    validation_result = {
        "valid": True,
        "errors": [],
        "corrected_response": response_json.copy()
    }
    
    required_fields = [
        "pattern_detected", "user_controlled_input", "uses_shell", 
        "argument_type", "exploitability", "severity", "confidence", "reasoning"
    ]
    
    # Check required fields
    for field in required_fields:
        if field not in response_json:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Missing required field: {field}")
    
    if not validation_result["valid"]:
        return validation_result
    
    # Logical consistency checks
    resp = response_json
    
    # Rule: If user_controlled_input = false → severity cannot be CRITICAL
    if not resp.get("user_controlled_input", True) and resp.get("severity") == "CRITICAL":
        validation_result["errors"].append("Logical error: No user input but CRITICAL severity")
        validation_result["corrected_response"]["severity"] = "HIGH"
    
    # Rule: If uses_shell = false AND argument_type = list → severity ≤ LOW
    if (not resp.get("uses_shell", True) and 
        resp.get("argument_type") == "list" and 
        resp.get("severity") in ["CRITICAL", "HIGH", "MEDIUM"]):
        validation_result["errors"].append("Logical error: Safe subprocess usage but high severity")
        validation_result["corrected_response"]["severity"] = "LOW"
    
    # Rule: If exploitability = none → severity must be NONE
    if resp.get("exploitability") == "none" and resp.get("severity") != "NONE":
        validation_result["errors"].append("Logical error: No exploitability but non-zero severity")
        validation_result["corrected_response"]["severity"] = "NONE"
    
    # Rule: If pattern_detected indicates no risk → severity should be NONE
    safe_patterns = ["none", "no pattern", "no risk", "safe", "no issues"]
    if any(safe in resp.get("pattern_detected", "").lower() for safe in safe_patterns):
        if resp.get("severity") != "NONE":
            validation_result["errors"].append("Logical error: No pattern detected but non-zero severity")
            validation_result["corrected_response"]["severity"] = "NONE"
    
    # Confidence validation
    confidence = resp.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        validation_result["errors"].append("Invalid confidence value (must be 0.0-1.0)")
        validation_result["corrected_response"]["confidence"] = 0.5
    
    if validation_result["errors"]:
        validation_result["valid"] = False
        logger.warning(f"V2 response validation errors: {validation_result['errors']}")
    
    return validation_result

def convert_v2_to_legacy_format(v2_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert V2 response format to legacy format for compatibility.
    
    Args:
        v2_response: V2 format response
        
    Returns:
        Legacy format response
    """
    
    # Map severity to action
    severity = v2_response.get("severity", "NONE")
    action = "REJECT" if severity in ["CRITICAL", "HIGH", "MEDIUM"] else "ACCEPT"
    
    # Map severity to drift score
    severity_to_score = {
        "CRITICAL": 1.0,
        "HIGH": 0.8,
        "MEDIUM": 0.6,
        "LOW": 0.3,
        "NONE": 0.0
    }
    drift_score = severity_to_score.get(severity, 0.0)
    
    # Create violations array if rejecting
    violations = []
    if action == "REJECT":
        violations.append({
            "rule_id": "V2_ANALYSIS",
            "line_number": 1,  # V2 doesn't track specific lines yet
            "violation": v2_response.get("pattern_detected", "Security violation detected"),
            "confidence": "HIGH" if v2_response.get("confidence", 0.0) > 0.7 else "LOW"
        })
    
    return {
        "action": action,
        "drift_score": drift_score,
        "reasoning": v2_response.get("reasoning", "V2 analysis completed"),
        "violations": violations,
        # Include V2 metadata for debugging
        "v2_metadata": {
            "pattern_detected": v2_response.get("pattern_detected"),
            "user_controlled_input": v2_response.get("user_controlled_input"),
            "uses_shell": v2_response.get("uses_shell"),
            "argument_type": v2_response.get("argument_type"),
            "exploitability": v2_response.get("exploitability"),
            "severity": v2_response.get("severity"),
            "confidence": v2_response.get("confidence")
        }
    }

# ── STRICT MODE RETRY PROMPT ────────────────────────────────────────────────

STRICT_MODE_RETRY_PROMPT = """Your previous answer violated constraints. Re-evaluate strictly.

REMINDER - You must follow these constraints:
1. Do NOT assume user input unless explicitly shown
2. Do NOT assume shell=True unless explicitly present
3. Treat hardcoded constants as SAFE
4. Prefer FALSE NEGATIVE over FALSE POSITIVE when uncertain

Re-analyze the code and provide a corrected JSON response following the required schema exactly."""

def build_strict_retry_prompt(original_user_prompt: str) -> str:
    """
    Build a strict mode retry prompt when validation fails.
    
    Args:
        original_user_prompt: The original user prompt that failed
        
    Returns:
        Enhanced strict mode prompt
    """
    return f"{STRICT_MODE_RETRY_PROMPT}\n\n{original_user_prompt}"

# ── TESTING AND COMPARISON UTILITIES ────────────────────────────────────────

def compare_v1_v2_responses(v1_response: Dict[str, Any], v2_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare V1 and V2 responses for analysis.
    
    Args:
        v1_response: Legacy V1 format response
        v2_response: New V2 format response
        
    Returns:
        Comparison analysis
    """
    
    # Convert V2 to legacy format for comparison
    v2_legacy = convert_v2_to_legacy_format(v2_response)
    
    comparison = {
        "v1_action": v1_response.get("action"),
        "v2_action": v2_legacy.get("action"),
        "action_changed": v1_response.get("action") != v2_legacy.get("action"),
        "v1_score": v1_response.get("drift_score", 0.0),
        "v2_score": v2_legacy.get("drift_score", 0.0),
        "score_delta": v2_legacy.get("drift_score", 0.0) - v1_response.get("drift_score", 0.0),
        "v1_violations": len(v1_response.get("violations", [])),
        "v2_violations": len(v2_legacy.get("violations", [])),
        "v2_severity": v2_response.get("severity"),
        "v2_exploitability": v2_response.get("exploitability"),
        "v2_confidence": v2_response.get("confidence"),
        "improvement_indicators": []
    }
    
    # Analyze improvements
    if comparison["action_changed"] and comparison["v1_action"] == "REJECT" and comparison["v2_action"] == "ACCEPT":
        comparison["improvement_indicators"].append("Reduced false positive")
    
    if comparison["score_delta"] < -0.2:
        comparison["improvement_indicators"].append("Significantly lower risk score")
    
    if v2_response.get("exploitability") == "none":
        comparison["improvement_indicators"].append("Correctly identified no exploitability")
    
    if v2_response.get("user_controlled_input") == False:
        comparison["improvement_indicators"].append("Correctly identified no user input")
    
    return comparison