import sys
import time
import json
import requests
import io

# Force UTF-8 for console output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, ".")

from trepan_server.prompt_builder import build_prompt, STRUCTURAL_INTEGRITY_SYSTEM
from trepan_server.response_parser import guillotine_parser

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELS = ["llama3.1:8b", "qwen2.5-coder:7b"]
RUNS = 3

# ── TEST CASES ───────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "A — Literal string (expect ACCEPT)",
        "code": 'name = "John Doe"\nprint(name)',
        "ext": ".py",
        "expected": "ACCEPT"
    },
    {
        "name": "B — Single source to print (expect REJECT)",
        "code": "name = req.body['name']\nprint(name)",
        "ext": ".py",
        "expected": "REJECT"
    },
    {
        "name": "C — Sanitized flow (expect ACCEPT)",
        "code": "name = req.body['name']\nsafe = redact(name)\nprint(safe)",
        "ext": ".py",
        "expected": "ACCEPT"
    },
    {
        "name": "D — Hashlib safe transformation (expect ACCEPT)",
        "code": "password = req.body['password']\nhashed = hashlib.sha256(password.encode()).hexdigest()\nstore(hashed)",
        "ext": ".py",
        "expected": "ACCEPT"
    },
    {
        "name": "E — Depth limit exceeded (expect ACCEPT)",
        "code": "v1 = req.body['x']\nv2 = step1(v1)\nv3 = step2(v2)\nv4 = step3(v3)\nv5 = step4(v4)",
        "ext": ".py",
        "expected": "ACCEPT"
    },
    {
        "name": "F — Multi-source JS (expect REJECT for email)",
        "code": """const express = require('express');
const app = express();

app.get('/user', (req, res) => {
    const userId = req.params.id;
    const email = req.query.email;
    const safeName = sanitize_input(userId);
    console.log(email);
    res.json({ id: safeName });
});""",
        "ext": ".js",
        "expected": "REJECT"
    },
]

# ── INFERENCE ────────────────────────────────────────────────────────────────

def call_model(model: str, prompt: str, system: str, timeout: int = 60) -> tuple:
    """Call Ollama directly. Returns (raw_output, elapsed_seconds)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {"temperature": 0.1}
    }
    t = time.perf_counter()
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        return content, time.perf_counter() - t
    except requests.exceptions.Timeout:
        return "TIMEOUT", time.perf_counter() - t
    except Exception as e:
        return f"ERROR: {e}", time.perf_counter() - t

# ── BENCHMARK ────────────────────────────────────────────────────────────────

def run_model_benchmark(model: str) -> dict:
    results = {}
    for test in TEST_CASES:
        prompt = build_prompt(
            system_rules="",
            user_command=test["code"],
            file_extension=test["ext"]
        )
        runs = []
        for run in range(1, RUNS + 1):
            raw, elapsed = call_model(model, prompt, STRUCTURAL_INTEGRITY_SYSTEM)
            if raw in ("TIMEOUT", ) or raw.startswith("ERROR"):
                verdict = raw
                correct = False
            else:
                parsed = guillotine_parser(raw, user_command=test["code"])
                verdict = parsed["verdict"]
                correct = verdict == test["expected"]
            runs.append({"run": run, "verdict": verdict, "time": elapsed, "correct": correct})
            status = "✅" if correct else "❌"
            print(f"  [{model}] {test['name']} | Run {run}: {verdict} {status} | {elapsed:.1f}s")
        results[test["name"]] = {
            "expected": test["expected"],
            "runs": runs,
            "correct_count": sum(1 for r in runs if r["correct"]),
            "avg_time": sum(r["time"] for r in runs) / len(runs)
        }
    return results

# ── REPORT ───────────────────────────────────────────────────────────────────

def print_report(model: str, results: dict):
    print(f"\n{'='*60}")
    print(f"MODEL: {model}")
    print(f"{'='*60}")
    total_correct = 0
    total_runs = 0
    for name, data in results.items():
        c = data["correct_count"]
        t = data["avg_time"]
        status = "✅" if c == RUNS else ("⚠️" if c > 0 else "❌")
        print(f"{status} {name}")
        print(f"   Accuracy: {c}/{RUNS} | Avg: {t:.1f}s")
        total_correct += c
        total_runs += RUNS
    pct = 100 * total_correct // total_runs
    print(f"\nOVERALL: {total_correct}/{total_runs} ({pct}%)")
    print(f"{'='*60}")

def print_head_to_head(llama_r: dict, qwen_r: dict):
    print(f"\n{'='*60}")
    print("HEAD TO HEAD SUMMARY")
    print(f"{'='*60}")
    print(f"{'Scenario':<42} {'Llama 3.1:8b':>12} {'Qwen2.5-coder:7b':>16}")
    print("-" * 72)
    for name in llama_r:
        l = llama_r[name]
        q = qwen_r[name]
        l_str = f"{l['correct_count']}/3 @ {l['avg_time']:.1f}s"
        q_str = f"{q['correct_count']}/3 @ {q['avg_time']:.1f}s"
        winner = "⬅" if l['correct_count'] > q['correct_count'] else ("➡" if q['correct_count'] > l['correct_count'] else "=")
        print(f"{name[:41]:<42} {l_str:>12} {q_str:>16} {winner}")
    print(f"{'='*60}")

# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🏁 TREPAN STAGE 1 MODEL BENCHMARK")
    print(f"6 scenarios × {RUNS} runs each × 2 models = {6*RUNS*2} total inference calls")
    print("This will take approximately 10-15 minutes. Do not interrupt.\n")

    print("─── ROUND 1: llama3.1:8b ───\n")
    llama_results = run_model_benchmark("llama3.1:8b")
    print_report("llama3.1:8b", llama_results)

    print("\n─── ROUND 2: qwen2.5-coder:7b ───\n")
    qwen_results = run_model_benchmark("qwen2.5-coder:7b")
    print_report("qwen2.5-coder:7b", qwen_results)

    print_head_to_head(llama_results, qwen_results)

    print("\n✅ Benchmark complete. Paste full output for review.")
