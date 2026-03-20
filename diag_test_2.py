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

print("--- REPRODUCING _trace_variable_recursive(v1) ---")
spec = {"sink_hits": [], "propagation_steps": [], "trace_boundary_reached": False}
tree = ast.parse(code)
target_id = "v1"

# Step 1: Pass 1
sinks_found_at_lines = set()
for node in ast.walk(tree):
    if not hasattr(node, "lineno"): continue
    if isinstance(node, ast.Call):
        all_sub_names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if target_id in all_sub_names:
            if sink_registry.is_sink(node):
                sinks_found_at_lines.add(node.lineno)
                print(f"SINK HIT at L{node.lineno} for {target_id}")

print(f"sinks_found_at_lines: {sinks_found_at_lines}")

# Step 2: Pass 2
for node in ast.walk(tree):
    if not hasattr(node, "lineno"): continue
    
    # DEBUG: print all nodes matching target_id
    if isinstance(node, ast.Assign):
        rhs_names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        if target_id in rhs_names:
            print(f"FOUND Assign for {target_id} at L{node.lineno}. sinks_found_at_lines is {sinks_found_at_lines}")
            if node.lineno in sinks_found_at_lines:
                print(f"SKIPPING Assign at L{node.lineno} because it's in sinks_found_at_lines")
                continue
            print(f"ADDING Assignment at L{node.lineno} to propagation_steps")
    
    if isinstance(node, ast.Call):
        all_sub_names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if target_id in all_sub_names:
            print(f"FOUND Call for {target_id} at L{node.lineno}. sinks_found_at_lines is {sinks_found_at_lines}")
            if node.lineno in sinks_found_at_lines:
                print(f"SKIPPING Call at L{node.lineno}")
                continue
            print(f"ADDING Call at L{node.lineno} to propagation_steps")
