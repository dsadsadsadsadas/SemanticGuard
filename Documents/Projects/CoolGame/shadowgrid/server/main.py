"""
ShadowGrid FastAPI Server

Main application entry point with REST endpoints and WebSocket handling.
"""

from __future__ import annotations
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..game.world import Grid, GridConfig
from ..game.constants import DEFAULT_GRID_CONFIG
from .websocket import game_ws, GameWebSocket
from .replay import ReplayRecorder
from .ai_detector import ai_detector
from .match_manager import match_manager
from ..anticheat.secure_pipeline import secure_pipeline


# =============================================================================
# LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("🎮 ShadowGrid Server starting...")
    from ..database import init_db
    await init_db()
    
    game_ws.create_game()
    yield
    # Shutdown
    print("🎮 ShadowGrid Server shutting down...")
    game_ws.running = False


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="ShadowGrid",
    description="Anti-Cheat POMDP Game Server",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# SECURE PIPELINE (WARDEN)
# =============================================================================

@app.websocket("/warden/{session_id}")
async def warden_endpoint(websocket: WebSocket, session_id: str):
    """
    🛡️ SECURE PIPELINE: Receives integrity reports from the Warden Sidecar.
    This channel is separate from the game move channel.
    """
    await websocket.accept()
    
    # Register Warden channel
    session = secure_pipeline.get_session(session_id)
    if session:
        secure_pipeline.connect_warden_channel(session_id)
        print(f"🛡️ SECURE PIPELINE ESTABLISHED for session {session_id[:8]}...")
    else:
        print(f"⚠️ WARDEN CONNECTION REJECTED: Unknown session {session_id[:8]}...")
        await websocket.close(code=4003) # Forbidden
        return

    try:
        while True:
            # Receive encrypted report (JSON for demo)
            data = await websocket.receive_json()
            
            # Validate and process report
            valid, reason = secure_pipeline.receive_warden_report(session_id, data)
            
            if not valid:
                print(f"🚨 WARDEN REPORT REJECTED [{session_id[:8]}]: {reason}")
                # In strict mode, we would ban immediately
            
            # Log specific alerts
            if data.get("alerts"):
                for alert in data["alerts"]:
                    severity = alert.get("severity", "INFO")
                    print(f"🚨 WARDEN ALERT [{session_id[:8]}]: {alert.get('message')}")
                    
    except WebSocketDisconnect:
        print(f"⚠️ Warden Disconnected for {session_id[:8]}")
    except Exception as e:
        print(f"⚠️ Warden Error for {session_id[:8]}: {e}")


# CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Replay recorder
replay_recorder = ReplayRecorder()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class NewGameRequest(BaseModel):
    width: int = 20
    height: int = 20
    lava_density: float = 0.15
    crystal_count: int = 10
    seed: Optional[int] = None


class GameStateResponse(BaseModel):
    tick: int
    players: dict
    crystals_remaining: int
    grid_width: int
    grid_height: int


class PlayerStatsResponse(BaseModel):
    player_id: str
    suspicion_score: float
    is_flagged: bool
    violations: dict


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "game": "ShadowGrid",
        "status": "online",
        "version": "0.1.0",
        "players": len(game_ws.clients)
    }


@app.post("/game/new")
async def create_new_game(request: NewGameRequest):
    """Create a new game instance."""
    # [FIX] Force finalize previous match if it exists and wasn't saved yet
    # This prevents 'run_demo.py' from overwriting unsaved data when restarting quickly
    if match_manager.current_match_id:
        print(f"⚠️ FORCE FINALIZING stalled match: {match_manager.current_match_id}")
        await match_manager.finalize_match(ai_detector)

    config = GridConfig(
        width=request.width,
        height=request.height,
        lava_density=request.lava_density,
        crystal_count=request.crystal_count,
        seed=request.seed
    )
    
    game_ws.create_game(config)
    
    # Start replay recording
    replay_id = f"game_{uuid.uuid4().hex[:8]}"
    replay_recorder.start_recording(replay_id)
    
    return {
        "status": "created",
        "replay_id": replay_id,
        "grid_size": [config.width, config.height],
        "crystals": config.crystal_count
    }


@app.get("/game/state")
async def get_game_state():
    """Get current game state (admin view)."""
    if not game_ws.game_state:
        raise HTTPException(status_code=404, detail="No active game")
    
    gs = game_ws.game_state
    
    # Get suspicion scores from validator
    players_data = {}
    for pid, player in gs.players.items():
        state = player.get_state()
        # Add suspicion score from validator
        val_state = game_ws.validator.get_player_stats(pid)
        score = val_state['suspicion_score'] if val_state else 0.0
        
        # Override with AI score if available and higher
        ai_data = ai_detector.get_player_analysis(pid)
        if ai_data:
            state['ai_score'] = ai_data['xgboost_score']
            state['ai_flagged'] = ai_data['is_flagged']
            score = max(score, ai_data['xgboost_score'])
            
        state['suspicion_score'] = score
        players_data[pid] = state
    
    return {
        "tick": gs.current_tick,
        "players": players_data,
        "crystals_remaining": gs.grid.crystals_remaining,
        "grid_size": [gs.grid.width, gs.grid.height]
    }


@app.get("/game/grid")
async def get_full_grid():
    """Get full grid state (admin/debug only)."""
    if not game_ws.game_state:
        raise HTTPException(status_code=404, detail="No active game")
    
    return {
        "grid": game_ws.game_state.grid.get_full_state(),
        "width": game_ws.game_state.grid.width,
        "height": game_ws.game_state.grid.height
    }


@app.get("/players")
async def get_players():
    """Get list of connected players."""
    print(f"📊 API /players called. game_ws.clients = {len(game_ws.clients)}")
    print(f"   game_ws id = {id(game_ws)}")
    return {
        "count": len(game_ws.clients),
        "players": [
            {
                "player_id": pid,
                "connected_at": client.connected_at,
                "latency_ms": client.latency_ms
            }
            for pid, client in game_ws.clients.items()
        ]
    }


@app.get("/anticheat/flagged")
async def get_flagged_players():
    """Get list of players flagged for review."""
    return {
        "flagged": game_ws.validator.get_flagged_players(),
        "threshold": game_ws.validator.SUSPICION_THRESHOLD
    }


@app.get("/anticheat/player/{player_id}")
async def get_player_anticheat_stats(player_id: str):
    """Get anti-cheat statistics for a specific player."""
    stats = game_ws.validator.get_player_stats(player_id)
    
    if not stats:
        raise HTTPException(status_code=404, detail="Player not found")
    
    return stats


@app.post("/replay/stop")
async def stop_replay_recording():
    """Stop current replay recording and save."""
    filepath = replay_recorder.stop_recording()
    
    if not filepath:
        return {"status": "no_recording"}
    
    return {
        "status": "saved",
        "filepath": filepath
    }


@app.get("/ai/scores")
async def get_ai_scores():
    """Get all current AI scores."""
    return ai_detector.get_all_scores()


@app.post("/ai/analyze/{player_id}")
async def run_deep_analysis(player_id: str):
    """Trigger Llama deep analysis for a player."""
    result = await ai_detector.run_deep_analysis(player_id)
    if not result:
        return {"status": "failed", "reason": "No data or model unavailable"}
    return result


# =============================================================================
# MATCH HISTORY ENDPOINTS
# =============================================================================

from .match_manager import match_manager


@app.get("/matches")
async def get_matches(limit: int = 50):
    """Get match history."""
    return await match_manager.get_match_history(limit)


@app.get("/matches/{match_id}")
async def get_match_cases(match_id: str):
    """Get all cases for a specific match."""
    cases = await match_manager.get_match_cases(match_id)
    if not cases:
        raise HTTPException(status_code=404, detail="Match not found")
    return cases


@app.post("/matches/{match_id}/train")
async def trigger_rl_training(match_id: str):
    """Trigger RL training update for a match."""
    # TODO: Implement RL trainer integration
    return {"status": "pending", "message": "RL training not yet implemented"}


# =============================================================================
# DASHBOARD ENDPOINTS
# =============================================================================

@app.get("/api/cases")
async def get_dashboard_cases():
    """Get active cases for dashboard."""
    from ..database import db_manager, Case
    from sqlalchemy import select
    
    async with db_manager.session_factory() as session:
        result = await session.execute(
            select(Case).order_by(Case.created_at.desc()).limit(50)
        )
        cases = result.scalars().all()
        return cases

@app.get("/api/cases/{case_id}")
async def get_case_details(case_id: str):
    """Get specific case details."""
    from ..database import db_manager, Case, Session
    from sqlalchemy import select
    
    async with db_manager.session_factory() as session:
        result = await session.execute(
            select(Case).where(Case.case_id == case_id)
        )
        case = result.scalar_one_or_none()
        
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
            
        return case

@app.post("/api/cases/{case_id}/resolve")
async def resolve_case(case_id: str, verdict: dict):
    """Resolve a case (ban or clear)."""
    # Logic to apply verdict, ban player, update DB
    return {"status": "resolved", "verdict": verdict}

@app.get("/api/stats/dashboard")
async def get_dashboard_stats():
    """Get global dashboard stats."""
    from ..database import db_manager, Player, Case
    from sqlalchemy import select, func
    
    async with db_manager.session_factory() as session:
        # Count active players (approx 24h)
        # Count flagged
        return {
            "active_players": len(game_ws.clients),
            "flagged_users": len(game_ws.validator.flagged_players),
            "banned_today": 0, # TODO: Query DB
            "system_load": "12%" # Mock
        }


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@app.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    """WebSocket endpoint for game communication."""
    print(f"🔌 WS ENDPOINT CALLED for {player_id}", flush=True)
    print(f"   game_ws id: {id(game_ws)}", flush=True)
    print(f"   game_ws.clients BEFORE: {list(game_ws.clients.keys())}", flush=True)
    try:
        await game_ws.connect(websocket, player_id)
        print(f"   game_ws.clients AFTER: {list(game_ws.clients.keys())}", flush=True)
        
        while True:
            message = await websocket.receive_text()
            await game_ws.handle_message(player_id, message)

            # [BAN HAMMER] Only ban if Panopticon/Oracle detected (score=100) or explicitly flagged by Tier2
            ai_data = ai_detector.get_player_analysis(player_id)
            if ai_data:
                score = ai_data.get('xgboost_score', 0.0)
                is_flagged = ai_data.get('is_flagged', False)
                
                # [FIX] Score is 0-100, not 0-1. Check >= 95.0 (95%)
                # [DEBUG] Log all values
                print(f"[BAN_CHECK] {player_id}: score={score:.1f}, is_flagged={is_flagged}, FLAG_THRESHOLD=99")
                if score >= 95.0 or is_flagged:
                    reason = f"AI Detection (Score: {score:.1f}%)"
                    print(f"🔨 BANNED {player_id} (Reason: {reason})")
                    
                    # [FIX] Update match manager verdict BEFORE ban to ensure UI shows moves/score
                    # Get current moves from player stats
                    current_moves = 0
                    if game_ws.game_state:
                         p = game_ws.game_state.players.get(player_id)
                         if p:
                             current_moves = p.stats.total_moves

                    match_manager.update_player(
                        player_id,
                        total_moves=current_moves,
                        ai_score=score,
                        ai_reasoning=f"BANNED: {reason}"
                    )
                    
                    try:
                        await websocket.send_json({"type": "ban", "reason": reason})
                        await websocket.close(code=1008)
                    except:
                        pass
                    break
    
    except WebSocketDisconnect:
        print(f"🔌 WS DISCONNECT for {player_id}")
        await game_ws.disconnect(player_id)
    
    except Exception as e:
        print(f"WebSocket error for {player_id}: {e}")
        await game_ws.disconnect(player_id)


# =============================================================================
# DEVELOPMENT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
