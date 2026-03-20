import sys
sys.path.insert(0, ".")

try:
    from trepan_server.response_parser import guillotine_parser
    print("Import successful")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

malformed = '{"data_flow_logic": null, "chain_complete": true, "verdict": "REJECT", "confidence": "HIGH"}'

result = guillotine_parser(malformed, user_command="name = req.body['name']")
print("Result:", result)

import os
log_path = os.path.join("logs", "trepan_parse_errors.jsonl")
if os.path.exists(log_path):
    with open(log_path, "r") as f:
        lines = f.readlines()
    print(f"Log entries: {len(lines)}")
    print("Last entry:", lines[-1] if lines else "empty")
else:
    print("Log file not found at:", log_path)