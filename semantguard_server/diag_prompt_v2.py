import sys
import os
import ast
sys.path.insert(0, os.getcwd())

from semantguard_server import prompt_builder

code = "name = req.body['name']\nprint(name)"
spec = prompt_builder.extract_data_flow_spec(code)

print(f"Sources: {len(spec['pii_sources'])}")
if len(spec['pii_sources']) > 0:
    print(f"Source 0: {spec['pii_sources'][0]}")

prompt = prompt_builder.build_prompt("Rule: 1", code, "py")
print(f"Prompt contains 'Variable name': {'Variable name' in prompt}")
print(f"Prompt preview:\n{prompt[:300]}")
