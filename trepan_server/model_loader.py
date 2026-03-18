#!/usr/bin/env python3
"""
🛡️ Trepan — Model Loader (Ollama API)
"""

import logging
import requests

logger = logging.getLogger("trepan.model")


# ─── Public API ──────────────────────────────────────────────────────────────

def get_model():
    """Return dummy objects to satisfy legacy callers."""
    return None, None


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
    num_gpu = 99 if processor_mode == "GPU" else 0
    
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
        response = requests.post(url, json=payload, timeout=30)
        
        print(f"DEBUG: Ollama Status Code: {response.status_code}")
        print(f"DEBUG: Raw Response Text: {response.text[:500]}...")
        
        response.raise_for_status()
        
        # Extract message content from chat response
        result = response.json()["message"]["content"]
        
        logger.info(f"   Generated {len(result)} characters from Ollama: {result[:80]!r}")
        return result
    except requests.exceptions.Timeout:
        logger.error("Ollama request timed out after 30 seconds")
        raise RuntimeError("Ollama inference timeout")
    except KeyError as e:
        logger.error(f"Unexpected Ollama response format: {e}")
        logger.error(f"Response: {response.json()}")
        raise RuntimeError(f"Ollama response format error: {e}")
    except Exception as e:
        logger.error(f"Ollama generation failed: {e}")
        raise RuntimeError(f"Ollama inference error: {e}")
