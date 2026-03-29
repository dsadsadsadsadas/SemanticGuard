# Rate Limiting Pipeline Audit

## Executive Summary

**Problem**: Full Audit mode is still experiencing 429 errors and 30-second waits despite detecting 300K TPM from Groq API.

**Root Cause**: The `/update_rate_limits` endpoint is being called, but the server's `cloud_rate_limiter` is NOT being upgraded properly OR the upgrade is happening AFTER files have already started processing.

---

## Pipeline Comparison: stress_test.py vs Full Audit

### stress_test.py (WORKING - No 429 errors)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Detect TPM/RPM from Groq API                             │
│    └─> detect_model_limits(api_key, model_name)            │
│        └─> Returns: (max_rpm, max_tpm)                     │
│            Example: (500000, 300000)                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Initialize TokenBucket with detected limits              │
│    └─> rate_limiter = TokenBucket(                         │
│            max_rpm=detected_rpm,                            │
│            max_tpm=detected_tpm                             │
│        )                                                    │
│    └─> TokenBucket state:                                  │
│        • max_tpm: 300,000                                   │
│        • tokens: 300,000 (full capacity)                    │
│        • refill_rate: 5,000 tokens/second                   │
│        • max_file_tokens: 60,000 (20% of TPM)               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Process files with CLIENT-SIDE rate limiting             │
│    └─> For each file:                                      │
│        1. Estimate tokens                                   │
│        2. await rate_limiter.consume_with_wait(tokens)      │
│        3. Make Groq API call                                │
│        4. Refund unused tokens                              │
│                                                             │
│    └─> Concurrency: 2 files at a time                      │
│    └─> Rate limiting: CLIENT controls the pace             │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    ✅ RESULT: 0.3s/file
                    ✅ No 429 errors
                    ✅ 100% success rate
```

---

### Full Audit (BROKEN - 429 errors + 30s waits)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Server starts with DEFAULT limits                        │
│    └─> cloud_rate_limiter = TokenBucket(                   │
│            max_rpm=30,                                      │
│            max_tpm=30000                                    │
│        )                                                    │
│    └─> TokenBucket state:                                  │
│        • max_tpm: 30,000 ❌                                 │
│        • tokens: 30,000                                     │
│        • refill_rate: 500 tokens/second                     │
│        • max_file_tokens: 6,000 (20% of TPM)                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. UI detects TPM/RPM from Groq API                         │
│    └─> detectModelLimits(apiKey, cloudModelName)           │
│        └─> Returns: { maxRpm: 500000, maxTpm: 300000 }     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. UI sends upgrade request to server                       │
│    └─> POST /update_rate_limits                            │
│        Body: { max_tpm: 300000, max_rpm: 500000 }          │
│                                                             │
│    ⚠️ CRITICAL TIMING ISSUE:                                │
│    This happens CONCURRENTLY with file processing!          │
│    Files may already be queued with 30K TPM limits!         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Server upgrades TokenBucket (MAYBE TOO LATE)             │
│    └─> if req.max_tpm > cloud_rate_limiter.max_tpm:        │
│            cloud_rate_limiter.max_tpm = 300000              │
│            cloud_rate_limiter.tokens = 300000               │
│            cloud_rate_limiter.refill_rate = 5000            │
│                                                             │
│    ⚠️ BUT: Files already in flight use OLD limits!          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Process files with SERVER-SIDE rate limiting             │
│    └─> For each file:                                      │
│        1. UI sends file to /evaluate_cloud                  │
│        2. Server: await cloud_rate_limiter.consume(tokens)  │
│        3. Server: Make Groq API call                        │
│        4. Server: Refund unused tokens                      │
│                                                             │
│    └─> Concurrency: 10 files at a time ❌                   │
│    └─> Rate limiting: SERVER controls the pace              │
│    └─> Problem: 10 concurrent requests × 2,588 tokens       │
│                 = 25,880 tokens needed immediately          │
│                 BUT: TokenBucket only has 30,000 tokens     │
│                 AND: Refill rate is only 500 tokens/sec     │
└─────────────────────────────────────────────────────────────┘
                            ↓
                    ❌ RESULT: 1.0s/file + 30s waits
                    ❌ 429 errors
                    ❌ 94% success rate
```

---

## Key Differences

| Aspect | stress_test.py | Full Audit |
|--------|----------------|------------|
| **Rate Limiter Location** | Client-side (Python script) | Server-side (FastAPI) |
| **TPM Detection** | Before TokenBucket init | After server starts |
| **TokenBucket Init** | With detected limits (300K) | With defaults (30K) |
| **Upgrade Timing** | N/A (initialized correctly) | During file processing ⚠️ |
| **Concurrency** | 2 files | 10 files ⚠️ |
| **Token Burst** | 2 × ~2,500 = 5,000 tokens | 10 × ~2,500 = 25,000 tokens ⚠️ |
| **Refill Rate** | 5,000 tokens/sec | 500 tokens/sec (initially) ⚠️ |
| **429 Errors** | 0 | Multiple |
| **Performance** | 0.3s/file | 1.0s/file + waits |

---

## Root Cause Analysis

### Problem 1: Race Condition
The `/update_rate_limits` call happens CONCURRENTLY with file processing:

```javascript
// extension/extension.js line 940-970
// ═══ DETECT TPM/RPM ═══
const limits = await detectModelLimits(apiKey, cloudModelName);
detectedTPM = limits.maxTpm;
detectedRPM = limits.maxRpm;

// ═══ UPGRADE SERVER ═══
const updateResponse = await fetchWithTimeout(`${serverUrl}/update_rate_limits`, {
    method: 'POST',
    body: JSON.stringify({ max_tpm: detectedTPM, max_rpm: detectedRPM })
}, 10000);

// ⚠️ PROBLEM: File processing starts immediately after this
// Files may already be queued before upgrade completes!
```

### Problem 2: High Concurrency Burst
Full Audit uses 10 concurrent requests, which requires:
- **Immediate burst**: 10 × 2,500 tokens = 25,000 tokens
- **With 30K TPM**: Only 5,000 tokens left after first burst
- **Refill rate (30K)**: 500 tokens/second = 5 seconds to refill 2,500 tokens
- **Result**: Requests wait 5-30 seconds for tokens

### Problem 3: Server-Side Rate Limiting
- stress_test.py: Client controls pacing (can see token availability)
- Full Audit: Server controls pacing (client blindly sends 10 requests)
- **Result**: Server gets overwhelmed, triggers 429 errors

---

## Evidence from Logs

```
2026-03-26 19:06:30,108 [INFO] Rate limiting: Waited 29.82s for 2,588 tokens
2026-03-26 19:06:30,108 [WARNING] Request woke up but global pause is active. Sleeping for 29.82s
2026-03-26 19:06:30,233 [WARNING] 429 Rate Limit! Global pause 30s, retry 1/3
```

**Analysis**:
1. Request waited 29.82s for 2,588 tokens → TokenBucket was nearly empty
2. Global pause active → Previous request triggered 429 error
3. Multiple 429 errors → Server is hitting Groq's actual rate limits

**Conclusion**: The TokenBucket is NOT upgraded to 300K TPM before files start processing.

---

## Verification Steps

### Step 1: Check if upgrade is called
Look for this log in the server:
```
🚀 UPGRADED TokenBucket: 30,000 → 300,000 TPM
🚀 Refill rate: 5,000 tokens/second
🚀 Current tokens topped up: 300,000
```

**If NOT present**: The `/update_rate_limits` endpoint is not being called or is failing silently.

**If present**: Check the timestamp - is it BEFORE or AFTER file processing starts?

### Step 2: Check extension console
Look for this log:
```
[SEMANTICGUARD FOLDER AUDIT] ✅ Server TokenBucket upgraded: 30,000 → 300,000 TPM
[SEMANTICGUARD FOLDER AUDIT] ✅ Refill rate: 5000 tokens/second
```

**If NOT present**: The upgrade request failed or timed out.

### Step 3: Check timing
Compare timestamps:
- When did `/update_rate_limits` complete?
- When did first `/evaluate_cloud` request arrive?

**If evaluate_cloud arrives BEFORE update_rate_limits completes**: Race condition confirmed.

---

## Recommended Fixes (DO NOT IMPLEMENT YET)

### Option 1: Strict Async Barrier (RECOMMENDED)
```javascript
// Wait for upgrade to complete BEFORE starting file processing
await fetchWithTimeout(`${serverUrl}/update_rate_limits`, ...);
// ← ADD VERIFICATION HERE: Check response.ok
// ← ADD DELAY: await new Promise(resolve => setTimeout(resolve, 1000));
// THEN start processing files
```

### Option 2: Reduce Concurrency
```javascript
const CONCURRENCY_LIMIT = 2;  // Match stress_test.py
```

### Option 3: Client-Side Rate Limiting
Move TokenBucket to client (like stress_test.py):
- Detect limits in UI
- Create TokenBucket in extension.js
- Control pacing before sending to server

---

## Next Steps

1. **Check server logs** for upgrade confirmation
2. **Check extension console** for upgrade response
3. **Compare timestamps** to confirm race condition
4. **Decide on fix strategy** based on findings

---

## Performance Target

After fix, Full Audit should match stress_test.py:
- **0.3-0.5s per file** (accounting for server overhead)
- **0 rate limit errors**
- **100% success rate**
- **No artificial waits**
