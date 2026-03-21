#!/usr/bin/env python3
"""
🛡️ Trepan — Model Loader (Ollama API)
"""

import logging
import requests
import subprocess
import time
import sys
import shutil
import re as _re

logger = logging.getLogger("trepan.model")


# ─── Public API ──────────────────────────────────────────────────────────────

def get_model():
    """Return dummy objects to satisfy legacy callers."""
    return None, None

def ensure_ollama_alive():
    """Check if Ollama is running, and attempt to start it if not."""
    url = "http://localhost:11434"
    try:
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            return True
    except requests.exceptions.ConnectionError:
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
        
        # Wait up to 10 seconds for it to wake up
        for i in range(10):
            time.sleep(1)
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    logger.info("✅ Ollama revived successfully.")
                    return True
            except requests.exceptions.ConnectionError:
                continue
    except Exception as e:
        logger.error(f"❌ Failed to auto-start Ollama: {e}")
        
    return False


def generate(prompt: str, system_prompt: str = None, processor_mode: str = "GPU", model_name: str = None) -> str:
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
    deepseek_stops = ["<|end_of_sentence|>"]
    
    active_model = model_name or "deepseek-r1:7b"
    stop_tokens = llama_stops if "llama" in active_model.lower() else deepseek_stops
    
    # DeepSeek needs more tokens — think block consumes ~300 before JSON starts
    num_predict = 800 if "deepseek" in active_model.lower() else 512
    
    options = {
        "temperature": 0.1,
        "num_ctx": 2048,
        "num_predict": num_predict,
        "num_thread": 8,
        "num_gpu": num_gpu,
        "stop": stop_tokens
    }
    
    payload = {
        "model": model_name or "deepseek-r1:7b",
        "messages": messages,
        "stream": False,
        "options": options
    }

    logger.info(f"   Sending request to Ollama ({url}) [Mode: {processor_mode}]...")
    logger.info(f"   System prompt: {system_prompt[:100] if system_prompt else 'None'}...")
    logger.info(f"   User prompt: {prompt[:100]}...")
    
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
    except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        logger.warning(f"⚠️ Ollama connection failed: {e}. Attempting self-healing...")
        if ensure_ollama_alive():
            # Retry once after revival
            try:
                response = requests.post(url, json=payload, timeout=120)
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
        
        logger.info(f"   Generated {len(content)} characters from Ollama: {content[:80]!r}")
        import re as _re

        # Find the LAST occurrence of { that is followed by one of the Trepan schema fields
        # This ignores any prose reasoning or earlier malformed JSON blocks
        target_fields = r'"(?:verdict|data_flow_logic|chain_complete)"'
        matches = list(_re.finditer(r'\{[^{}]*' + target_fields, content))
        
        if matches:
            # Take the last match start index as our JSON object beginning
            start_pos = matches[-1].start()
            candidate = content[start_pos:]
            
            # Simple brace balancer to extract the full JSON object
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
                content_no_think = candidate[:end_pos].strip()
                return content_no_think

        # Fallback to standard cleaning if no structured JSON was found via the pattern
        content_no_think = _re.sub(r"<think>.*?</think>", "", content, flags=_re.DOTALL).strip()
        return content_no_think if content_no_think else content

    except KeyError as e:
        logger.error(f"Unexpected Ollama response format: {e}")
        logger.error(f"Response: {response.json()}")
        raise RuntimeError(f"Ollama response format error: {e}")
    except Exception as e:
        logger.error(f"Ollama processing failed: {e}")
        raise RuntimeError(f"Ollama processing error: {e}")
