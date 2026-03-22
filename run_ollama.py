import requests
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "trepan_server"))
import prompt_builder

def main():
    with open("crash_test.js", "r") as f:
        code = f.read()

    import sink_registry
    sinks_list = ", ".join(sink_registry._current_registry["middleware"])
    formatted_system = prompt_builder.STRUCTURAL_INTEGRITY_SYSTEM.format(sinks=sinks_list)
    
    prompt = prompt_builder.build_prompt(
        system_rules=formatted_system,
        user_command=code,
        file_extension=".js",
        model_name="deepseek-r1:7b"
    )

    payload = {
        # Using llama3.1:8b to avoid invalid JSON output like unquoted variables
        "model": "llama3.1:8b",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {"num_predict": 1500, "temperature": 0.1}
    }
    
    print("Asking deepseek-r1:7b...")
    try:
        resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=60)
        output = resp.json()["message"]["content"]
    except Exception as e:
        print("deepseek failed:", e)
        payload["model"] = "llama3.1:8b"
        print("Asking llama3.1:8b instead...")
        resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=60)
        output = resp.json()["message"]["content"]
        
    print("--- RAW API RESPONSE ---")
    print(output)
    
    import response_parser
    try:
        result = response_parser.guillotine_parser(output, user_command=code)
        print("\n--- VERDICT ---")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print("Parser failed:", e)

main()
