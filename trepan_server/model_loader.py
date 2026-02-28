#!/usr/bin/env python3
"""
🛡️ Trepan — Model Loader

Load priority:
  1. Unsloth  (fastest, GPU + 4-bit, preferred)
  2. Transformers + PEFT  (no bitsandbytes, avoids broken conda packages)
     2a. float16 on CUDA
     2b. float32 on CPU  (slow, for dev/test only)
"""

import os
import logging
import warnings
from pathlib import Path

# Silence transformers deprecation noise (FutureWarning logging bug in older versions)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="transformers")
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("transformers.modeling_attn_mask_utils").setLevel(logging.ERROR)

logger = logging.getLogger("trepan.model")

# Silence Unsloth's torchvision version mismatch warning before it even imports
os.environ.setdefault("UNSLOTH_SKIP_TORCHVISION_CHECK", "1")

_ADAPTER_PATH = str(Path(__file__).parent.parent / "Trepan_Model_V2")
_BASE_MODEL   = "unsloth/llama-3-8b-bnb-4bit"
_MAX_NEW_TOKENS = 512

_model     = None
_tokenizer = None


# ─── Public API ──────────────────────────────────────────────────────────────

def get_model():
    """Return (model, tokenizer), loading on first call."""
    if _model is None or _tokenizer is None:
        _load_model()
    return _model, _tokenizer


def generate(prompt: str) -> str:
    """Run greedy inference on prompt, return generated text only."""
    import torch
    from transformers import GenerationConfig
    model, tokenizer = get_model()

    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1800)
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # Stop strings: physically halt token generation when model tries to roleplay.
    # GenerationConfig stop_strings requires the tokenizer to compute byte-level token overlaps.
    stop_sequences = [
        "User:",    # Roleplay start
        "\nUser:",  # Roleplay on new line
        "###",      # Dialogue separator
        "[THOUGHT]", # Model looping back to re-evaluate
        "\n\n\n",  # Triple newline = trailing yap
    ]

    gen_config = GenerationConfig(
        max_new_tokens=120,       # Tight budget — short answers only
        do_sample=False,          # Greedy decoding = deterministic
        temperature=1.0,          # Must be 1.0 when do_sample=False (ignored anyway)
        pad_token_id=tokenizer.eos_token_id,
    )

    with torch.no_grad():
        out = model.generate(
            **inputs,
            generation_config=gen_config,
            tokenizer=tokenizer,           # Needed for stop_strings byte-overlap
            stop_strings=stop_sequences,
        )
    generated = out[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


# ─── Internal loading ─────────────────────────────────────────────────────────

def _load_model():
    global _model, _tokenizer

    logger.info("🔄 Loading Trepan_Model_V2 adapter…")
    logger.info(f"   Base    : {_BASE_MODEL}")
    logger.info(f"   Adapter : {_ADAPTER_PATH}")

    # ── 1. Try Unsloth ────────────────────────────────────────────────────────
    try:
        from unsloth import FastLanguageModel

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=_ADAPTER_PATH,
            max_seq_length=2048,
            dtype=None,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(model)
        _model, _tokenizer = model, tokenizer
        logger.info("✅ Loaded via Unsloth (4-bit GPU)")
        return

    except Exception as e:
        logger.warning(f"⚠️  Unsloth unavailable ({type(e).__name__}: {e})")
        logger.warning("    Falling back to transformers + PEFT…")

    # ── 2. Transformers + PEFT fallback (NO bitsandbytes) ────────────────────
    _load_peft_fallback()


def _load_peft_fallback():
    """
    Minimal PEFT fallback — intentionally avoids bitsandbytes, accelerate,
    datasets, and evaluate to prevent broken conda C-extension chains.
    Loads in float16 on CUDA or float32 on CPU.
    """
    global _model, _tokenizer

    # These three are the ONLY imports needed — no sklearn chain possible
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    cuda_ok = torch.cuda.is_available()
    dtype  = torch.float16 if cuda_ok else torch.float32
    device = "cuda"        if cuda_ok else "cpu"

    if cuda_ok:
        logger.info(f"   CUDA device : {torch.cuda.get_device_name(0)}")
        logger.info(f"   VRAM free   : {torch.cuda.mem_get_info()[0] / 1e9:.1f} GB")
    else:
        logger.warning("   ⚠️  No CUDA detected — loading on CPU (slow!)")
        logger.warning("   To fix: reinstall torch with CUDA support:")
        logger.warning("   pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 "
                       "--index-url https://download.pytorch.org/whl/cu121")

    logger.info(f"   dtype={dtype}  device={device}")

    # Load tokenizer from local adapter (has the tokenizer files)
    tokenizer = AutoTokenizer.from_pretrained(
        _ADAPTER_PATH,
        trust_remote_code=False,
        use_fast=True,
    )

    # Load the base model — NOTE: unsloth/llama-3-8b-bnb-4bit is a 4-bit
    # checkpoint; without bitsandbytes we load the raw weights at float16/32.
    # This needs ~16 GB VRAM (float16) or ~32 GB RAM (float32).
    # For a lighter load, replace _BASE_MODEL with "meta-llama/Llama-3-8B".
    logger.info("   Loading base model weights (this may take 1–3 minutes)…")
    base = AutoModelForCausalLM.from_pretrained(
        _BASE_MODEL,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )

    if cuda_ok:
        base = base.cuda()

    logger.info("   Applying LoRA adapter…")
    model = PeftModel.from_pretrained(base, _ADAPTER_PATH, is_trainable=False)
    model.eval()

    _model, _tokenizer = model, tokenizer
    logger.info(f"✅ Loaded via PEFT fallback  [{device} / {dtype}]")
