# ShadowGrid Anti-Cheat System - Complete Technical Overview

## Executive Summary

ShadowGrid is a **POMDP (Partially Observable Markov Decision Process) gridworld game** with a sophisticated **three-tier AI anti-cheat system** that evolves through **adversarial reinforcement learning**. The system is designed as a research testbed for anti-cheat detection algorithms.

---

## 1. Game Architecture

### Core Mechanics
- **Grid**: 20×20 procedurally generated world
- **Tiles**: Empty, Wall, Lava (damage), Crystal (reward), Exit (goal)
- **Player Objective**: Collect all crystals, reach exit, avoid lava
- **Fog of War**: Players only see 3×3 area (POMDP constraint)
- **Server Authority**: Full grid state on server, partial on client

### Technology Stack
```
Server: Python + FastAPI + WebSocket (real-time sync)
Client: Pygame (fog-of-war rendering)
Protocol: Deterministic lockstep (tick-based)
```

### Why POMDP?
The partial observability creates a natural asymmetry:
- **Legitimate players**: Make decisions based on visible 3×3 area
- **Cheaters (wallhack/ESP)**: Make decisions based on hidden information

This asymmetry is the foundation for cheat detection.

---

## 2. Three-Tier Anti-Cheat Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     PLAYER ACTIONS                           │
│               (movement, timing, patterns)                   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 1: XGBoost (Client-Side, Fast)                        │
│  ────────────────────────────────────                       │
│  • 50 features per session                                  │
│  • Goal: HIGH RECALL (catch 95%+ cheaters)                  │
│  • Accepts false positives → escalates to Tier 2            │
│  • Latency: <10ms per prediction                            │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ (flagged players only)
┌─────────────────────────────────────────────────────────────┐
│  TIER 2: TabNet + Llama 3.1 (Server-Side, Deep)             │
│  ──────────────────────────────────────────────             │
│  • TabNet: 66 features (50 session + 16 player history)     │
│  • Llama 3.1: Replay analysis via Groq API                  │
│  • Goal: HIGH PRECISION (minimize false bans)               │
│  • Provides explainable verdicts with attention weights     │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ (uncertain cases)
┌─────────────────────────────────────────────────────────────┐
│  TIER 3: Human Expert Review                                │
│  ───────────────────────────                                │
│  • Case management with priority queue                      │
│  • Evidence viewer (replay + AI reasoning)                  │
│  • Human feedback improves AI models                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Feature Engineering (50+ Features)

### Tier 1 Features (extracted per session)

| Category | Features | Cheat Type Detected |
|----------|----------|---------------------|
| **Movement** | velocity_avg, acceleration, path_straightness, direction_entropy | Speedhack, Aimbot |
| **Timing** | input_frequency, input_regularity_std, reaction_time_avg | Macro, Bot |
| **Anomalies** | speed_violations, teleport_detection, fog_violations | Speedhack, Teleport, Wallhack |
| **Patterns** | behavioral_consistency, knowledge_anomaly, optimal_pathing_ratio | Wallhack, ESP |

### Key Detection Signals

1. **Fog Violations**: Moving directly toward crystals outside 3×3 visibility
2. **Speed Violations**: Moving faster than physics allows
3. **Input Regularity**: Inhuman consistency (bots have σ < 0.01s)
4. **Optimal Pathing**: Always taking shortest path to hidden objectives

---

## 4. AI Models in Detail

### Tier 1: XGBoost
```python
# Configuration
XGBClassifier(
    max_depth=4,
    learning_rate=0.1,
    n_estimators=50,
    threshold=0.3  # Low threshold for high recall
)
```

**Training Data**: Synthetic generation of:
- Normal players (varied skill levels)
- Speedhack profiles (velocity > max_speed)
- Wallhack profiles (fog violations)
- Aimbot profiles (perfect timing)
- Macro profiles (too-regular inputs)

### Tier 2: TabNet
```python
# Architecture
TabNetClassifier(
    n_d=24, n_a=24,  # Attention dimensions
    n_steps=4,       # Decision steps
    gamma=1.3        # Coefficient for feature reuse
)

# Input: 66 features
SESSION_FEATURES = 50   # From Tier 1
HISTORY_FEATURES = 16   # Player's historical behavior
```

**Attention Mechanism**: TabNet provides explainable outputs:
```
Top suspicious features:
  - fog_violations: 35% attention
  - speed_violations: 25% attention
  - input_regularity_std: 15% attention
```

### Tier 2: Llama 3.1 Visual Analysis
```python
# Prompt template
prompt = """
Analyze this gameplay sequence for wallhack indicators:
- Does the player move directly toward hidden objectives?
- Do they avoid hazards that should be invisible?

Frame data:
{frame_summaries}

Provide:
1. SUSPICION_LEVEL: low/medium/high/certain
2. CONFIDENCE: 0.0-1.0
3. KEY_EVIDENCE: specific behaviors observed
"""
```

**Current Usage**: Text-based frame analysis (not actual video)
**API**: Groq (fast inference for Llama 3.1 70B)

---

## 5. Adversarial RL (Cheater vs Detector)

### Cheater Agent Architecture
```python
# Environment: Full observability (cheater sees entire grid)
CheaterEnv(
    observation_space=(grid_state + player_state),
    action_space=Discrete(10)  # 5 directions × 2 (normal/stealth)
)

# Reward function
reward = game_reward - (detectability_score × λ)

# Agent: PPO (Proximal Policy Optimization)
PPO('MlpPolicy', env, learning_rate=3e-4)
```

### Co-Evolution Training Loop
```
for iteration in range(N):
    1. Train cheater (maximize score, minimize detection)
    2. Collect cheater behavior samples
    3. Retrain detector on new cheater behavior
    4. Increase λ (detection penalty harder)
```

**Results from 3 iterations**:
- Cheater learned to reduce detectability: 10% → 2%
- Detector recall improved: 94.8% → 100%
- Arms race creates stronger both agents

---

## 6. Enforcement System

### Graduated Response
| Detection Score | Action |
|-----------------|--------|
| ≥95% | Permanent ban |
| 85-94% | 7-30 day temp ban |
| 70-84% | 24h ban + monitoring |
| 50-69% | Shadow ban (match with other cheaters) |
| 30-49% | Warning |
| <30% | No action |

### Metrics Tracked
- **Precision**: True cheaters / All bans
- **Recall**: Detected cheaters / All cheaters
- **False Positive Rate**: False bans / All legitimate players
- **AUC**: Area under ROC curve

---

## 7. Current Implementation Status

### ✅ Completed
- [x] Game environment with POMDP fog-of-war
- [x] WebSocket real-time multiplayer
- [x] 50-feature extraction pipeline
- [x] XGBoost Tier 1 detector
- [x] TabNet Tier 2 detector with history
- [x] Llama 3.1 visual analyzer (text-based)
- [x] Case management system
- [x] Adversarial RL cheater agent
- [x] Co-evolution training loop
- [x] Real-time detection dashboard in client
- [x] Cheat mode toggle for testing

### ⏳ Not Yet Implemented
- [ ] Actual video/frame analysis (currently text summaries)
- [ ] Dashboard React UI for Tier 3
- [ ] Database persistence (SQLAlchemy)
- [ ] Production deployment
- [ ] Real player data collection

---

## 8. Questions for Analysis

### AI/ML Improvements
1. **Llama 3.1 Usage**: Currently we convert frames to text. Should we use a vision model (Llama 3.2 Vision) for actual frame analysis? What would be the tradeoffs?

2. **Feature Engineering**: Are there better features for detecting wallhacks in a POMDP setting? Should we use temporal convolutions instead of hand-crafted features?

3. **TabNet vs Transformers**: Would a Transformer-based model provide better attention interpretation for anti-cheat?

### Verification Questions
4. **Detection Validation**: How can we verify the AI truly detects cheating vs learning spurious correlations? What's a good test methodology?

5. **Adversarial Robustness**: How can cheaters defeat our current detection? What's our biggest weakness?

### Game Improvements
6. **Visual Appeal**: The game is currently minimal ASCII-style. What visual/UX improvements would make it more engaging?

7. **Gameplay Depth**: What mechanics would make the cheater vs anti-cheat dynamic more interesting to observe?

### Live Demonstration
8. **Spectator Mode**: How should we visualize the cheater vs AI battle in real-time? What would be most educational?

### Roadmap
9. **Priority Order**: What should we build next for maximum learning value?

10. **Scaling**: How would this system need to change for a real game with 10,000+ players?

---

## 9. Code Structure

```
shadowgrid/
├── game/
│   ├── constants.py     # TileType, Direction, configs
│   ├── world.py         # Grid generation, visibility
│   ├── player.py        # Movement, stat tracking
│   └── lockstep.py      # Deterministic sync
├── server/
│   ├── main.py          # FastAPI app
│   ├── websocket.py     # Real-time comms
│   └── validator.py     # Input validation
├── client/
│   └── game_client.py   # Pygame + detection dashboard
├── anticheat/
│   ├── features/
│   │   ├── temporal.py  # 50 features
│   │   ├── heatmap.py   # Movement patterns
│   │   ├── vadnet.py    # Aim analysis
│   │   └── gnn.py       # Collusion detection
│   ├── tier1/
│   │   ├── model.py     # XGBoost
│   │   └── train.py     # Synthetic data
│   ├── tier2/
│   │   ├── tabnet.py    # TabNet + history
│   │   ├── visual.py    # Llama 3.1
│   │   └── integrator.py
│   └── tier3/
│       └── case_manager.py
├── adversarial/
│   ├── cheater_env.py   # Gymnasium env
│   ├── cheater_agent.py # PPO agent
│   └── coevolution.py   # Training loop
└── enforcement/
    ├── response.py      # Graduated penalties
    └── metrics.py       # Precision/Recall
```

---

## 10. Sample Detection in Action

### Normal Player Behavior
```
Detection Score: 3%
Tier 1 (XGBoost): 2%
Features:
  speed_violations: 0
  fog_violations: 0
  total_moves: 45
Reasons: ✓ No issues detected
```

### Cheater Behavior (Cheat Mode On)
```
Detection Score: 85%
Tier 1 (XGBoost): 68%
Features:
  speed_violations: 12
  fog_violations: 0
  total_moves: 89
Reasons:
  • Speed violations: 12
  • Inhuman input speed
  • Cheat mode active
```

---

*Document prepared for NotebookLM analysis - January 2026*
