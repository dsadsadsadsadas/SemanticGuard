#!/usr/bin/env python3
"""
🛡️ Trepan Gatekeeper — FastAPI Server
POST /evaluate  → drift evaluation using Trepan_Model_V2
GET  /health    → status + model loaded flag
"""

import logging
import time
import os
import shutil
import difflib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .prompt_builder import build_prompt
from .response_parser import parse_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("trepan.server")

# ─── Vault Initialization ───────────────────────────────────────────────────

VAULT_STATE = {}
PILLARS = [
    "golden_state.md",
    "done_tasks.md",
    "pending_tasks.md",
    "history_phases.md",
    "system_rules.md",
    "problems_and_resolutions.md",
]

def init_vault():
    global VAULT_STATE
    # Action 1: Create in project root (parent directory of the server folder)
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    trepan_dir = os.path.join(root_dir, ".trepan")
    
    # Action 2: Name it simply 'trepan_vault' to make it visible
    vault_dir = os.path.join(root_dir, "trepan_vault")
    
    os.makedirs(vault_dir, exist_ok=True)
    
    for pillar in PILLARS:
        src = os.path.join(trepan_dir, pillar)
        dst = os.path.join(vault_dir, pillar)
        
        # Action 3: Physically copy current .trepan/*.md to trepan_vault every time
        if os.path.exists(src):
            shutil.copy2(src, dst)
            
        # Load into memory
        if os.path.exists(dst):
            with open(dst, "r", encoding="utf-8") as f:
                VAULT_STATE[pillar] = f.read()
        else:
            VAULT_STATE[pillar] = ""

    logger.info(f"🛡️  Shadow Vault initialized at {vault_dir} and loaded into memory.")

# ─── Startup: pre-load model ───────────────────────────────────────────────

_model_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load the model during server startup."""
    global _model_ready
    logger.info("🔄 Starting Trepan Gatekeeper server…")
    init_vault()
    try:
        from .model_loader import get_model
        get_model()  # warm up — loads weights once
        _model_ready = True
        logger.info("✅ Trepan_Model_V2 ready — server accepting requests")
    except Exception as e:
        logger.error(f"❌ Model failed to load: {e}")
        logger.warning("⚠️  Server will start but /evaluate will return 503 until model loads")
    yield
    logger.info("🛑 Trepan server shutting down")


# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Trepan Gatekeeper",
    description="Local drift-detection gatekeeper for AI-assisted coding prompts.",
    version="2.0.0",
    lifespan=lifespan,
)

# Allow Antigravity IDE extension (browser) to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # localhost extension — safe in local-only context
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Schemas ────────────────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    golden_state:             str = Field("", description="Contents of .trepan/golden_state.md")
    done_tasks:               str = Field("", description="Contents of .trepan/done_tasks.md")
    pending_tasks:            str = Field("", description="Contents of .trepan/pending_tasks.md")
    history_phases:           str = Field("", description="Phase history (optional)")
    system_rules:             str = Field("", description="Contents of .trepan/system_rules.md")
    problems_and_resolutions: str = Field("", description="Contents of .trepan/problems_and_resolutions.md (optional)")
    user_command:             str = Field(...,  description="The user's typed prompt or [SAVE INTERCEPT] payload")

class EvaluatePillarRequest(BaseModel):
    filename:         str = Field(..., description="The name of the pillar, e.g. system_rules.md")
    incoming_content: str = Field(..., description="The content of the pillar that the user is trying to save")



class EvaluateResponse(BaseModel):
    action:      str   = Field(...,  description="ACCEPT or REJECT")
    drift_score: float = Field(...,  description="0.0 (clean) – 1.0 (high drift)")
    raw_output:  str   = Field(...,  description="Full model reasoning for display")


class HealthResponse(BaseModel):
    status:       str  = "ok"
    model_loaded: bool = False
    version:      str  = "2.0.0"


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Status"])
async def health():
    """Quick liveness + readiness check for the IDE extension."""
    return HealthResponse(status="ok", model_loaded=_model_ready)


@app.post("/evaluate", response_model=EvaluateResponse, tags=["Gatekeeper"])
async def evaluate(req: EvaluateRequest):
    """
    Evaluate a user prompt against the 5 workspace pillars.

    Returns ACCEPT (drift_score < 0.40) or REJECT (drift_score >= 0.40).
    """
    if not _model_ready:
        raise HTTPException(
            status_code=503,
            detail="Trepan model is still loading. Retry in a few seconds."
        )

    prompt = build_prompt(
        golden_state=req.golden_state,
        done_tasks=req.done_tasks,
        pending_tasks=req.pending_tasks,
        history_phases=req.history_phases,
        system_rules=req.system_rules,
        problems_and_resolutions=req.problems_and_resolutions,
        user_command=req.user_command,
    )

    # Run inference
    t0 = time.perf_counter()
    try:
        from .model_loader import generate
        raw = generate(prompt)

        print("\n" + "="*40)
        print("🧠 TREPAN RAW THOUGHTS:")
        print(raw)
        print("="*40 + "\n")
        
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    elapsed = time.perf_counter() - t0
    logger.info(f"Inference took {elapsed:.2f}s — command: {req.user_command[:80]!r}")

    # Parse result
    result = parse_response(raw)

    logger.info(
        f"Decision: {result.action} | score={result.drift_score:.2f} | "
        f"cmd={req.user_command[:60]!r}"
    )

    return EvaluateResponse(
        action=result.action,
        drift_score=result.drift_score,
        raw_output=result.raw_output,
    )

# Build the ruthless Architect prompt
    prompt = f"""### SYSTEM: TREPAN ARCHITECT META-GATE
You are a deterministic logic gate. Evaluate the [DIFF] against the project [GOLDEN_STATE].
REJECT any non-technical rules, "banana" rules, or nonsense.
ACCEPT only valid software architecture improvements.

[GOLDEN_STATE]
{golden_state}

[DIFF - {filename}]
{diff}

---
[THOUGHT]
(1 sentence check)
[SCORE]
(1.00 for nonsense, 0.00 for perfect)
[ACTION]
(REJECT or ACCEPT)"""

    t0 = time.perf_counter()
    try:
        from .model_loader import generate
        raw = generate(prompt)

        print("\n" + "="*40)
        print("🏛️ TREPAN META-GATE RAW THOUGHTS:")
        print(raw)
        print("="*40 + "\n")
        
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    elapsed = time.perf_counter() - t0
    logger.info(f"Meta-Gate eval took {elapsed:.2f}s — file: {filename}")

    result = parse_response(raw)

    if result.action == "ACCEPT":
        # Write-Protection: update the vault after successful Meta-Evaluation
        VAULT_STATE[filename] = incoming_content
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        vault_file = os.path.join(root_dir, "trepan_vault", filename)
        with open(vault_file, "w", encoding="utf-8") as f:
            f.write(incoming_content)

    return EvaluateResponse(
        action=result.action,
        drift_score=result.drift_score,
        raw_output=raw,
    )
