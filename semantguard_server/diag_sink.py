import ast
import sys
import os

# Put semantguard_server in path
sys.path.insert(0, os.path.join(os.getcwd(), ".."))

from semantguard_server import sink_registry

code = "v2 = redact(v1)"
tree = ast.parse(code)
assign = tree.body[0]
call = assign.value

print(f"Node: {ast.dump(call)}")
print(f"Is Sink: {sink_registry.is_sink(call)}")
print(f"Middleware: {sink_registry._current_registry['middleware']}")
