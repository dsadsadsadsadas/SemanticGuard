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


def generate(prompt: str, system_prompt: str = None, processor_mode: str = "GPU") -> str:
    """
    Run inference using local Ollama API with /api/chat endpoint.
    Uses Alpaca-compatible chat format for fine-tuned models.
    
    Args:
        prompt: User prompt
        system_prompt: System prompt (optional)
        processor_mode: "GPU" (default) or "CPU"
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
    
    payload = {
        "model": "llama3.1:8b",  # Stable Llama 3.1 8B model
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,     # Optimized for speed (less prefill overhead)
            "num_predict": 1024, # Limit output length
            "num_thread": 8,     # Use multiple threads for CPU segments
            "num_gpu": num_gpu,  # 99 = all GPU, 0 = all CPU
            "stop": [
                "<|eot_id|>",
                "<|start_header_id|>"
            ]
        }
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
        result = response.json()["message"]["content"]
        logger.info(f"   Generated {len(result)} characters from Ollama: {result[:80]!r}")
        return result
    except KeyError as e:
        logger.error(f"Unexpected Ollama response format: {e}")
        logger.error(f"Response: {response.json()}")
        raise RuntimeError(f"Ollama response format error: {e}")
    except Exception as e:
        logger.error(f"Ollama processing failed: {e}")
        raise RuntimeError(f"Ollama processing error: {e}")
