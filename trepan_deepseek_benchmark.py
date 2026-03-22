import sys
import time
import re
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
MODELS = ["llama3.1:8b", "deepseek-r1:7b"]
RUNS = 3

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

def strip_think_block(raw: str) -> str:
    """
    DeepSeek-R1 outputs <think>...</think> before its answer.
    Strip it so the JSON parser can find the actual response.
    """
    stripped = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    return stripped.strip()

def call_model(model: str, prompt: str, system: str, timeout: int = 120) -> tuple:
    """Call Ollama directly. Returns (raw_output, elapsed_seconds)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_gpu": 999,
            "num_thread": 4,
            "low_vram": False
        }
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

            if raw in ("TIMEOUT",) or raw.startswith("ERROR"):
                verdict = raw
                correct = False
                think_len = 0
            else:
                # Strip DeepSeek thinking block before parsing
                clean = strip_think_block(raw)
                think_len = len(raw) - len(clean)
                parsed = guillotine_parser(clean, user_command=test["code"])
                verdict = parsed["verdict"]
                correct = verdict == test["expected"]

            runs.append({
                "run": run,
                "verdict": verdict,
                "time": elapsed,
                "correct": correct,
                "think_chars": think_len
            })

            status = "✅" if correct else "❌"
            think_note = f" [think: {think_len} chars]" if think_len > 0 else ""
            print(f"  [{model}] {test['name']} | Run {run}: {verdict} {status} | {elapsed:.1f}s{think_note}")

        results[test["name"]] = {
            "expected": test["expected"],
            "runs": runs,
            "correct_count": sum(1 for r in runs if r["correct"]),
            "avg_time": sum(r["time"] for r in runs) / len(runs),
            "avg_think": sum(r["think_chars"] for r in runs) / len(runs)
        }
    return results

def print_report(model: str, results: dict):
    print(f"\n{'='*60}")
    print(f"MODEL: {model}")
    print(f"{'='*60}")
    total_correct = 0
    total_runs = 0
    for name, data in results.items():
        c = data["correct_count"]
        t = data["avg_time"]
        think = data.get("avg_think", 0)
        status = "✅" if c == RUNS else ("⚠️" if c > 0 else "❌")
        think_note = f" | avg think: {int(think)} chars" if think > 0 else ""
        print(f"{status} {name}")
        print(f"   Accuracy: {c}/{RUNS} | Avg: {t:.1f}s{think_note}")
        total_correct += c
        total_runs += RUNS
    pct = 100 * total_correct // total_runs
    print(f"\nOVERALL: {total_correct}/{total_runs} ({pct}%)")
    print(f"{'='*60}")

def print_head_to_head(r1: dict, r2: dict, name1: str, name2: str):
    print(f"\n{'='*60}")
    print("HEAD TO HEAD")
    print(f"{'='*60}")
    print(f"{'Scenario':<42} {name1:>12} {name2:>16}")
    print("-" * 72)
    for name in r1:
        a = r1[name]
        b = r2[name]
        a_str = f"{a['correct_count']}/3 @ {a['avg_time']:.1f}s"
        b_str = f"{b['correct_count']}/3 @ {b['avg_time']:.1f}s"
        if a["correct_count"] > b["correct_count"]:
            winner = "⬅"
        elif b["correct_count"] > a["correct_count"]:
            winner = "➡"
        else:
            winner = "="
        print(f"{name[:41]:<42} {a_str:>12} {b_str:>16} {winner}")
    print(f"{'='*60}")

if __name__ == "__main__":
    print("\n?? TREPAN DEEPSEEK-R1 BENCHMARK")
    print(f"6 scenarios ? {RUNS} runs ? 1 model = {6*RUNS*1} total calls")
    print("Estimated time: 15-25 minutes. Do not interrupt.\n")

    print("Warming up GPU ? loading model into VRAM...")
    warmup_raw, warmup_time = call_model("deepseek-r1:7b", "Say READY.", STRUCTURAL_INTEGRITY_SYSTEM)
    print(f"Warmup complete in {warmup_time:.1f}s. GPU should now be hot.\n")

    print("??? deepseek-r1:7b ???\n")
    ds_results = run_model_benchmark("deepseek-r1:7b")
    print_report("deepseek-r1:7b", ds_results)

    print("\n? Benchmark complete. Paste full output for review.")
