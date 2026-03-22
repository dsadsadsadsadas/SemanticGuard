import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "trepan_server"))

import prompt_builder
import response_parser
import model_loader
import sink_registry

def main():
    crash_file = "crash_test.js"
    with open(crash_file, "r") as f:
        code = f.read()

    # Get registered sinks
    sinks_list = ", ".join(sink_registry._current_registry["middleware"])
    
    # Format the system prompt
    formatted_system = prompt_builder.STRUCTURAL_INTEGRITY_SYSTEM.format(sinks=sinks_list)
    
    prompt = prompt_builder.build_prompt(
        system_rules=formatted_system,
        user_command=code,
        file_extension=".js",
        model_name="deepseek-r1:7b"
    )
    
    print("Testing with deepseek-r1:7b...")
    
    output = model_loader.generate(prompt=prompt, model_name="deepseek-r1:7b")
        
    print("RAW THOUGHTS:")
    print(output)
    
    result = response_parser.guillotine_parser(output, user_command=code)
    print("\nVERDICT:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
