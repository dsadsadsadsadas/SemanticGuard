import time
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, ".")

try:
    from trepan_server.prompt_builder import extract_data_flow_spec, build_prompt, STRUCTURAL_INTEGRITY_SYSTEM
    from trepan_server.model_loader import generate
    from trepan_server.response_parser import guillotine_parser
except ImportError as e:
    print(f"FAILED TO IMPORT TREPAN MODULES: {e}")
    sys.exit(1)

SAMPLE_SHORT = """name = req.body['name']
print(name)"""

# Update to use server.py as a representative large sample
SAMPLE_LONG_PATH = "trepan_server/server.py"
SAMPLE_LONG = open(SAMPLE_LONG_PATH, encoding="utf-8").read() if os.path.exists(SAMPLE_LONG_PATH) else SAMPLE_SHORT

def run_diagnostic(name, code):
    results = {}
    
    # Stage 6 - Full Start
    full_start = time.perf_counter()
    
    # Stage 1 - AST Extraction
    s1_start = time.perf_counter()
    spec = extract_data_flow_spec(code)
    results['s1'] = time.perf_counter() - s1_start
    
    # Stage 2 - Prompt Construction
    s2_start = time.perf_counter()
    prompt = build_prompt(system_rules="", user_command=code, file_extension=".js")
    results['s2'] = time.perf_counter() - s2_start
    results['prompt_len'] = len(prompt)
    results['token_est'] = len(prompt) // 4
    
    # Stage 3 - Prompt Size Analysis
    # Approximate sections from the prompt structure
    s_spec_start = prompt.find("[STRUCTURAL_SPECIFICATION]")
    a_inst_start = prompt.find("ANALYSIS INSTRUCTIONS:")
    code_audit_start = prompt.find("CODE TO AUDIT:")
    
    results['system_rules_len'] = 0 # system_rules passed as ""
    results['s_spec_len'] = a_inst_start - s_spec_start if a_inst_start > s_spec_start else 0
    results['a_inst_len'] = code_audit_start - a_inst_start if code_audit_start > a_inst_start else 0
    results['code_audit_len'] = len(prompt) - code_audit_start if code_audit_start != -1 else 0
    results['total_len'] = len(prompt)
    
    # Stage 4 - Model Inference (GPU default)
    s4_start = time.perf_counter()
    raw_output = generate(prompt, STRUCTURAL_INTEGRITY_SYSTEM, processor_mode="GPU")
    results['s4'] = time.perf_counter() - s4_start
    results['output_len'] = len(raw_output)
    results['output_tokens'] = len(raw_output) // 4
    
    # Stage 5 - Parser
    s5_start = time.perf_counter()
    _ = guillotine_parser(raw_output, user_command=code)
    results['s5'] = time.perf_counter() - s5_start
    
    # Stage 6 - Full End
    results['s6'] = time.perf_counter() - full_start
    
    # Build report section
    print(f"SAMPLE: {name} ({len(code)} chars, ~{len(code)//4} tokens)")
    print(f"  Stage 1 - AST Extraction:      {results['s1']:.3f}s")
    print(f"  Stage 2 - Prompt Construction: {results['s2']:.3f}s")
    print(f"  Stage 3 - Prompt Size:")
    print(f"    [SYSTEM_RULES]:              {results['system_rules_len']} chars")
    print(f"    [STRUCTURAL_SPECIFICATION]:  {results['s_spec_len']} chars")
    print(f"    [ANALYSIS INSTRUCTIONS]:     {results['a_inst_len']} chars")
    print(f"    [CODE TO AUDIT]:             {results['code_audit_len']} chars")
    print(f"    TOTAL:                       {results['total_len']} chars (~{results['token_est']} tokens)")
    print(f"  Stage 4 - Model Inference:     {results['s4']:.3f}s")
    print(f"    Model Output Size:           {results['output_len']} chars (~{results['output_tokens']} tokens)")
    print(f"  Stage 5 - Parser:              {results['s5']:.3f}s")
    print(f"  Stage 6 - End-to-End:          {results['s6']:.3f}s")
    print()
    
    return results

print("======== TREPAN PERFORMANCE DIAGNOSTIC ========")
print()

short_res = run_diagnostic("SHORT", SAMPLE_SHORT)
long_res = run_diagnostic("LONG", SAMPLE_LONG)

print("BOTTLENECK CANDIDATES (any stage > 0.5s):")
bottlenecks = []
for res in [short_res, long_res]:
    for stage in ['s1', 's2', 's4', 's5']:
        if res[stage] > 0.5:
            bottlenecks.append(f"{stage} ({res[stage]:.3f}s)")

if not bottlenecks:
    print("  None detected.")
else:
    for b in sorted(set(bottlenecks)):
        print(f"  {b}")

print()
print("================================================")
