#!/usr/bin/env python3
"""
🛡️ SemantGuard — Model Loader (Ollama API)
"""

import logging
import requests
import subprocess
import time
import sys
import shutil
import re as _re

logger = logging.getLogger("semantguard.model")


# ─── Public API ──────────────────────────────────────────────────────────────

def get_model():
    """Return dummy objects to satisfy legacy callers."""
    return None, None

def ensure_ollama_alive():
    """Check if Ollama is running, and attempt to start it if not."""
    url = "http://localhost:11434"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return True
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass

    logger.info("⚙️  Ollama not responding. Attempting to start 'ollama serve'...")
    
    if shutil.which("ollama") is None:
        logger.error("❌ Ollama binary not found in PATH.")
        return False

    try:
        # Start as a detached background process
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True

        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs
        )
        
        # Wait up to 30 seconds for it to wake up (Windows can be slow)
        logger.info("⏳ Waiting for Ollama to start (up to 30s)...")
        for i in range(30):
            time.sleep(1)
            try:
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    logger.info(f"✅ Ollama started successfully after {i+1} seconds.")
                    return True
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                continue
        
        logger.error("❌ Ollama failed to start within 30 seconds.")
    except Exception as e:
        logger.error(f"❌ Failed to auto-start Ollama: {e}")
        
    return False


def generate(prompt: str, system_prompt: str = None, processor_mode: str = "CPU", model_name: str = None) -> str:
    """
    Run inference using local Ollama API with /api/chat endpoint.
    Uses Alpaca-compatible chat format for fine-tuned models.
    
    Args:
        prompt: User prompt
        system_prompt: System prompt (optional)
        processor_mode: "GPU" (default) or "CPU"
        model_name: Model to use (optional, defaults to deepseek-r1:7b)
    """
    url = "http://localhost:11434/api/chat"
    
    # Build messages array for chat endpoint
    messages = []
    
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt
        })
    
    messages.append({
        "role": "user",
        "content": prompt
    })
    # Configure GPU/CPU based on mode
    num_gpu = 99 if processor_mode.upper() == "GPU" else 0
    
    # Model-specific stop tokens — critical for correct generation termination
    llama_stops = ["<|eot_id|>", "<|start_header_id|>"]
    deepseek_stops = []
    
    active_model = model_name or "llama3.1:8b"
    stop_tokens = llama_stops if "llama" in active_model.lower() else deepseek_stops
    
    # DeepSeek R1 needs MUCH more tokens — thinking block is separate and consumes 3000+ chars
    num_predict = 4000 if "deepseek" in active_model.lower() else 512
    
    # PRODUCTION — Model-specific configuration
    # STEP 1 — Minimal options
    options = {
        "temperature": 0.1,
        "num_ctx": 512,
        "num_gpu": 999,
    }
    
    payload = {
        "model": model_name or "llama3.1:8b",
        "messages": messages,
        "stream": False,
        "format": {
            "type": "object",
            "properties": {
                "data_flow_logic": {
                    "type": "object",
                    "properties": {
                        "step_1_source": {
                            "type": "object",
                            "properties": {
                                "line": {"type": "integer"},
                                "expression": {"type": "string"}
                            },
                            "required": ["line", "expression"]
                        },
                        "step_2_propagation": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "line": {"type": "integer"},
                                    "to": {"type": "string"}
                                }
                            }
                        },
                        "step_3_sink_check": {
                            "type": "object",
                            "properties": {
                                "sink_name": {"type": "string"},
                                "line": {"type": "integer"}
                            }
                        }
                    },
                    "required": ["step_1_source"]
                },
                "chain_complete": {"type": "boolean"},
                "verdict": {"type": "string", "enum": ["ACCEPT", "REJECT"]},
                "confidence": {"type": "string", "enum": ["HIGH", "LOW"]},
                "rejection_reason": {"type": "string"}
            },
            "required": ["data_flow_logic", "chain_complete", "verdict", "confidence", "rejection_reason"]
        },
        "options": options
    }
    
    if stop_tokens:
        payload["stop"] = stop_tokens

    logger.info(f"   Sending request to Ollama ({url}) [Mode: {processor_mode}]...")
    logger.info(f"   System prompt: {system_prompt[:100] if system_prompt else 'None'}...")
    logger.info(f"   User prompt: {prompt[:100]}...")
    
    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
    except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        logger.warning(f"⚠️ Ollama connection failed: {e}. Attempting self-healing...")
        if ensure_ollama_alive():
            # Retry once after revival
            try:
                response = requests.post(url, json=payload, timeout=180)
                response.raise_for_status()
            except Exception as retry_e:
                logger.error(f"❌ Self-healing failed during retry: {retry_e}")
                raise RuntimeError(f"Ollama inference error after retry: {retry_e}")
        else:
            raise RuntimeError(f"Ollama inference error: {e}")
    except requests.exceptions.Timeout:
        logger.error("Ollama request timed out after 120 seconds")
        raise RuntimeError("Ollama inference timeout")
    
    try:
        # Extract message content from chat response
        data = response.json()
        content = data["message"]["content"]
        
        logger.debug(f"[PIPE-1] RAW MODEL OUTPUT ({len(content)} chars):\n{content}")
        
        logger.info(f"   Generated {len(content)} characters from Ollama: {content[:80]!r}")
        import re as _re

        # Strip think block first using re.sub
        content_no_think = _re.sub(r"<think>.*?</think>", "", content, flags=_re.DOTALL).strip()
        search_target = content_no_think if content_no_think else content

        target_fields = r'"(?:verdict|data_flow_logic|chain_complete|sinks_scanned)"'
        # Allow nested objects — use a broader search that finds { followed by schema fields anywhere after it
        matches = list(_re.finditer(target_fields, search_target))
        if matches:
            # Walk backward from the first schema field match to find the opening {
            first_match_pos = matches[0].start()
            # Find the last { before the first schema field
            search_region = search_target[:first_match_pos]
            last_brace = search_region.rfind('{')
            if last_brace != -1:
                start_pos = last_brace
            else:
                start_pos = 0
        else:
            start_pos = -1

        if start_pos != -1:
            candidate = search_target[start_pos:]
            brace_count = 0
            end_pos = 0
            for i, char in enumerate(candidate):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break
            if end_pos > 0:
                result = candidate[:end_pos].strip()
                # Strip markdown code fences if present
                result = _re.sub(r'^```(?:json)?\s*', '', result)
                result = _re.sub(r'\s*```$', '', result)
                logger.debug(f"FINAL EXTRACTED ({len(result)} chars): {repr(result[:300])}")
                logger.debug(f"[PIPE-2] AFTER EXTRACTION ({len(result)} chars):\n{result}")
                return result.strip()

        final = search_target
        final = _re.sub(r'^```(?:json)?\s*', '', final)
        final = _re.sub(r'\s*```$', '', final)
        logger.debug(f"[PIPE-2] AFTER EXTRACTION ({len(final)} chars):\n{final}")
        return final.strip()

    except KeyError as e:
        logger.error(f"Unexpected Ollama response format: {e}")
        logger.error(f"Response: {response.json()}")
        raise RuntimeError(f"Ollama response format error: {e}")
    except Exception as e:
        logger.error(f"Ollama processing failed: {e}")
        raise RuntimeError(f"Ollama processing error: {e}")
