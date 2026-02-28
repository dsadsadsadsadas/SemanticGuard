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
import hashlib
import re
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

# ─── Cross-Platform Path Resolver ─────────────────────────────────────────────

def get_root_dir() -> str:
    """
    Returns the Trepan_Test_Zone path that works on both WSL and native Windows.
    On WSL (Linux kernel), C:\ maps to /mnt/c/.
    On Windows, use the Windows path directly.
    """
    import platform, sys
    win_path = r"C:\Users\ethan\Documents\Projects\Trepan_Test_Zone"
    # Detect WSL: Linux kernel but running under Windows Subsystem
    if sys.platform.startswith("linux"):
        wsl_path = "/mnt/c/Users/ethan/Documents/Projects/Trepan_Test_Zone"
        return wsl_path
    return win_path

# ─── Cryptographic Vault Security ──────────────────────────────────────────

def calculate_vault_hash() -> str:
    """Calculate a SHA-256 hash representing the current Vault disk state."""
    hasher = hashlib.sha256()
    root_dir = get_root_dir()
    vault_dir = os.path.join(root_dir, ".trepan", "trepan_vault")
    
    for pillar in sorted(PILLARS):
        dst = os.path.join(vault_dir, pillar)
        if os.path.exists(dst):
            with open(dst, "rb") as f:
                hasher.update(f.read())
        else:
            hasher.update(b"") 
            
    return hasher.hexdigest()

def verify_vault_hash() -> bool:
    """Check if the Vault matches the .trepan.lock signature."""
    root_dir = get_root_dir()
    lock_file = os.path.join(root_dir, ".trepan", ".trepan.lock")
    
    if not os.path.exists(lock_file):
        return True # If no lock exists, assume valid for first run
        
    with open(lock_file, "r", encoding="utf-8") as f:
        stored_hash = f.read().strip()
        
    return calculate_vault_hash() == stored_hash

def write_vault_lock():
    """Sign the vault by saving its hash to .trepan.lock."""
    root_dir = get_root_dir()
    lock_file = os.path.join(root_dir, ".trepan", ".trepan.lock")
    with open(lock_file, "w", encoding="utf-8") as f:
        f.write(calculate_vault_hash())


def init_vault():
    global VAULT_STATE
    try:
        print("\n" + "="*50)
        print("SHADOW VAULT INITIALIZATION STARTING...")
        
        # Target the extension testing folder explicitly
        root_dir = get_root_dir()
        trepan_dir = os.path.join(root_dir, ".trepan")
        
        # Action 2: Put trepan_vault INSIDE the .trepan folder
        vault_dir = os.path.join(trepan_dir, "trepan_vault")
        
        print(f"Target Root: {root_dir}")
        print(f"Source .trepan: {trepan_dir} (Exists? {os.path.exists(trepan_dir)})")
        print(f"Target Vault: {vault_dir}")
        
        os.makedirs(vault_dir, exist_ok=True)
        print(f"os.makedirs called. Vault exists on disk? {os.path.exists(vault_dir)}")
        
        # Action: Ensure Default Rules exist in the source system_rules.md
        sys_rules_src = os.path.join(trepan_dir, "system_rules.md")
        if os.path.exists(sys_rules_src):
            print("\n[RULE GUARDIAN] Scanning system_rules.md for mandatory defaults...")
            with open(sys_rules_src, "r", encoding="utf-8") as f:
                sys_content = f.read()
            
            mandatory_checks = [
                ("Strict Contextual Synchronization", "Strict Contextual Synchronization. Every architectural change must logically align with the established Project Context (README). If a developer introduces a new feature, rule, or concept, they must simultaneously update all affected pillars to prevent architectural drift. Isolated updates that create a contradiction between pillars or the project's core context are strictly forbidden."),
                ("create a Detailed And Planned Readme File", "After Understanding With User What the Project is about, create a Detailed And Planned Readme File, that is also Accepted by User."),
                ("NO hardcoded secrets, API keys, or passwords", "NO hardcoded secrets, API keys, or passwords"),
                ("NO `eval()` or `exec()`", "NO `eval()` or `exec()` with user input"),
                ("NO `os.system()` or `subprocess`", "NO `os.system()` or `subprocess` with `shell=True`"),
                ("ALL file paths must use `os.path.realpath()`", "ALL file paths must use `os.path.realpath()` + `startswith()` validation"),
                ("ALL SQL queries must use parameterized statements", "ALL SQL queries must use parameterized statements"),
                ("YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock", "YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock"),
            ]
            
            missing_rules = []
            for check_str, full_rule in mandatory_checks:
                if check_str in sys_content:
                    print(f"  [OK]      {check_str[:70]}")
                else:
                    print(f"  [MISSING] {check_str[:70]}")
                    missing_rules.append(full_rule)
                    
            if not missing_rules:
                print("[RULE GUARDIAN] All mandatory rules are present. No injection needed.")
            else:
                print(f"[RULE GUARDIAN] Injecting {len(missing_rules)} missing mandatory rules into system_rules.md...")
                
                # Determine the current highest Rule number safely
                rule_nums = [int(n) for n in re.findall(r"(?:^|\n)Rule\s+(\d+)\s*:", sys_content, re.IGNORECASE)]
                max_rule_num = max(rule_nums) if rule_nums else 0
                
                with open(sys_rules_src, "a", encoding="utf-8") as f:
                    f.write("\n\n## Trepan Mandatory Defaults\n")
                    for rule in missing_rules:
                        max_rule_num += 1
                        f.write(f"Rule {max_rule_num} : {rule}\n")
                        print(f"  [ADDED]   Rule {max_rule_num} : {rule[:70]}")
                print(f"[RULE GUARDIAN] Done. system_rules.md now has all mandatory defaults.")
        else:
            print("[RULE GUARDIAN] No system_rules.md found — skipping rule audit.")
        # Determine if this is first-time init or a restart with existing vault
        lock_file = os.path.join(trepan_dir, ".trepan.lock")
        is_first_init = not os.path.exists(lock_file)
        
        print(f"\n[VAULT LOCK] Lock file path : {lock_file}")
        print(f"[VAULT LOCK] Lock exists     : {os.path.exists(lock_file)}")
        print(f"[VAULT LOCK] Mode            : {'FIRST INIT - seeding from .trepan/' if is_first_init else 'RESTART - loading frozen snapshot'}")
        
        copied_files = 0
        for pillar in PILLARS:
            src = os.path.join(trepan_dir, pillar)
            dst = os.path.join(vault_dir, pillar)
            
            if is_first_init:
                # FIRST TIME ONLY: seed the vault from .trepan/ directory
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    copied_files += 1
            # else: on restarts, read existing vault — never overwrite with live files
                
            # Load vault into memory from the vault snapshot (not the live file)
            if os.path.exists(dst):
                with open(dst, "r", encoding="utf-8") as f:
                    VAULT_STATE[pillar] = f.read()
                if is_first_init:
                    print(f"  [VAULT] Seeded {pillar} from .trepan/")
                else:
                    print(f"  [VAULT] Loaded {pillar} from snapshot ({len(VAULT_STATE[pillar])} chars)")
            else:
                VAULT_STATE[pillar] = ""
                print(f"  [VAULT] WARNING: {pillar} missing from vault (empty in VAULT_STATE)")

        if is_first_init:
            print(f"\n[VAULT LOCK] First-time vault seeded with {copied_files} files.")
            try:
                write_vault_lock()
                print(f"[VAULT LOCK] Lock written to: {lock_file}")
                print(f"[VAULT LOCK] Lock exists now: {os.path.exists(lock_file)}")
            except Exception as lock_err:
                print(f"[VAULT LOCK] ERROR writing lock file: {lock_err}")
        else:
            print(f"\n[VAULT LOCK] Snapshot loaded ({len(VAULT_STATE)} pillars). Tripwire active.")
            print("  -> Live .trepan/ files are NOT copied to vault. Only ACCEPT verdicts update the vault.")
        
        print("="*50 + "\n")
        
        logger.info(f"Shadow Vault initialized at {vault_dir} and loaded into memory.")
    except Exception as e:
        print(f"\nCRITICAL ERROR IN init_vault: {e}")
        import traceback
        traceback.print_exc()
        print("="*50 + "\n")
        logger.error(f"Failed to init shadow vault: {e}")

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



class ResignResponse(BaseModel):
    status: str
    message: str

class EvaluateResponse(BaseModel):
    action:        str   = Field(...,  description="ACCEPT, REJECT, or ERROR")
    drift_score:   float = Field(...,  description="0.0 (clean) – 1.0 (high drift)")
    raw_output:    str   = Field(...,  description="Clean [THOUGHT] reasoning for display")
    vault_updated: bool  = Field(False, description="True if the vault snapshot was updated")
    vault_file:    str   = Field("",    description="Which vault file was updated (on ACCEPT)")


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

    root_dir = r"C:\Users\ethan\Documents\Projects\Trepan_Test_Zone"
    readme_path = os.path.join(root_dir, "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_content = f.read()
        logger.info(f"📄 Loaded Project Context from {readme_path}")
    else:
        readme_content = "No project context provided. Enforce strict technical baseline."
        logger.warning(f"⚠️  No README.md found at {readme_path}. Enforcing strict baseline.")

    prompt = build_prompt(
        golden_state=req.golden_state,
        system_rules=req.system_rules,
        user_command=req.user_command,
        readme_content=readme_content,
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

# ─── Vault Recovery & Resigning Endpoint ───────────────────────────────────

@app.post("/resign_vault", response_model=ResignResponse, tags=["Security"])
async def resign_vault():
    """Action 1 & 2: Recovery mechanism if the Vault is tampered with."""
    global VAULT_STATE
    root_dir = r"C:\Users\ethan\Documents\Projects\Trepan_Test_Zone"
    trepan_dir = os.path.join(root_dir, ".trepan")
    vault_dir = os.path.join(trepan_dir, "trepan_vault")
    
    # Overwrite the vault files with Ground-Truth workspace files
    for pillar in PILLARS:
        src = os.path.join(trepan_dir, pillar)
        dst = os.path.join(vault_dir, pillar)
        
        if os.path.exists(src):
            shutil.copy2(src, dst)
            with open(dst, "r", encoding="utf-8") as f:
                VAULT_STATE[pillar] = f.read()
        else:
            VAULT_STATE[pillar] = ""
            
    # Generate new SHA-256 hash and lock
    write_vault_lock()
    return ResignResponse(status="success", message="Vault cryptographically re-signed.")

# ─── Pillar Evaluation Endpoint ────────────────────────────────────────────

@app.post("/evaluate_pillar", response_model=EvaluateResponse, tags=["Gatekeeper"])
async def evaluate_pillar(req: EvaluatePillarRequest):
    """Evaluate a proposed change to one of the 5 workspace pillars."""
    if not _model_ready:
        raise HTTPException(status_code=503, detail="Trepan model is still loading.")
        
    # Action 3: Cryptographic Tamper Check
    if not verify_vault_hash():
        logger.warning(f"🚨 VAULT COMPROMISED: Hash mismatch on {req.filename}")
        return EvaluateResponse(
            action="VAULT_COMPROMISED",
            drift_score=1.0,
            raw_output="Ground-truth files modified."
        )

    # Calculate diff
    golden_state = VAULT_STATE.get("golden_state.md", "")
    current_pillar_content = VAULT_STATE.get(req.filename, "")
    
    diff_lines = list(difflib.unified_diff(
        current_pillar_content.splitlines(),
        req.incoming_content.splitlines(),
        fromfile="current",
        tofile="incoming",
        lineterm=""
    ))
    diff_text = "\n".join(diff_lines)

    root_dir = r"C:\Users\ethan\Documents\Projects\Trepan_Test_Zone"
    readme_path = os.path.join(root_dir, "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_content = f.read()
        logger.info(f"📄 Loaded Project Context from {readme_path}")
    else:
        readme_content = "No project context provided. Enforce strict technical baseline."
        logger.warning(f"⚠️  No README.md found at {readme_path}. Enforcing strict baseline.")

    # The 'Cornered' Prompt — ends exactly at [THOUGHT] to prevent AI roleplay
    prompt = f"""Evaluate the [DIFF] against the [PROJECT_CONTEXT] and [GOLDEN_STATE].
You must output exactly three tags: [THOUGHT], [SCORE], and [ACTION].
Do not generate any fake scenarios or user dialogues.

[PROJECT_CONTEXT]
{readme_content}

[GOLDEN_STATE]
{golden_state}

[DIFF]
{diff_text}

[THOUGHT]"""

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
    logger.info(f"Meta-Gate eval took {elapsed:.2f}s — file: {req.filename}")

    result = parse_response(raw)
    vault_updated = False

    if result.action == "ACCEPT":
        # 1. Update the in-memory VAULT_STATE
        VAULT_STATE[req.filename] = req.incoming_content
        print(f"[VAULT SYNC] ACCEPT verdict for '{req.filename}' — syncing to vault...")
        
        # 2. Write the accepted content to the correct vault snapshot file
        root_dir = get_root_dir()
        vault_file_path = os.path.join(root_dir, ".trepan", "trepan_vault", req.filename)
        with open(vault_file_path, "w", encoding="utf-8") as f:
            f.write(req.incoming_content)
        print(f"[VAULT SYNC] Written: trepan_vault/{req.filename}")
            
        # 3. Recalculate SHA-256 hash for entire vault directory and re-sign .trepan.lock
        write_vault_lock()
        lock_path = os.path.join(root_dir, ".trepan", ".trepan.lock")
        print(f"[VAULT SYNC] Lock re-signed: {lock_path}")
        print(f"[VAULT SYNC] Complete ✅ — trepan_vault/{req.filename} is now the new baseline.")
        vault_updated = True

    return EvaluateResponse(
        action=result.action,
        drift_score=result.drift_score,
        raw_output=result.raw_output,
        vault_updated=vault_updated,
        vault_file=req.filename if vault_updated else "",
    )
