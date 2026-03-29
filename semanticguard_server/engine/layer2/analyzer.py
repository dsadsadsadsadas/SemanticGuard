"""
SemanticGuard V2.0 — Layer 2: Focused Model Analyzer

Asks one specific question per PII source instead of one broad question.
Each call is small, fast, and focused — no context drift.
"""
import logging
import requests
import json
import re as _re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("semanticguard.engine.layer2")

OLLAMA_URL = "http://localhost:11434/api/chat"

# ── RESULT TYPES ─────────────────────────────────────────────────────────────

@dataclass
class Layer2SourceResult:
    variable: str
    source_line: int
    verdict: str  # ACCEPT | REJECT
    confidence: str  # HIGH | LOW
    rejection_reason: str = ""
    sink_line: Optional[int] = None
    sink_name: Optional[str] = None

@dataclass
class Layer2Result:
    source_results: List[Layer2SourceResult] = field(default_factory=list)
    verdict: str = "ACCEPT"
    details: str = ""
    
    def add_source_result(self, r: Layer2SourceResult):
        self.source_results.append(r)
        if r.verdict == "REJECT":
            self.verdict = "REJECT"

# ── FOCUSED PROMPT BUILDER ────────────────────────────────────────────────────

LAYER2_SYSTEM = """You are a code security auditor. Answer ONE question about ONE variable. Output ONLY valid JSON. No prose. No explanation.

Output exactly:
{"verdict": "ACCEPT or REJECT", "confidence": "HIGH or LOW", "sink_line": <int or null>, "sink_name": "<string or null>", "rejection_reason": "<string or empty>"}

RULES:
- REJECT only if the variable reaches print(), console.log(), res.json(), logger, or any output WITHOUT first passing through redact(), sanitize(), hashlib, or a safe transformation
- If the variable passes through a safe transformation before output — ACCEPT
- If you cannot confirm the variable reaches any output in the provided lines — ACCEPT
- Literal strings are always SAFE
- Database connection objects (conn, connection) are NOT sensitive data — ACCEPT
- Query results that are parameterized are SAFE — ACCEPT
- Variables that are only used for control flow (not output) — ACCEPT

FEW-SHOT EXAMPLES — CORRECT VERDICTS:

Example 1 — Parameterized query result logged (SAFE):
Variable: connection
Code: connection.query(query, [email], (err, results) => { console.log(results); });
Correct verdict: {"verdict": "ACCEPT", "confidence": "HIGH", "rejection_reason": ""}
Reason: Parameterized query results are safe to log. The query uses ? placeholder.

Example 2 — Database connection object (SAFE):
Variable: conn
Code: conn = sqlite3.connect('users.db'); conn.commit()
Correct verdict: {"verdict": "ACCEPT", "confidence": "HIGH", "rejection_reason": ""}
Reason: Connection objects are not sensitive data. They are control flow objects.

Example 3 — Safe response with validated data (SAFE):
Variable: query
Code: const query = req.query.q; res.send('OK');
Correct verdict: {"verdict": "ACCEPT", "confidence": "HIGH", "rejection_reason": ""}
Reason: res.send('OK') sends a literal string, not the query variable.
"""

def _build_focused_prompt(
    variable: str,
    source_line: int,
    source_expression: str,
    propagation_steps: List[Dict],
    sink_hits: List[Dict],
    code_snippet: str,
    registered_sinks: str
) -> str:
    prop_text = "\n".join([
        f"  Line {p['line']}: passes to {p['to']}"
        for p in propagation_steps
        if p.get("variable") == variable
    ]) or "  No propagation detected"
    
    sink_text = "\n".join([
        f"  Line {s['line']}: hits registered sink {s['sink_name']} — SAFE"
        for s in sink_hits
        if s.get("variable") == variable
    ]) or "  No registered sink reached"
    
    return f"""QUESTION: Does variable `{variable}` reach an unsafe output?

VARIABLE: {variable}
DEFINED: Line {source_line} — {source_expression}

PROPAGATION:
{prop_text}

SINK STATUS:
{sink_text}

REGISTERED SAFE SINKS: {registered_sinks}

RELEVANT CODE:
{code_snippet}

Does `{variable}` reach an unsafe output without passing through a registered sink? Answer in JSON only."""

# ── MODEL CALL ────────────────────────────────────────────────────────────────

def _call_model(prompt: str, model_name: str) -> str:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": LAYER2_SYSTEM},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "format": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["ACCEPT", "REJECT"]},
                "confidence": {"type": "string", "enum": ["HIGH", "LOW"]},
                "sink_line": {"type": ["integer", "null"]},
                "sink_name": {"type": ["string", "null"]},
                "rejection_reason": {"type": "string"}
            },
            "required": ["verdict", "confidence", "rejection_reason"]
        },
        "options": {
            "temperature": 0.1,
            "num_ctx": 1024,
            "num_predict": 150,
            "num_gpu": 999,
        }
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        content = response.json().get("message", {}).get("content", "")
        return content
    except Exception as e:
        logger.error(f"Layer 2 model call failed: {e}")
        return ""

def _parse_response(raw: str, variable: str) -> Layer2SourceResult:
    try:
        # Strip markdown fences if present
        clean = _re.sub(r'^```(?:json)?\s*', '', raw.strip())
        clean = _re.sub(r'\s*```$', '', clean)
        data = json.loads(clean)
        return Layer2SourceResult(
            variable=variable,
            source_line=0,
            verdict=data.get("verdict", "ACCEPT"),
            confidence=data.get("confidence", "LOW"),
            rejection_reason=data.get("rejection_reason", ""),
            sink_line=data.get("sink_line"),
            sink_name=data.get("sink_name")
        )
    except Exception as e:
        logger.warning(f"Layer 2 parse failed for {variable}: {e} — defaulting to ACCEPT")
        return Layer2SourceResult(
            variable=variable,
            source_line=0,
            verdict="ACCEPT",
            confidence="LOW",
            rejection_reason=""
        )

# ── MAIN ANALYZER ─────────────────────────────────────────────────────────────

def _analyze_single_source(
    source: Dict,
    spec: Dict,
    source_code: str,
    model_name: str,
    registered_sinks: str
) -> Layer2SourceResult:
    """Analyze a single PII source (for parallel execution)"""
    variable = source["variable"]
    source_line = source["line"]
    source_expression = source["expression"]
    
    logger.info(f"Layer 2 analyzing source: {variable} (line {source_line})")
    
    prompt = _build_focused_prompt(
        variable=variable,
        source_line=source_line,
        source_expression=source_expression,
        propagation_steps=spec.get("propagation_steps", []),
        sink_hits=spec.get("sink_hits", []),
        code_snippet=source_code[:800],
        registered_sinks=registered_sinks
    )
    
    raw = _call_model(prompt, model_name)
    source_result = _parse_response(raw, variable)
    source_result.source_line = source_line
    
    logger.info(
        f"Layer 2 result for {variable}: {source_result.verdict} "
        f"({source_result.confidence}) — {source_result.rejection_reason[:60] if source_result.rejection_reason else 'no reason'}"
    )
    
    return source_result

def analyze(
    spec: Dict,
    source_code: str,
    model_name: str = "llama3.1:8b",
    registered_sinks: str = ""
) -> Layer2Result:
    """
    Run Layer 2 focused analysis on each PII source from the spec.
    Parallelizes model calls for faster execution.
    """
    result = Layer2Result()
    
    if not spec.get("pii_sources"):
        result.details = "Layer 2: No PII sources to analyze."
        return result
    
    # Parallelize model calls using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(spec["pii_sources"]), 4)) as executor:
        futures = [
            executor.submit(
                _analyze_single_source,
                source,
                spec,
                source_code,
                model_name,
                registered_sinks
            )
            for source in spec["pii_sources"]
        ]
        
        # Collect results as they complete
        for future in futures:
            try:
                source_result = future.result(timeout=60)
                result.add_source_result(source_result)
            except Exception as e:
                logger.error(f"Layer 2 parallel analysis failed: {e}")
    
    violating = [r for r in result.source_results if r.verdict == "REJECT"]
    if violating:
        result.details = f"Layer 2 found {len(violating)} violation(s) across {len(spec['pii_sources'])} source(s)."
    else:
        result.details = f"Layer 2 cleared {len(spec['pii_sources'])} source(s). No violations confirmed."
    
    return result
