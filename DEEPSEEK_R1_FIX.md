# DeepSeek R1 Zero-Character Bug Fix

## Problem
When using `deepseek-r1:latest`, the model was returning "Generated 0 characters" on every audit, causing all audits to fail with ACCEPT (gate override).

## Root Cause
DeepSeek R1 models have a unique architecture that separates reasoning (thinking) from output (content):
- The `thinking` field contains the model's reasoning process (~3000-3700 characters)
- The `content` field contains the actual JSON response (~200-300 characters)

The original configuration used `num_predict: 800`, which was insufficient. The thinking block consumed most of the token budget, leaving only ~79 characters for the JSON response, causing it to be truncated mid-sentence.

## Isolation Diagnostic Results

| Step | Configuration | Result | Analysis |
|------|--------------|--------|----------|
| 1 | `num_ctx: 512` | 768 chars | Hallucinated Python code (context too small) |
| 2 | `num_ctx: 512, num_predict: 800` | ~500 chars | Hallucinated Flask code (context too small) |
| 3 | `num_ctx: 2048, num_predict: 800` | 0 chars | **Truncated JSON response** |
| 4 | `num_ctx: 2048, num_predict: 800, num_thread: 8` | 0 chars | Still truncated |
| 5 | `num_ctx: 4096, num_predict: 4000` | 215 chars | ✅ **COMPLETE VALID JSON** |

## Solution

### Changes Made to `trepan_server/model_loader.py`:

1. **Increased context window for DeepSeek R1:**
   ```python
   num_ctx: 4096  # Was 2048
   ```

2. **Increased token prediction limit:**
   ```python
   num_predict = 4000 if "deepseek" in active_model.lower() else 512
   # Was: num_predict = 800 if "deepseek" in active_model.lower() else 512
   ```

3. **Updated comment to reflect new understanding:**
   ```python
   # DeepSeek R1 needs MUCH more tokens — thinking block is separate and consumes 3000+ chars
   ```

### Changes Made to `trepan_server/server.py`:

1. **Rate-limited health check logging:**
   - Health checks now log once per minute instead of every request
   - Reduces console noise during development

## Verification

### Direct Ollama Test (Before Fix):
```json
{
  "content": "{\"verdict\": \"REJECT\",\"data_flow_logic\": \"Code logs user email, which is P"
}
```
**Result:** Truncated at 79 characters ❌

### Direct Ollama Test (After Fix):
```json
{
  "content": "{\"verdict\": \"REJECT\",\"data_flow_logic\": \"Code logs user email, which is PII, potentially exposing sensitive data to insecure logging mechanisms.\",\"chain_complete\": true,\"sinks_scanned\": [\"console.log\"]}"
}
```
**Result:** Complete valid JSON at 215 characters ✅

### Test Suite:
All 14 tests pass ✅

## Performance Impact

- **Llama 3.1:8b (Fast Mode):** ~5-7 seconds (unchanged)
- **DeepSeek R1:7b (Smart Mode):** ~18-25 seconds (slightly slower due to larger token generation, but now functional)

## Key Learnings

1. **DeepSeek R1 architecture is different:** The thinking/content separation means token budgets must account for BOTH parts
2. **Context window matters:** 512 tokens causes hallucinations, 2048 causes truncation, 4096 works correctly
3. **Model-specific tuning is critical:** What works for Llama doesn't work for DeepSeek R1
4. **Always test with direct Ollama calls:** This revealed the truncation issue immediately

## Files Modified

- `trepan_server/model_loader.py` - Increased `num_ctx` and `num_predict` for DeepSeek
- `trepan_server/server.py` - Rate-limited health check logging

## Status

✅ **FIXED** - DeepSeek R1 now returns complete, valid JSON responses
✅ **TESTED** - All 14 unit tests pass
✅ **READY** - Ready for beta testing with both Llama and DeepSeek models
