import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from semanticguard_server.engine.layer3.aggregator import aggregate, AggregatedResult
from semanticguard_server.engine.layer1.screener import Layer1Result, Layer1Violation
from semanticguard_server.engine.layer2.analyzer import Layer2Result, Layer2SourceResult

def make_l1_reject(rule_id="L1-001", line=5):
    r = Layer1Result()
    r.add_violation(Layer1Violation(
        rule_id=rule_id,
        rule_name="Hardcoded Secret",
        line_number=line,
        matched_text='api_key = "secret"',
        severity="CRITICAL",
        description="Hardcoded secret detected.",
        suggested_fix="Use environment variables."
    ))
    return r

def make_l1_accept():
    r = Layer1Result()
    r.details = "No violations."
    return r

def make_l2_reject(variable="user", line=3):
    r = Layer2Result()
    r.add_source_result(Layer2SourceResult(
        variable=variable,
        source_line=line,
        verdict="REJECT",
        confidence="HIGH",
        rejection_reason=f"{variable} reaches print without sanitization",
        sink_line=4,
        sink_name="print"
    ))
    return r

def make_l2_accept():
    r = Layer2Result()
    r.add_source_result(Layer2SourceResult(
        variable="user",
        source_line=1,
        verdict="ACCEPT",
        confidence="HIGH"
    ))
    return r

class TestLayer3Aggregator(unittest.TestCase):

    # ── Both layers ACCEPT ───────────────────────────────────────────────
    def test_both_accept_returns_accept(self):
        result = aggregate(make_l1_accept(), make_l2_accept())
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertEqual(result.drift_score, 0.0)
        self.assertEqual(len(result.violations), 0)

    # ── Layer 1 REJECT only ──────────────────────────────────────────────
    def test_layer1_reject_returns_reject(self):
        result = aggregate(make_l1_reject(), make_l2_accept())
        self.assertEqual(result.verdict, "REJECT")
        self.assertEqual(result.drift_score, 1.0)
        self.assertTrue(any(v["rule_id"] == "L1-001" for v in result.violations))

    def test_layer1_reject_includes_layer_in_reasoning(self):
        result = aggregate(make_l1_reject(), make_l2_accept())
        self.assertIn("Layer1", result.reasoning)

    # ── Layer 2 REJECT only ──────────────────────────────────────────────
    def test_layer2_reject_returns_reject(self):
        result = aggregate(make_l1_accept(), make_l2_reject())
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v["rule_id"] == "L2-DATA-FLOW" for v in result.violations))

    def test_layer2_reject_includes_layer_in_reasoning(self):
        result = aggregate(make_l1_accept(), make_l2_reject())
        self.assertIn("Layer2", result.reasoning)

    # ── Both layers REJECT ───────────────────────────────────────────────
    def test_both_reject_combines_violations(self):
        result = aggregate(make_l1_reject(), make_l2_reject())
        self.assertEqual(result.verdict, "REJECT")
        self.assertEqual(len(result.violations), 2)
        rule_ids = [v["rule_id"] for v in result.violations]
        self.assertIn("L1-001", rule_ids)
        self.assertIn("L2-DATA-FLOW", rule_ids)

    # ── Severity sorting ─────────────────────────────────────────────────
    def test_critical_violations_sorted_first(self):
        result = aggregate(make_l1_reject("L1-001", 5), make_l2_reject("user", 3))
        self.assertEqual(result.violations[0]["severity"], "CRITICAL")

    # ── v1.0 fallback integration ────────────────────────────────────────
    def test_v1_reject_included_when_no_layer_violations(self):
        v1 = {
            "verdict": "REJECT",
            "violations": [{
                "rule_id": "DATA_FLOW_VIOLATION",
                "rule_name": "Insecure Data Flow",
                "line_number": 8,
                "violation": "data reaches output",
                "confidence": "HIGH"
            }]
        }
        result = aggregate(make_l1_accept(), make_l2_accept(), v1_result=v1)
        self.assertEqual(result.verdict, "REJECT")
        self.assertTrue(any(v["source_layer"] == "V1.0" for v in result.violations))

    def test_v1_duplicate_not_added_if_layer2_already_caught_it(self):
        l2 = make_l2_reject("user", 8)
        v1 = {
            "verdict": "REJECT",
            "violations": [{
                "rule_id": "DATA_FLOW_VIOLATION",
                "rule_name": "Insecure Data Flow",
                "line_number": 8,
                "violation": "same line as layer 2",
                "confidence": "HIGH"
            }]
        }
        result = aggregate(make_l1_accept(), l2, v1_result=v1)
        lines = [v["line_number"] for v in result.violations]
        self.assertEqual(lines.count(8), 1)

    # ── layers_used tracking ─────────────────────────────────────────────
    def test_layers_used_tracked_correctly(self):
        result = aggregate(make_l1_accept(), make_l2_reject())
        self.assertIn("Layer1", result.layers_used)
        self.assertIn("Layer2", result.layers_used)

    # ── None inputs handled safely ───────────────────────────────────────
    def test_none_layer1_handled_safely(self):
        result = aggregate(None, make_l2_accept())
        self.assertEqual(result.verdict, "ACCEPT")

    def test_none_layer2_handled_safely(self):
        result = aggregate(make_l1_accept(), None)
        self.assertEqual(result.verdict, "ACCEPT")

if __name__ == "__main__":
    unittest.main(verbosity=2)
