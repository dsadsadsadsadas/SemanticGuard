import sys
import os
sys.path.insert(0, os.getcwd())

from semanticguard_server import sink_registry

print(f"Initial: {len(sink_registry._current_registry['middleware'])}")

# Mock a config that should NOT double
config = {"middleware": ["custom"]}
with open("temp_sinks.json", "w") as f:
    import json
    json.dump(config, f)

sink_registry.load("temp_sinks.json")
print(f"After load: {len(sink_registry._current_registry['middleware'])}")
print(f"Middleware: {sink_registry._current_registry['middleware']}")

sink_registry.load("non_existent.json")
print(f"After fallback: {len(sink_registry._current_registry['middleware'])}")
print(f"Middleware: {sink_registry._current_registry['middleware']}")

# Cleanup
if os.path.exists("temp_sinks.json"):
    os.remove("temp_sinks.json")
