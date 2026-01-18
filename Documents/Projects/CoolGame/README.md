# ShadowGrid 🎮🛡️

> A POMDP gridworld game with a sophisticated three-tier anti-cheat architecture that evolves through adversarial reinforcement learning.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the game server
python -m shadowgrid.server.main

# In another terminal, start the game client
python -m shadowgrid.client.game_client
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ShadowGrid                                │
├─────────────────────────────────────────────────────────────────┤
│  Game Layer                                                      │
│  ├── Gridworld with fog-of-war (POMDP)                          │
│  ├── Deterministic lockstep protocol                             │
│  └── WebSocket real-time sync                                    │
├─────────────────────────────────────────────────────────────────┤
│  Anti-Cheat Layer                                                │
│  ├── Tier 1: XGBoost (client, high recall)                      │
│  ├── Tier 2: TabNet + Llama 3.1 Visual (server, high precision) │
│  └── Tier 3: Expert Dashboard (human review)                     │
├─────────────────────────────────────────────────────────────────┤
│  Adversarial Layer                                               │
│  ├── PPO Cheater Agent with stealth mode                        │
│  └── Co-evolution training loop                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Features

### Game Environment
- 🗺️ Procedurally generated 20x20 gridworld
- 👁️ 3x3 fog of war (partial observability)
- 🔥 Lava hazards, 💎 Crystal collectibles, 🚪 Exit goal
- ⚡ Real-time WebSocket multiplayer

### Anti-Cheat Detection

| Tier | Location | Model | Focus |
|------|----------|-------|-------|
| 1 | Client | XGBoost | High recall (catch all) |
| 2 | Server | TabNet + Llama 3.1 | High precision (reduce FP) |
| 3 | Dashboard | Human | Final verification |

**50+ Features Tracked:**
- Movement: velocity, acceleration, path straightness
- Timing: input frequency, reaction time variance
- Anomalies: teleports, speed violations, fog violations
- Patterns: behavioral entropy, knowledge anomalies

### Adversarial Testing
- 🤖 PPO-based cheater agent with full map visibility
- 🥷 Stealth mode to evade detection
- 🔄 Co-evolution training (cheater vs detector arms race)

## Usage

### Training the Tier 1 Detector

```bash
python -m shadowgrid.anticheat.tier1.train \
  --output models \
  --normal 5000 \
  --cheater 5000
```

### Running Co-Evolution Training

```bash
python -m shadowgrid.adversarial.coevolution \
  --iterations 20 \
  --cheater-steps 50000 \
  --save-dir models/coevolution
```

### Starting the Dashboard

```bash
cd dashboard
npm install
npm run dev
```

## Environment Variables

```env
GROQ_API_KEY=your_groq_api_key  # For Tier 2 visual analysis
```

## Project Structure

```
shadowgrid/
├── game/           # Core game: world, player, lockstep
├── server/         # FastAPI server + WebSocket
├── client/         # Pygame client
├── anticheat/      # Detection systems
│   ├── features/   # Feature extraction
│   ├── tier1/      # XGBoost detector
│   ├── tier2/      # TabNet + Visual
│   └── tier3/      # Case management
├── adversarial/    # RL cheater training
├── enforcement/    # Penalties + metrics
└── database/       # Data persistence
```

## License

MIT
