import unittest
import ast
from trepan_server import prompt_builder, sink_registry

class TestPromptBuilder(unittest.TestCase):
    def setUp(self):
        sink_registry.load() # Reset to defaults

    def test_pii_source_extraction_request(self):
        code = "user_name = req.body['name']"
        spec = prompt_builder.extract_data_flow_spec(code)
        self.assertEqual(len(spec["pii_sources"]), 1)
        self.assertEqual(spec["pii_sources"][0]["variable"], "user_name")
        self.assertEqual(spec["pii_sources"][0]["node_type"], "EXTERNAL_INPUT")

    def test_literal_string_exclusion(self):
        code = "user_name = 'John Doe'"
        spec = prompt_builder.extract_data_flow_spec(code)
        # Literal strings with no interpolation should be excluded
        self.assertEqual(len(spec["pii_sources"]), 0)

    def test_depth_3_cutoff(self):
        # We need a chain of 4 hops
        code = """
v1 = req.body['data']
v2 = step1(v1)
v3 = step2(v2)
v4 = step3(v3)
v5 = step4(v4)
"""
        spec = prompt_builder.extract_data_flow_spec(code)
        # v1 is the source. 
        # Propagation: v1->step1, v2->step2, v3->step3.
        # Hop 4 (v4->step4) should trigger trace_boundary_reached: True
        self.assertTrue(spec["trace_boundary_reached"])
        
    def test_sink_termination(self):
        # redact() is a known sink in defaults
        code = """
v1 = req.body['data']
v2 = redact(v1)
console.log(v2)
"""
        spec = prompt_builder.extract_data_flow_spec(code)
        # v1 is source. v1->redact is a sink hit.
        # Trace should stop at v1 passed to redact.
        self.assertEqual(len(spec["sink_hits"]), 1)
        self.assertEqual(spec["sink_hits"][0]["sink_name"], "redact")
        # console.log(v2) should NOT be in propagation_steps because v2 is not traced (v1 was the source)
        # Wait, if v1 was the source, but v2 is assigned the result of a sink... 
        # The prompt builder only traces the source variable name for now.
        # Let's verify propagation steps count.
        self.assertEqual(len(spec["propagation_steps"]), 0)

    def test_prompt_construction_smoking_gun(self):
        code = "name = req.body['name']\nprint(name)"
        prompt = prompt_builder.build_prompt("Rule: 1", code, "py")
        self.assertIn("[SMOKING GUN REQUIREMENT]", prompt)
        self.assertIn("PII SOURCES:", prompt)
        self.assertIn("Variable name", prompt)

if __name__ == "__main__":
    unittest.main()
