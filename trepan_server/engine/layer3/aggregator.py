"""
Trepan V2.0 — Layer 3: Result Aggregator

Merges Layer 1 and Layer 2 results into one unified verdict.
Handles combined violations, deduplication, and severity ranking.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("trepan.engine.layer3")

@dataclass
class AggregatedResult:
    verdict: str = "ACCEPT"
    drift_score: float = 0.0
    violations: List[Dict] = field(default_factory=list)
    reasoning: str = ""
    raw_output: str = ""
    layers_used: List[str] = field(default_factory=list)

def aggregate(
    layer1_result=None,
    layer2_result=None,
    v1_result: Optional[Dict] = None
) -> AggregatedResult:
    """
    Merge results from all active layers into one unified verdict.
    Priority: Layer 1 > Layer 2 > v1.0
    Any REJECT from any layer = final REJECT.
    """
    result = AggregatedResult()
    all_violations = []
    
    # ── Layer 1 results ──────────────────────────────────────────────────
    if layer1_result and layer1_result.screener_ran:
        result.layers_used.append("Layer1")
        if layer1_result.verdict == "REJECT":
            for v in layer1_result.violations:
                all_violations.append({
                    "rule_id": v.rule_id,
                    "rule_name": v.rule_name,
                    "line_number": v.line_number,
                    "violation": v.description,
                    "data_flow": f"Deterministic match: {v.matched_text[:80]}",
                    "confidence": "HIGH",
                    "severity": v.severity,
                    "source_layer": "Layer 1",
                    "suggested_fix": v.suggested_fix
                })
    
    # ── Layer 2 results ──────────────────────────────────────────────────
    if layer2_result and layer2_result.source_results:
        result.layers_used.append("Layer2")
        if layer2_result.verdict == "REJECT":
            for sr in layer2_result.source_results:
                if sr.verdict == "REJECT":
                    all_violations.append({
                        "rule_id": "L2-DATA-FLOW",
                        "rule_name": "Insecure Data Flow",
                        "line_number": sr.source_line,
                        "violation": sr.rejection_reason,
                        "data_flow": f"Source: {sr.variable} (line {sr.source_line}) -> Sink: {sr.sink_name or 'unknown'} (line {sr.sink_line or '?'})",
                        "confidence": sr.confidence,
                        "severity": "HIGH",
                        "source_layer": "Layer 2",
                        "suggested_fix": "Sanitize input using a registered sink (e.g., redact(), strip_pii()) before output."
                    })
    
    # ── v1.0 fallback results ────────────────────────────────────────────
    if v1_result:
        result.layers_used.append("V1.0")
        if v1_result.get("verdict") == "REJECT":
            for v in v1_result.get("violations", []):
                # Avoid duplicating what Layer 2 already found
                already_reported = any(
                    ex["line_number"] == v.get("line_number")
                    for ex in all_violations
                )
                if not already_reported:
                    v["source_layer"] = "V1.0"
                    all_violations.append(v)
    
    # ── Final verdict ────────────────────────────────────────────────────
    if all_violations:
        result.verdict = "REJECT"
        result.drift_score = 1.0
        
        # Sort by severity: CRITICAL first, then HIGH, then MEDIUM
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
        all_violations.sort(
            key=lambda v: severity_order.get(v.get("severity", "HIGH"), 1)
        )
        
        layers_str = " + ".join(result.layers_used)
        result.reasoning = (
            f"[{layers_str}] {len(all_violations)} violation(s) found. "
            f"Most severe: {all_violations[0]['rule_id']} on line {all_violations[0]['line_number']}."
        )
        result.raw_output = f"[AGGREGATED — {layers_str}] {result.reasoning}"
        logger.info(f"Layer 3 REJECT — {len(all_violations)} violation(s) from {layers_str}")
    else:
        result.verdict = "ACCEPT"
        result.drift_score = 0.0
        layers_str = " + ".join(result.layers_used) if result.layers_used else "unknown"
        result.reasoning = f"[{layers_str}] All layers cleared. No violations found."
        result.raw_output = f"[AGGREGATED — {layers_str}] ACCEPT"
        logger.info(f"Layer 3 ACCEPT — cleared by {layers_str}")
    
    result.violations = all_violations
    return result
