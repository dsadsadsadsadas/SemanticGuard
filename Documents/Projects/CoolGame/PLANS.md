# PLANS.md - ShadowGrid Module Roadmap

> **Rule**: Every module gets ✅ only after BOTH of us confirm it's working.

---

## ✅ COMPLETED MODULES

### ✅ MODULE 1: Core Game Environment
- Grid world with procedural generation
- Player movement and collision
- Lava damage, crystal collection, exit goal
- Fog-of-war (3×3 POMDP visibility)

### ✅ MODULE 2: Server Architecture  
- FastAPI REST endpoints
- WebSocket real-time communication
- Lockstep deterministic sync protocol
- Input validation

### ✅ MODULE 3: Client Rendering
- Pygame client with fog rendering
- Smooth movement animation
- Death screen + restart (R key)
- Safe spawn (no lava)

### ✅ MODULE 4: Feature Engineering
- 50 temporal features (velocity, timing, anomalies)
- Heatmap generator for movement patterns
- VADNet for decision analysis
- GNN structure for collusion detection

### ✅ MODULE 5: Tier 1 - XGBoost Detector
- High-recall XGBoost model
- Synthetic data generator (speedhack, wallhack, aimbot, macro)
- Training pipeline

### ✅ MODULE 6: Tier 2 - TabNet + Visual
- TabNet with attention (66 features)
- Player history integration
- Llama 3.1 text-based replay analysis
- Score integration and verdict

### ✅ MODULE 7: Tier 3 - Case Management
- Priority-based case queue
- Status tracking (pending → banned)
- Evidence attachment
- Statistics tracking

### ✅ MODULE 8: Adversarial RL
- Cheater environment (full observability)
- PPO agent with stealth mode
- Co-evolution training loop

### ✅ MODULE 9: Enforcement System
- Graduated response (warning → perm ban)
- Shadow ban pool
- Precision/Recall/AUC metrics

### ✅ MODULE 10: Detection Dashboard
- Real-time detection score display
- Feature values visualization
- Cheat mode toggle (C key)
- Dashboard toggle (D key)

### ✅ MODULE 11: Database Persistence
- SQLAlchemy async models (Player, Session, Case, DetectionEvent)
- PlayerRepository with 16 history features for Tier 2
- SessionRepository with replay saving
- SQLite default, configurable via DATABASE_URL
- **Integration**: Server initializes DB, tracks sessions, saves stats on disconnect

---

## 🔲 PENDING MODULES (Priority Order)

### ✅ MODULE 12: Tier 3 Dashboard UI
**Status**: COMPLETED ✅
- React/Vite dashboard with dark theme
- Case list with real API integration (auto-refresh 5s)
- Evidence viewer with animated replay
- Ban/Clear action buttons

### 🔲 MODULE 13: Split-View Spectator Mode
**Priority**: HIGH (educational visualization)
- Player view (3×3 fog)
- Server truth (full grid)
- AI confidence heatmap overlay
- Real-time feature importance bars

### 🔲 MODULE 14: Temporal Neural Detection
**Priority**: MEDIUM (better wallhack detection)
- LSTM/RNN for temporal patterns
- Replace static features with sequences
- Transformer-based AntiCheatPT option

### 🔲 MODULE 15: Vision Model Integration
**Priority**: MEDIUM (better visual analysis)
- Llama 3.2 Vision or VADNet
- Actual frame analysis (not text summaries)
- Spatial correlation detection

### 🔲 MODULE 16: Anti-Mimicry Defense
**Priority**: MEDIUM (adversarial robustness)
- Detect toggling behavior
- Long-term pattern analysis
- "Lucky player" vs cheater distinction

### 🔲 MODULE 17: Visual Upgrade
**Priority**: MEDIUM (engagement)
- 2D sprites instead of SDL rectangles
- Movement heatmap visualization
- Particle effects (lava, crystals)

### 🔲 MODULE 18: Social Mechanics & GNN
**Priority**: LOW (collusion detection)
- Decoy items requiring coordination
- Trade/interaction system
- GNN for social graph analysis

### 🔲 MODULE 19: Distributed Architecture
**Priority**: LOW (scaling to 10k+ players)
- Microservices separation
- Kafka event processing
- Bulkhead failure isolation

### 🔲 MODULE 20: Explainable AI (XAI)
**Priority**: LOW (validation)
- Explainer module for each tier
- Correlation vs causation tests
- False positive analysis tools

---

## Progress Tracker

| Category | Done | Total | Percentage |
|----------|------|-------|------------|
| Core Game | 3 | 3 | 100% |
| Anti-Cheat | 4 | 7 | 57% |
| Adversarial | 1 | 2 | 50% |
| Infrastructure | 2 | 5 | 40% |
| **TOTAL** | **10** | **20** | **50%** |

---

*Last updated: 2026-01-16*
