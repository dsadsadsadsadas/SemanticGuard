import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "trepan_server"))

import prompt_builder
import response_parser
import model_loader
import sink_registry
import logging

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

def test_file(filename, model_name):
    with open(filename, "r") as f:
        code = f.read()

    sinks_list = ", ".join(sink_registry._current_registry["middleware"])
    formatted_system = prompt_builder.STRUCTURAL_INTEGRITY_SYSTEM.format(sinks=sinks_list)
        
    prompt = prompt_builder.build_prompt(
        system_rules=formatted_system,
        user_command=code,
        file_extension=".js",
        model_name=model_name
    )
    
    print(f"=== Testing {filename} with {model_name} ===")
    output = model_loader.generate(prompt=prompt, system_prompt=formatted_system, model_name=model_name)
    print("RAW THOUGHTS:\n" + output)
    result = response_parser.guillotine_parser(output, user_command=code)
    print("VERDICT:", result["verdict"])
    print("="*40 + "\n")

if __name__ == "__main__":
    for i in range(3):
        print(f"Run {i+1}/3")
        test_file("cool.js", "deepseek-r1")
