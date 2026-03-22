"""
trepan_benchmark.py

Head-to-head benchmark: Qwen 2.5:3B vs Llama 3.1:8B
Tests accuracy, speed, and schema compliance across 10 scenarios.

Run with: python trepan_benchmark.py
"""

import requests
import time
import json
import statistics

SERVER_URL = "http://127.0.0.1:8001"

MODELS = {
    "qwen2.5:3b": "⚡⚡ Turbo (Qwen)",
    "llama3.1:8b": "⚡ Fast (Llama)"
}

TEST_CASES = [
    # ── FALSE POSITIVE CHECKS (should all ACCEPT) ─────────────────────
    {
        "id": "A1",
        "name": "Literal string to print",
        "code": 'name = "John Doe"\nprint(name)',
        "ext": ".py",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },
    {
        "id": "A2",
        "name": "Sanitized with redact",
        "code": "name = req.body['name']\nsafe = redact(name)\nprint(safe)",
        "ext": ".py",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },
    {
        "id": "A3",
        "name": "Hashlib safe transformation",
        "code": "password = req.body['password']\nhashed = hashlib.sha256(password.encode()).hexdigest()\nstore(hashed)",
        "ext": ".py",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },
    {
        "id": "A4",
        "name": "Secure logger JS",
        "code": "const patientId = req.params.id;\nsecureLogger.info(patientId);",
        "ext": ".js",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },
    {
        "id": "A5",
        "name": "Static string console.log",
        "code": 'console.log("Server started on port 3000")',
        "ext": ".js",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },
    {
        "id": "A6",
        "name": "Depth limit exceeded — untraceable",
        "code": "v1 = req.body['x']\nv2 = step1(v1)\nv3 = step2(v2)\nv4 = step3(v3)\nv5 = step4(v4)",
        "ext": ".py",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },
    {
        "id": "A7",
        "name": "bcrypt hash safe",
        "code": "pw = req.body['password']\nhashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt())\ndb.save(hashed)",
        "ext": ".py",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },
    {
        "id": "A8",
        "name": "Internal constant to logger",
        "code": 'status = "active"\nlogger.info(f"Status: {status}")',
        "ext": ".py",
        "expected": "ACCEPT",
        "category": "FALSE POSITIVE"
    },

    # ── VIOLATION DETECTION (should all REJECT) ───────────────────────
    {
        "id": "R1",
        "name": "Request body to print",
        "code": "name = req.body['name']\nprint(name)",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R2",
        "name": "DB record to console.log JS",
        "code": "const record = db.getPatient(id);\nconsole.log(record);",
        "ext": ".js",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R3",
        "name": "Password to print in f-string",
        "code": "password = request.json.get('password')\nprint(f'Login attempt: {password}')",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R4",
        "name": "Request query to res.json",
        "code": "const userInput = req.query.search;\nres.json({ result: userInput });",
        "ext": ".js",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R5",
        "name": "Multi-hop data flow",
        "code": "raw = request.args.get('data')\nprocessed = raw.strip()\nprint(processed)",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R6",
        "name": "Email from request to logger",
        "code": "email = request.form.get('email')\nlogger.info(f'User email: {email}')",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R7",
        "name": "User ID to console.error",
        "code": "const userId = req.body.userId;\nconsole.error('Failed for user:', userId);",
        "ext": ".js",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R8",
        "name": "SSN direct assignment to print",
        "code": "ssn = patient['ssn']\nprint(ssn)",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R9",
        "name": "Request header leaked",
        "code": "token = request.headers.get('Authorization')\nprint(f'Token: {token}')",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R10",
        "name": "JSON body to res.send",
        "code": "const payload = req.body;\nres.send(payload);",
        "ext": ".js",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R11",
        "name": "Env variable secret logged",
        "code": "secret = os.environ.get('SECRET_KEY')\nprint(f'Using secret: {secret}')",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
    {
        "id": "R12",
        "name": "DB query result to response",
        "code": "user_data = db.execute('SELECT * FROM users WHERE id = ?', [uid]).fetchone()\nreturn jsonify(user_data)",
        "ext": ".py",
        "expected": "REJECT",
        "category": "VIOLATION"
    },
]

RUNS_PER_TEST = 3

def run_audit(code: str, filename: str, model: str) -> dict:
    payload = {
        "filename": filename,
        "code_snippet": code,
        "pillars": {
            "system_rules": "",
            "golden_state": "",
            "done_tasks": "",
            "pending_tasks": "",
            "history_phases": ""
        },
        "project_path": "",
        "processor_mode": "GPU",
        "model_name": model
    }
    t = time.perf_counter()
    try:
        resp = requests.post(f"{SERVER_URL}/evaluate", json=payload, timeout=120)
        elapsed = time.perf_counter() - t
        if resp.status_code == 200:
            data = resp.json()
            return {
                "verdict": data.get("action", "UNKNOWN"),
                "elapsed": elapsed,
                "raw_output": data.get("raw_output", ""),
                "error": None
            }
        else:
            return {"verdict": "ERROR", "elapsed": time.perf_counter() - t, "error": resp.text}
    except Exception as e:
        return {"verdict": "ERROR", "elapsed": time.perf_counter() - t, "error": str(e)}

def get_layer(raw_output: str) -> str:
    if "LAYER 1" in raw_output:
        return "L1"
    elif "LAYER 2" in raw_output:
        return "L2"
    elif raw_output == "":
        return "V1"
    return "V1"

def run_benchmark():
    print("\n" + "="*70)
    print("TREPAN MODEL BENCHMARK — Qwen 2.5:3B vs Llama 3.1:8B")
    print("="*70)
    print(f"Tests: {len(TEST_CASES)} | Runs per test: {RUNS_PER_TEST} | Total calls: {len(TEST_CASES) * RUNS_PER_TEST * 2}")
    print()

    # Warmup
    print("Warming up both models...")
    for model in MODELS:
        run_audit('x = 1', 'warmup.py', model)
    print("Warmup done.\n")

    results = {model: [] for model in MODELS}

    for test in TEST_CASES:
        print(f"[{test['id']}] {test['name']} ({test['category']}) — expected: {test['expected']}")
        for model, label in MODELS.items():
            run_verdicts = []
            run_times = []
            run_layers = []

            for run in range(1, RUNS_PER_TEST + 1):
                r = run_audit(test["code"], f"bench_{test['id']}.{test['ext'].strip('.')}", model)
                run_verdicts.append(r["verdict"])
                run_times.append(r["elapsed"])
                run_layers.append(get_layer(r.get("raw_output", "")))

            # Majority verdict across runs
            reject_count = run_verdicts.count("REJECT")
            accept_count = run_verdicts.count("ACCEPT")
            majority_verdict = "REJECT" if reject_count >= 2 else "ACCEPT"
            correct = majority_verdict == test["expected"]
            avg_time = statistics.mean(run_times)
            dominant_layer = max(set(run_layers), key=run_layers.count)

            status = "✅" if correct else "❌"
            print(f"  {label:25s} | {majority_verdict:6s} {status} | avg {avg_time:.2f}s | layer: {dominant_layer} | runs: {'/'.join(run_verdicts)}")

            results[model].append({
                "test_id": test["id"],
                "expected": test["expected"],
                "verdict": majority_verdict,
                "correct": correct,
                "avg_time": avg_time,
                "layer": dominant_layer,
                "category": test["category"]
            })
        print()

    # ── Final Report ────────────────────────────────────────────────────
    print("="*70)
    print("FINAL RESULTS")
    print("="*70)
    print(f"\n{'Metric':<35} {'Qwen 2.5:3B':>15} {'Llama 3.1:8B':>15}")
    print("-"*65)

    for model, label in MODELS.items():
        r = results[model]
        total = len(r)
        correct = sum(1 for x in r if x["correct"])
        accuracy = 100 * correct / total

        fp_tests = [x for x in r if x["expected"] == "ACCEPT"]
        tp_tests = [x for x in r if x["expected"] == "REJECT"]
        fp_accuracy = 100 * sum(1 for x in fp_tests if x["correct"]) / len(fp_tests)
        tp_accuracy = 100 * sum(1 for x in tp_tests if x["correct"]) / len(tp_tests)

        avg_time = statistics.mean(x["avg_time"] for x in r)
        l1_hits = sum(1 for x in r if x["layer"] == "L1")
        l2_hits = sum(1 for x in r if x["layer"] == "L2")

        results[model + "_summary"] = {
            "accuracy": accuracy,
            "fp_accuracy": fp_accuracy,
            "tp_accuracy": tp_accuracy,
            "avg_time": avg_time,
            "l1_hits": l1_hits,
            "l2_hits": l2_hits
        }

    q = results["qwen2.5:3b_summary"]
    l = results["llama3.1:8b_summary"]

    print(f"{'Overall accuracy':<35} {q['accuracy']:>14.0f}% {l['accuracy']:>14.0f}%")
    print(f"{'False positive accuracy (ACCEPT)':<35} {q['fp_accuracy']:>14.0f}% {l['fp_accuracy']:>14.0f}%")
    print(f"{'Violation detection (REJECT)':<35} {q['tp_accuracy']:>14.0f}% {l['tp_accuracy']:>14.0f}%")
    print(f"{'Average audit time':<35} {q['avg_time']:>13.2f}s {l['avg_time']:>13.2f}s")
    print(f"{'Layer 1 catches (no model needed)':<35} {q['l1_hits']:>15} {l['l1_hits']:>15}")
    print(f"{'Layer 2 catches (focused model)':<35} {q['l2_hits']:>15} {l['l2_hits']:>15}")

    print("\n" + "="*70)
    print("WINNER")
    print("="*70)

    q_score = 0
    l_score = 0

    if q["accuracy"] > l["accuracy"]: q_score += 2
    elif l["accuracy"] > q["accuracy"]: l_score += 2
    else: q_score += 1; l_score += 1

    if q["avg_time"] < l["avg_time"]: q_score += 2
    elif l["avg_time"] < q["avg_time"]: l_score += 2
    else: q_score += 1; l_score += 1

    if q["tp_accuracy"] > l["tp_accuracy"]: q_score += 2
    elif l["tp_accuracy"] > q["tp_accuracy"]: l_score += 2
    else: q_score += 1; l_score += 1

    if q["fp_accuracy"] > l["fp_accuracy"]: q_score += 1
    elif l["fp_accuracy"] > q["fp_accuracy"]: l_score += 1
    else: q_score += 1; l_score += 1

    print(f"\n  Qwen 2.5:3B   score: {q_score}/7")
    print(f"  Llama 3.1:8B  score: {l_score}/7")

    if q_score > l_score:
        print(f"\n  🏆 WINNER: Qwen 2.5:3B — faster and/or more accurate")
        print(f"  Recommendation: Switch default model to qwen2.5:3b")
    elif l_score > q_score:
        print(f"\n  🏆 WINNER: Llama 3.1:8B — faster and/or more accurate")
        print(f"  Recommendation: Keep llama3.1:8b as default")
    else:
        print(f"\n  🤝 TIE — both models perform similarly")
        print(f"  Recommendation: Keep Llama (more widely tested)")

    print("\n" + "="*70)

if __name__ == "__main__":
    run_benchmark()
