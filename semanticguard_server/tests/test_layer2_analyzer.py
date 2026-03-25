import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from semanticguard_server.engine.layer2.analyzer import (
    _build_focused_prompt,
    _parse_response,
    Layer2SourceResult
)

class TestLayer2Analyzer(unittest.TestCase):

    def _make_spec(self, variable, line, expression, propagation=None, sink_hits=None):
        return {
            "pii_sources": [{"variable": variable, "line": line, "expression": expression}],
            "propagation_steps": propagation or [],
            "sink_hits": sink_hits or [],
            "trace_boundary_reached": False
        }

    # ── Prompt Builder Tests ─────────────────────────────────────────────
    def test_prompt_contains_variable_name(self):
        spec = self._make_spec("user", 1, "user = request.json.get('username')")
        prompt = _build_focused_prompt(
            variable="user",
            source_line=1,
            source_expression="user = request.json.get('username')",
            propagation_steps=[{"variable": "user", "line": 2, "to": "print"}],
            sink_hits=[],
            code_snippet="user = request.json.get('username')\nprint(user)",
            registered_sinks="redact, sanitize"
        )
        self.assertIn("user", prompt)
        self.assertIn("line 1", prompt.lower())

    def test_prompt_contains_propagation_steps(self):
        prompt = _build_focused_prompt(
            variable="email",
            source_line=3,
            source_expression="email = req.body['email']",
            propagation_steps=[{"variable": "email", "line": 4, "to": "console.log"}],
            sink_hits=[],
            code_snippet="email = req.body['email']\nconsole.log(email)",
            registered_sinks="secureLogger"
        )
        self.assertIn("console.log", prompt)

    def test_prompt_excludes_other_variable_propagation(self):
        """Propagation steps for other variables must not appear."""
        prompt = _build_focused_prompt(
            variable="user",
            source_line=1,
            source_expression="user = req.body['user']",
            propagation_steps=[
                {"variable": "user", "line": 2, "to": "print"},
                {"variable": "email", "line": 5, "to": "console.log"}
            ],
            sink_hits=[],
            code_snippet="user = req.body['user']\nprint(user)",
            registered_sinks=""
        )
        self.assertIn("print", prompt)

    def test_prompt_shows_registered_sink_as_safe(self):
        prompt = _build_focused_prompt(
            variable="name",
            source_line=1,
            source_expression="name = req.body['name']",
            propagation_steps=[],
            sink_hits=[{"variable": "name", "line": 2, "sink_name": "redact"}],
            code_snippet="name = req.body['name']\nredact(name)",
            registered_sinks="redact"
        )
        self.assertIn("SAFE", prompt)

    # ── Response Parser Tests ────────────────────────────────────────────
    def test_parse_valid_reject(self):
        raw = '{"verdict": "REJECT", "confidence": "HIGH", "sink_line": 2, "sink_name": "print", "rejection_reason": "user reaches print without sanitization"}'
        result = _parse_response(raw, "user")
        self.assertEqual(result.verdict, "REJECT")
        self.assertEqual(result.confidence, "HIGH")
        self.assertEqual(result.sink_line, 2)
        self.assertIn("sanitization", result.rejection_reason)

    def test_parse_valid_accept(self):
        raw = '{"verdict": "ACCEPT", "confidence": "HIGH", "sink_line": null, "sink_name": null, "rejection_reason": ""}'
        result = _parse_response(raw, "user")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertEqual(result.confidence, "HIGH")

    def test_parse_malformed_defaults_to_accept(self):
        raw = "this is not json at all"
        result = _parse_response(raw, "user")
        self.assertEqual(result.verdict, "ACCEPT")
        self.assertEqual(result.confidence, "LOW")

    def test_parse_markdown_fenced_json(self):
        raw = '```json\n{"verdict": "REJECT", "confidence": "HIGH", "rejection_reason": "data leak"}\n```'
        result = _parse_response(raw, "user")
        self.assertEqual(result.verdict, "REJECT")

    def test_parse_missing_fields_defaults_accept(self):
        raw = '{"some_field": "some_value"}'
        result = _parse_response(raw, "user")
        self.assertEqual(result.verdict, "ACCEPT")

    # ── Layer2Result Aggregation ─────────────────────────────────────────
    def test_one_reject_makes_result_reject(self):
        from semanticguard_server.engine.layer2.analyzer import Layer2Result
        result = Layer2Result()
        result.add_source_result(Layer2SourceResult(
            variable="user", source_line=1,
            verdict="ACCEPT", confidence="HIGH"
        ))
        result.add_source_result(Layer2SourceResult(
            variable="email", source_line=2,
            verdict="REJECT", confidence="HIGH",
            rejection_reason="email reaches console.log"
        ))
        self.assertEqual(result.verdict, "REJECT")

    def test_all_accept_keeps_result_accept(self):
        from semanticguard_server.engine.layer2.analyzer import Layer2Result
        result = Layer2Result()
        result.add_source_result(Layer2SourceResult(
            variable="user", source_line=1,
            verdict="ACCEPT", confidence="HIGH"
        ))
        result.add_source_result(Layer2SourceResult(
            variable="email", source_line=2,
            verdict="ACCEPT", confidence="HIGH"
        ))
        self.assertEqual(result.verdict, "ACCEPT")

if __name__ == "__main__":
    unittest.main(verbosity=2)
