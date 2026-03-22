# DEBUG INSTRUCTIONS

## Check the server terminal window

Look at the server terminal where you ran `python start_server.py`.

What do you see after the test script sent the request?

Look for these specific lines:

1. **Request received?**
   - `POST /evaluate` or similar

2. **Ollama request sent?**
   - `Sending request to Ollama (http://localhost:11434/api/chat)`

3. **Any errors?**
   - Stack traces, exceptions, or error messages

4. **Is it stuck?**
   - Does the log just stop at "Sending request to Ollama" with no response?

## Paste the last 20-30 lines from the server terminal

This will tell us exactly where it's hanging.

## Quick test: Is Ollama responding at all?

Run this in your terminal:

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "deepseek-r1:latest",
  "prompt": "Say hello",
  "stream": false,
  "options": {
    "temperature": 0.1,
    "num_ctx": 512,
    "num_gpu": 999
  }
}'
```

Does this return immediately or hang?
