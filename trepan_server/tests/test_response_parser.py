import unittest
import json
import os
import shutil
from trepan_server import response_parser

class TestResponseParser(unittest.TestCase):
    def setUp(self):
        # Ensure logs directory exists and is clean for testing
        if os.path.exists("logs"):
            shutil.rmtree("logs")
        os.makedirs("logs", exist_ok=True)
        self.log_path = os.path.join("logs", "trepan_parse_errors.jsonl")

    def test_valid_reject_passes(self):
        code = "name = req.body['name']\nprint(name)"
        raw_response = json.dumps({
            "data_flow_logic": {
                "step_1_source": {"variable": "name", "line": 1, "expression": "req.body['name']"},
                "step_2_propagation": [{"line": 2, "call": "print", "argument_position": 0}],
                "step_3_sink_check": {"hits_sanitization_sink": False, "sink_name": None, "reaches_unsafe_output": True, "output_line": 2}
            },
            "chain_complete": True,
            "verdict": "REJECT",
            "confidence": "HIGH",
            "rejection_reason": "Sensitive data from req.body reaches print() without sanitization."
        })
        result = response_parser.guillotine_parser(raw_response, user_command=code)
        self.assertEqual(result["verdict"], "REJECT")
        self.assertEqual(len(result["violations"]), 1)

    def test_malformed_json_override(self):
        code = "x = 1"
        raw_response = "This is not JSON { \"verdict\": \"REJECT\"" # missing closing brace
        result = response_parser.guillotine_parser(raw_response, user_command=code)
        self.assertEqual(result["verdict"], "ACCEPT")
        self.assertIn("malformed_cot_schema", open(self.log_path).read())

    def test_literal_source_override(self):
        code = "name = 'John Doe'\nprint(name)"
        raw_response = json.dumps({
            "data_flow_logic": {
                "step_1_source": {"variable": "name", "line": 1, "expression": "'John Doe'"},
                "step_2_propagation": [],
                "step_3_sink_check": {"hits_sanitization_sink": False, "sink_name": None, "reaches_unsafe_output": True, "output_line": 2}
            },
            "chain_complete": True,
            "verdict": "REJECT",
            "confidence": "HIGH",
            "rejection_reason": "Literal string flagged as PII."
        })
        result = response_parser.guillotine_parser(raw_response, user_command=code)
        self.assertEqual(result["verdict"], "ACCEPT")
        self.assertIn("literal_string_source", open(self.log_path).read())

    def test_proximity_reasoning_override(self):
        code = "name = req.body['name']\nlogger.info('User logged in')\nprint(name)"
        # The model flags because line 2 is "nearby"
        raw_response = json.dumps({
            "data_flow_logic": {
                "step_1_source": {"variable": "name", "line": 1, "expression": "req.body['name']"},
                "step_2_propagation": [],
                "step_3_sink_check": {"hits_sanitization_sink": False, "sink_name": None, "reaches_unsafe_output": True, "output_line": 3}
            },
            "chain_complete": True,
            "verdict": "REJECT",
            "confidence": "HIGH",
            "rejection_reason": "The logger is in close proximity to the data source."
        })
        result = response_parser.guillotine_parser(raw_response, user_command=code)
        self.assertEqual(result["verdict"], "ACCEPT")
        self.assertIn("proximity_argument_detected", open(self.log_path).read())

    def test_incomplete_chain_override(self):
        code = "name = req.body['name']"
        raw_response = json.dumps({
            "data_flow_logic": {
                "step_1_source": {"variable": "name", "line": 1, "expression": "req.body['name']"},
                "step_2_propagation": [],
                "step_3_sink_check": None
            },
            "chain_complete": False,
            "verdict": "REJECT",
            "confidence": "LOW",
            "rejection_reason": "I suspect it might reach a sink later."
        })
        result = response_parser.guillotine_parser(raw_response, user_command=code)
        self.assertEqual(result["verdict"], "ACCEPT")
        self.assertIn("incomplete_chain", open(self.log_path).read())

if __name__ == "__main__":
    unittest.main()
