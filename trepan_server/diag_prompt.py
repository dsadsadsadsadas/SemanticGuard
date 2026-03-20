import sys
import os
sys.path.insert(0, os.getcwd())

from trepan_server import prompt_builder

code = """
name = req.body['name']
print(name)
"""
spec = prompt_builder.extract_data_flow_spec(code)

print(f"Sources found: {len(spec['pii_sources'])}")
for source in spec['pii_sources']:
    print(f"Source: {source}")

print(f"Propagation steps: {len(spec['propagation_steps'])}")
for step in spec['propagation_steps']:
    print(f"Step: {step}")
