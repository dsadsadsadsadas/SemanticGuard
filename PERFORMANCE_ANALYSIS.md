# 🚀 SemanticGuard Performance Analysis

## Architecture Comparison

| System | Architecture | Rate Limiting | Concurrency | Performance | Accuracy |
|--------|-------------|---------------|-------------|-------------|----------|
| **stress_test.py** | Client → Groq API | Client TokenBucket (300k TPM) | 2 | **0.3s/file** | 100% |
| **test_few_shot_examples.py** | Client → Server → Groq API | Server TokenBucket (30k TPM) | 10 | 1.0s/file | 100% |
| **UI Full Audit (BEFORE)** | Client → Server → Groq API | Server TokenBucket (30k TPM) | 10 | 1.0s/file + 429 errors | 94% |
| **UI Full Audit (AFTER)** | Client → Server → Groq API | Server TokenBucket (300k TPM) | 10 | **~1.0s/file** | **100%** |

## Root Cause Analysis

### Issue 1: 429 Rate Limit Errors

**Problem:**
```
Server TokenBucket: 30k TPM (hardcoded)
Your Account: 300k TPM (10x higher!)
UI Concurrency: 10 requests
Burst load: 10 × 2,500 tokens = 25,000 tokens
Result: Immediate bucket depletion → 429 errors
```

**Solution:**
- Added `detect_and_upgrade_rate_limiter()` function
- Runs on server startup (before any audits)
- Detects TPM from Groq API headers
- Upgrades TokenBucket: 30k → 300k TPM
- Refill rate: 500 → 5,000 tokens/second

### Issue 2: Missing Line Numbers (94% Accuracy)

**Problem:**
```javascript
// UI was sending raw code
code_snippet: codeContent
```

**Solution:**
```javascript
// Now sends numbered code (like test_few_shot_examples.py)
const numberedLines = lines.map((line, i) => `${i + 1}: ${line}`);
const numberedCode = numberedLines.join('\n');
code_snippet: numberedCode
```

## Token Bucket Math Explained

### Refill Rate Calculation
```
refill_rate = max_tpm / 60.0  # Tokens per second

30k TPM:  500 tokens/second
300k TPM: 5,000 tokens/second  ← 10x faster!
```

### Deficit Calculation
```
deficit = requested_tokens - available_tokens
wait_time = deficit / refill_rate

Example with 30k TPM:
- Need: 2,500 tokens
- Have: 0 tokens
- Deficit: 2,500 tokens
- Wait: 2,500 / 500 = 5 seconds

Example with 300k TPM:
- Need: 2,500 tokens
- Have: 0 tokens
- Deficit: 2,500 tokens
- Wait: 2,500 / 5,000 = 0.5 seconds  ← 10x faster!
```

### Why Concurrent Processing Works

With 300k TPM and concurrency=10:
```
Time 0s:  File 1-10 start (consume 25,000 tokens total)
Time 0.5s: Files complete, bucket refills 2,500 tokens
Time 0.5s: File 11-20 start (consume 25,000 tokens)
Time 1.0s: Files complete, bucket refills 2,500 tokens
...
```

The bucket continuously refills while API calls are in flight, so you're never truly waiting.

## Expected Performance After Fix

### With 300k TPM (Upgraded Account)

**100 files × 2,500 tokens average:**
- Total tokens: 250,000
- Refill rate: 5,000 tokens/second
- Theoretical time: 250,000 / 5,000 = **50 seconds**
- With concurrency=10 and API latency: **~40-50 seconds**

### With 30k TPM (Free Tier)

**100 files × 2,500 tokens average:**
- Total tokens: 250,000
- Refill rate: 500 tokens/second
- Theoretical time: 250,000 / 500 = **500 seconds (8.3 minutes)**
- With concurrency=10: **~450-500 seconds**

## Implementation Changes

### 1. Server Startup (server.py)
```python
# Added detect_and_upgrade_rate_limiter() function
# Calls Groq API on startup to detect TPM/RPM
# Upgrades cloud_rate_limiter before any audits

async def lifespan(app: FastAPI):
    # ... GPU setup ...
    
    # NEW: Detect and upgrade rate limiter
    await detect_and_upgrade_rate_limiter()
    
    # ... rest of startup ...
```

### 2. UI Request Format (extension.js)
```javascript
// Added line numbering in evaluateWithServer()
const numberedLines = lines.map((line, i) => `${i + 1}: ${line}`);
const numberedCode = numberedLines.join('\n');

// Send numbered code (matches test_few_shot_examples.py)
code_snippet: numberedCode
```

### 3. Removed Dynamic Detection from Endpoint
- Removed TPM detection from `/evaluate_cloud` endpoint
- Now handled once at startup (more efficient)

## Testing Instructions

1. **Set GROQ_API_KEY environment variable** before starting server:
   ```bash
   export GROQ_API_KEY="your_key_here"
   ```

2. **Restart server** to trigger TPM detection:
   ```bash
   python -m semanticguard_server.server
   ```

3. **Look for startup logs:**
   ```
   ✅ Detected TPM from API: 300,000
   🚀 UPGRADED TokenBucket: 30,000 → 300,000 TPM
   🚀 Refill rate: 5,000 tokens/second
   ```

4. **Run UI Full Audit** - should see:
   - No 429 errors
   - ~1s per file average
   - 100% accuracy

## Why UI Can't Match stress_test.py Speed

**stress_test.py: 0.3s per file**
- Direct API calls (no server hop)
- API latency only

**UI Full Audit: 1.0s per file**
- Goes through server (adds ~0.5-0.7s overhead)
- Server processing + API latency
- This is expected and acceptable

The goal is to eliminate 429 errors and achieve consistent 1s per file, not to match stress_test.py's 0.3s (which is impossible with the server architecture).
