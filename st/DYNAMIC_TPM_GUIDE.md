# 🚀 Dynamic TPM Detection Guide

## What Changed?

The stress test now **automatically detects** your API's TPM (Tokens Per Minute) limits by querying the Groq API headers, then adapts file size limits accordingly.

---

## ✨ New Features

### 1. Automatic TPM Detection from API

When you select a model, the script now:
1. Makes a test API call to Groq
2. Reads the rate limit headers (`x-ratelimit-limit-tokens`)
3. Automatically detects your account's TPM limits
4. Compares detected limits with defaults
5. Uses the higher limit if your account is upgraded

**Example:**
```
Selected: Llama 4 Scout 17B
Default limits: Max RPM: 30 | Max TPM: 30,000

🔍 Detecting model limits from Groq API...
✅ Detected from API: Max RPM: 30 | Max TPM: 500,000

🎉 UPGRADED LIMITS DETECTED!
   Your account has: Max RPM: 30 | Max TPM: 500,000

Use detected limits? [Y/n]: y
✅ Using detected limits: 500,000 TPM
```

### 2. Fallback to Manual Entry

If API detection fails (network issues, API changes, etc.), you can still manually enter TPM:

```
⚠️  Could not detect limits from API headers

⚠️  Automatic detection failed. Please enter limits manually:
Enter Max TPM (tokens per minute, e.g., 500000): 500000
```

### 3. Custom Model Option (Option 3)

For non-Groq models or custom endpoints:

```
📊 Available Models:
  1. Llama 3.3 70B Versatile
  2. Llama 4 Scout 17B
  3. Custom Model (Manual TPM Entry)

Select model (1, 2, or 3): 3
```

The script now calculates `max_file_tokens` based on your TPM:

| Your TPM | Max File Size | Formula |
|----------|---------------|---------|
| 12,000 | 2,400 tokens | 20% of TPM |
| 30,000 | 6,000 tokens | 20% of TPM |
| 500,000 | **100,000 tokens** | 20% of TPM (capped at 100k) |

**Formula:** `min(TPM * 0.2, 100000)`

This means:
- **500k TPM model**: Can audit files up to **100k tokens** (~400KB of code)
- **30k TPM model**: Can audit files up to **6k tokens** (~24KB of code)
- **12k TPM model**: Can audit files up to **2.4k tokens** (~10KB of code)

---

## 📊 Example Output

When you start the audit with 500k TPM:

```
🚀 Starting audit...
Model: your-model-name | Max RPM: 30 | Max TPM: 500,000
Max File Size: 100,000 tokens (20% of TPM capacity)
```

If a file is too large:

```
[12:34:56.789] [5/150] [SKIPPED] large_file.py is too large (120,000 tokens > 100,000 limit)
```

---

## 🔧 How It Works

### Token Bucket Algorithm

The `TokenBucket` class now dynamically sets `max_file_tokens`:

```python
# Dynamic max_file_tokens based on TPM
# For 500k TPM: allow up to 100k tokens per file (20% of capacity)
# For 30k TPM: allow up to 6k tokens per file (20% of capacity)
# Formula: min(TPM * 0.2, 100000) to cap at 100k for very high TPM
self.max_file_tokens = min(int(max_tpm * 0.2), 100000)
```

### Rate Limiting

The script still enforces:
- **Token-aware rate limiting**: Waits based on token consumption
- **Global pause on 429 errors**: All tasks sleep 30s if rate limited
- **Refund mechanism**: Returns unused tokens if estimate was too high

---

## 🎯 Use Cases

### Scenario 1: Free Tier (Auto-Detected)
```bash
$ python stress_test.py
Select model (1, 2, or 3): 2  # Llama 4 Scout 17B

Selected: Llama 4 Scout 17B
Default limits: Max RPM: 30 | Max TPM: 30,000

🔍 Detecting model limits from Groq API...
✅ Detected from API: Max RPM: 30 | Max TPM: 30,000

Using default limits: 30,000 TPM
# Result: Max file size = 6,000 tokens
```

### Scenario 2: Pro Tier (Auto-Detected - YOUR CASE!)
```bash
$ python stress_test.py
Select model (1, 2, or 3): 2  # Llama 4 Scout 17B

Selected: Llama 4 Scout 17B
Default limits: Max RPM: 30 | Max TPM: 30,000

🔍 Detecting model limits from Groq API...
✅ Detected from API: Max RPM: 30 | Max TPM: 500,000

🎉 UPGRADED LIMITS DETECTED!
   Your account has: Max RPM: 30 | Max TPM: 500,000

Use detected limits? [Y/n]: y
✅ Using detected limits: 500,000 TPM

# Result: Max file size = 100,000 tokens
```

### Scenario 3: Custom Model (Manual Entry)
```bash
$ python stress_test.py
Select model (1, 2, or 3): 3  # Custom Model

Enter model name: your-enterprise-model
🔍 Detecting model limits from Groq API...
⚠️  Could not detect limits from API headers

Enter Max TPM: 1000000
Enter Max RPM: 60

# Result: Max file size = 100,000 tokens (capped)
```

---

## 📈 Benefits

✅ **No more hardcoded 22k limits**  
✅ **Adapts to your API tier automatically**  
✅ **Audits larger files with high TPM models**  
✅ **Prevents wasted API calls on oversized files**  
✅ **Optimized rate limiting based on actual TPM**

---

## 🚨 Important Notes

1. **20% Rule**: The script reserves 20% of your TPM for a single file to prevent one large file from blocking the entire queue.

2. **100k Token Cap**: Even with 1M TPM, files are capped at 100k tokens (~400KB) to prevent extremely long API calls.

3. **Token Estimation**: Uses `1 token ≈ 4 characters` as a rough estimate. Actual token count may vary.

4. **Rate Limiting**: The script still enforces TPM limits via the Token Bucket algorithm to prevent 429 errors.

---

## 🔍 Debugging

To see the dynamic limits in action, check the console output:

```
🚀 Starting audit...
Model: your-model-name | Max RPM: 30 | Max TPM: 500,000
Max File Size: 100,000 tokens (20% of TPM capacity)

[12:34:56.789] [1/150] file1.py [5,000 input + 2000 output tokens]
[12:34:57.123] [2/150] file2.py [12,000 input + 2000 output tokens]
[12:34:58.456] [3/150] [SKIPPED] huge_file.py is too large (120,000 tokens > 100,000 limit)
```

---

## 🎉 Summary

Your 500k TPM model can now audit files up to **100k tokens** instead of being limited to 22k!

The script automatically calculates the optimal file size limit based on your TPM, ensuring maximum throughput without hitting rate limits.


---

## 🎉 What This Means for You

**Before:** You had to select Option 3 and manually enter 500,000 TPM

**Now:** Just select Option 2 (Llama 4 Scout 17B) and the script will:
1. Detect your 500k TPM automatically from API headers
2. Show "UPGRADED LIMITS DETECTED!"
3. Ask if you want to use the higher limit (default: Yes)
4. Set max file size to 100,000 tokens automatically

**No more manual entry needed!** The script is smart enough to detect your Pro tier limits.

---

## 🔍 API Detection Details

The script reads these Groq API response headers:
- `x-ratelimit-limit-requests` → Max RPM
- `x-ratelimit-limit-tokens` → Max TPM

If your account has upgraded limits (500k TPM instead of 30k TPM), the headers will reflect that, and the script will automatically use the higher limits.

---

## 🚨 Troubleshooting

**Q: What if API detection fails?**  
A: The script will fall back to manual entry. You can still enter 500000 TPM manually.

**Q: What if I want to use default limits even though I have 500k TPM?**  
A: When prompted "Use detected limits? [Y/n]", type `n` to use defaults.

**Q: Can I skip the detection and go straight to manual entry?**  
A: Yes, select Option 3 (Custom Model) to skip detection entirely.

---

## ✅ Summary

The script now **automatically detects your 500k TPM** from Groq API headers when you select Option 2 (Llama 4 Scout 17B). No more manual entry needed!

Just run the script, select Option 2, and it will detect your Pro tier limits automatically.
