import ast
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from trepan_server import prompt_builder, sink_registry

sink_registry.load()

code = """
v1 = req.body['data']
v2 = redact(v1)
console.log(v2)
"""

print("--- AST WALK DIAGNOSTICS ---")
tree = ast.parse(code)
for node in ast.walk(tree):
    if hasattr(node, 'lineno'):
        print(f"{node.__class__.__name__} at L{node.lineno}: {ast.unparse(node)[:50]}")

print("\n--- EXTRACTION ---")
spec = prompt_builder.extract_data_flow_spec(code)
print("Propagation Steps:")
for ps in spec["propagation_steps"]:
    print(ps)

print("\nSink Hits:")
for sh in spec["sink_hits"]:
    print(sh)
