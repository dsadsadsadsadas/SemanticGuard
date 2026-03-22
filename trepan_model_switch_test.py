"""
trepan_model_switch_test.py
Tests the cost of switching between llama3.1:8b and deepseek-r1:7b mid-session.
Measures: switch latency, first-request-after-switch penalty, and stability.
"""
import sys
import time
import re
import requests

sys.path.insert(0, ".")

from trepan_server.prompt_builder import build_prompt, STRUCTURAL_INTEGRITY_SYSTEM
from trepan_server.response_parser import guillotine_parser

OLLAMA_URL = "http://localhost:11434/api/chat"

MODELS = {
    "fast": "llama3.1:8b",
    "smart": "deepseek-r1:7b"
}

TEST_CASES = [
    {
        "name": "Literal string (expect ACCEPT)",
        "code": 'name = "John Doe"\nprint(name)',
        "ext": ".py",
        "expected": "ACCEPT"
    },
    {
        "name": "Single source violation (expect REJECT)",
        "code": "name = req.body['name']\nprint(name)",
        "ext": ".py",
        "expected": "REJECT"
    },
    {
        "name": "Sanitized flow (expect ACCEPT)",
        "code": "name = req.body['name']\nsafe = redact(name)\nprint(safe)",
        "ext": ".py",
        "expected": "ACCEPT"
    },
]

def strip_think(raw: str) -> str:
    import re as _re
    target = r'"(?:verdict|data_flow_logic|chain_complete)"'
    matches = list(_re.finditer(r'\{[^{}]*' + target, raw))
    if matches:
        start = matches[-1].start()
        candidate = raw[start:]
        count = 0
        end = 0
        for i, ch in enumerate(candidate):
            if ch == '{': count += 1
            elif ch == '}':
                count -= 1
                if count == 0:
                    end = i + 1
                    break
        return candidate[:end].strip() if end > 0 else ""
    return _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()

def call_model(model: str, prompt: str, system: str) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 2048,
            "num_gpu": 999,
            "num_predict": 512,
        }
    }
    t = time.perf_counter()
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    elapsed = time.perf_counter() - t
    data = resp.json()
    content = data.get("message", {}).get("content", "")
    load_duration = data.get("load_duration", 0) / 1e9
    return {
        "content": content,
        "elapsed": elapsed,
        "load_duration": load_duration,
        "output_tokens": data.get("eval_count", 0)
    }

def run_test(model_name: str, test: dict, label: str) -> dict:
    prompt = build_prompt(
        system_rules="",
        user_command=test["code"],
        file_extension=test["ext"]
    )
    result = call_model(model_name, prompt, STRUCTURAL_INTEGRITY_SYSTEM)
    stripped = strip_think(result["content"])
    parsed = guillotine_parser(stripped, user_command=test["code"])
    verdict = parsed["verdict"]
    correct = verdict == test["expected"]
    
    switch_note = f" ← MODEL LOAD: {result['load_duration']:.2f}s" if result['load_duration'] > 0.5 else ""
    status = "✅" if correct else "❌"
    print(f"  {label} [{model_name}] {test['name']}: {verdict} {status} | {result['elapsed']:.1f}s{switch_note}")
    
    return {
        "elapsed": result["elapsed"],
        "load_duration": result["load_duration"],
        "correct": correct,
        "verdict": verdict
    }

if __name__ == "__main__":
    print("\n" + "="*60)
    print("TREPAN MODEL SWITCH TRANSITION TEST")
    print("="*60)
    print("\nThis test measures the cost of switching between models.")
    print("A high load_duration on the first call after a switch")
    print("means the GPU had to evict the previous model from VRAM.\n")
    
    # Phase 1 — Warm up Llama
    print("─── PHASE 1: Warm up llama3.1:8b ───\n")
    warmup1 = call_model(MODELS["fast"], "Say READY.", "You are a test.")
    print(f"  Llama warmup: {warmup1['elapsed']:.1f}s (load: {warmup1['load_duration']:.2f}s)\n")
    
    # Phase 2 — Run 3 tests on Llama (baseline)
    print("─── PHASE 2: Llama baseline (3 tests) ───\n")
    llama_times = []
    for test in TEST_CASES:
        r = run_test(MODELS["fast"], test, "LLAMA ")
        llama_times.append(r["elapsed"])
    print(f"\n  Llama avg: {sum(llama_times)/len(llama_times):.1f}s\n")
    
    # Phase 3 — Switch to DeepSeek (first call = switch cost)
    print("─── PHASE 3: Switch to deepseek-r1:7b (FIRST CALL = SWITCH COST) ───\n")
    switch_result = run_test(MODELS["smart"], TEST_CASES[0], "SWITCH")
    print(f"\n  ⚠️  Switch cost (load_duration): {switch_result['load_duration']:.2f}s")
    print(f"  ⚠️  Total first request after switch: {switch_result['elapsed']:.1f}s\n")
    
    # Phase 4 — Run 2 more tests on DeepSeek (should be warm now)
    print("─── PHASE 4: DeepSeek warm (2 more tests) ───\n")
    ds_times = [switch_result["elapsed"]]
    for test in TEST_CASES[1:]:
        r = run_test(MODELS["smart"], test, "DEEP  ")
        ds_times.append(r["elapsed"])
    print(f"\n  DeepSeek avg (including switch): {sum(ds_times)/len(ds_times):.1f}s")
    print(f"  DeepSeek avg (excluding switch): {sum(ds_times[1:])/len(ds_times[1:]):.1f}s\n")
    
    # Phase 5 — Switch back to Llama (second switch)
    print("─── PHASE 5: Switch BACK to llama3.1:8b ───\n")
    switch_back = run_test(MODELS["fast"], TEST_CASES[0], "BACK  ")
    print(f"\n  ⚠️  Switch-back cost (load_duration): {switch_back['load_duration']:.2f}s")
    print(f"  ⚠️  Total first request after switch-back: {switch_back['elapsed']:.1f}s\n")
    
    # Phase 6 — Final summary
    print("="*60)
    print("TRANSITION COST SUMMARY")
    print("="*60)
    print(f"  Llama baseline avg:          {sum(llama_times)/len(llama_times):.1f}s")
    print(f"  DeepSeek baseline avg:       {sum(ds_times[1:])/len(ds_times[1:]):.1f}s")
    print(f"  Llama → DeepSeek switch:     {switch_result['elapsed']:.1f}s (load: {switch_result['load_duration']:.2f}s)")
    print(f"  DeepSeek → Llama switch:     {switch_back['elapsed']:.1f}s (load: {switch_back['load_duration']:.2f}s)")
    
    switch_penalty = switch_result["load_duration"]
    if switch_penalty > 10:
        print(f"\n  🔴 HIGH switch penalty ({switch_penalty:.1f}s) — model evicted from VRAM each time")
        print(f"     Users will feel a significant pause on every model switch")
    elif switch_penalty > 3:
        print(f"\n  🟡 MODERATE switch penalty ({switch_penalty:.1f}s) — acceptable for manual switches")
        print(f"     Users should not switch mid-session frequently")
    else:
        print(f"\n  🟢 LOW switch penalty ({switch_penalty:.1f}s) — switching is seamless")
        print(f"     Safe to allow per-file or per-session model selection")
    
    print("\n" + "="*60)
    print("TEST COMPLETE — paste full output for review")
    print("="*60)
