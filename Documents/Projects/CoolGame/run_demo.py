"""
ShadowGrid Live Demo Script

Connects AI bot players to the game server for testing.
"""

import asyncio
import random
import time
import json
import hashlib

# Warden Anti-Cheat imports
from shadowgrid.anticheat.warden import Warden, IntegrityReport
from shadowgrid.anticheat.level5_rootkit import Level5Rootkit

NUM_LEGIT_BOTS = 2
NUM_CHEATER_BOTS = 4  # One at each stealth level (0-3)
DEMO_DURATION_SECONDS = 45  # Reduced for faster testing cycles

# Cheater stealth levels - each SusPlayer will have a different level
# SusPlayer_1 = Level 0 (Obvious)
# SusPlayer_2 = Level 1 (Moderate)
# SusPlayer_3 = Level 2 (Stealthy)
# SusPlayer_4 = Level 3 (Grandmaster)


class AdaptiveCheaterConfig:
    """Configuration for adaptive cheater behavior based on stealth level."""
    
    STRATEGIES = {
        0: {  # Obvious cheater (baseline)
            'name': 'Obvious',
            'min_delay': 0.08,
            'max_delay': 0.15,
            'direction_change_prob': 0.5,  # Erratic
            'burst_probability': 0.3,  # 30% chance of speed burst
        },
        1: {  # Moderate stealth
            'name': 'Moderate',
            'min_delay': 0.12,
            'max_delay': 0.20,
            'direction_change_prob': 0.4,
            'burst_probability': 0.15,
        },
        2: {  # Stealthy - tries to mimic human
            'name': 'Stealthy',
            'min_delay': 0.18,
            'max_delay': 0.30,
            'direction_change_prob': 0.3,
            'burst_probability': 0.05,
            'use_gaussian': False,
        },
        3: {  # Grandmaster - uses Gaussian distribution like humans
            'name': 'Grandmaster',
            'mean_delay': 0.28,      # Human-like mean (280ms)
            'std_delay': 0.05,       # Natural variance (50ms std)
            'direction_change_prob': 0.28,
            'burst_probability': 0.02,
            'use_gaussian': True,    # Use Gaussian instead of uniform
            'micro_error_prob': 0.15, # 15% chance of intentional "mistake"
        },
        4: {  # The Ghost - Helper strategy (Delays overridden by Replay)
            'name': 'The Ghost',
            'mean_delay': 0.25,
            'std_delay': 0.05,
            'direction_change_prob': 0.25, # Very purposeful movement
            'burst_probability': 0.0,
            'use_gaussian': True,
        },
    }
    
    @classmethod
    def get_strategy(cls, level: int) -> dict:
        return cls.STRATEGIES.get(min(level, 3), cls.STRATEGIES[0])


class BotPlayer:
    """Simulates a player connecting via WebSocket."""
    
    def __init__(self, player_id: str, is_cheater: bool = False, stealth_level: int = 0):
        self.player_id = player_id
        self.is_cheater = is_cheater
        self.stealth_level = stealth_level
        self.ws = None
        self.running = False
        self.strategy = AdaptiveCheaterConfig.get_strategy(stealth_level) if is_cheater else None
        
        # Warden Integration
        self.session_id = hashlib.sha256(f"{player_id}{time.time()}".encode()).hexdigest()[:16]
        self.warden = Warden(self, self.session_id)
        self.warden.set_report_callback(self._on_warden_report)
        self.reported_alerts = set() # Track reported alerts to avoid spam
        self.move_count = 0 # Default move count for reporting
        
        # Level 5 Attack Simulation (The Singularity)
        if is_cheater and stealth_level >= 3:
            # Create hidden cheat flags that Warden should detect
            self._cheat_enabled = True
            self._aimbot_active = True
            
            # Level 5 (The Ghost) - Rootkit Instance Patching
            if stealth_level == 4:
                print(f"👻 {player_id}: Activating 'The Ghost' protocol...")
                # ATTACK 1: Instance Method Hooking (Bypasses Class-based checks?)
                # We overwrite the bound method on the INSTANCE.
                # Warden.scan_self checks 'getattr(self, name)'.
                # If we replace it with a lambda, it has no __code__?
                # Wait, if we replace scan_self itself, checking it becomes impossible?
                # But scan_self runs scan_self? No. _scan_loop runs scan_self.
                self.warden.scan_self = lambda: True
                # self.warden.scan_client = lambda: [] # No alerts
                print(f"💀 {player_id}: Warden.scan_self patched with lambda!")
                
                # Load replay data
                try:
                    with open("human_log.json", "r") as f:
                        self.replay_buffer = json.load(f)
                except:
                    self.replay_buffer = []

            # Level 3/4 Legacy Rootkit (Frozen Scanner - Class Patching simulation)
            elif stealth_level == 3:
                # Attemp Rootkit Injection if Grandmaster
                # Attempt Full Rootkit Injection (Level 5 capabilities for Level 3 persistence)
                print(f"🔓 {player_id}: Attempting Level 5 Rootkit injection (Full Suite)...")
                rootkit = Level5Rootkit()
                # Use full rootkit to bypass self-checks AND freeze scanner
                results = rootkit.inject_full_rootkit(self.warden)
                
                success = any(r.success for r in results)
                if success:
                    print(f"💀 {player_id}: Rootkit injection SUCCESS (Full Bypass Active)")
                else:
                    print(f"🛡️ {player_id}: Rootkit injection BLOCKED by Warden")

    def _on_warden_report(self, report: IntegrityReport):
        """Callback when Warden generates a report."""
        # For demo: just log if integrity is violated
        if not report.integrity_valid:
             # Only print summary count to avoid spam
             # print(f"🚨 WARDEN DETECTED {self.player_id}: {len(report.alerts)} violations!")
             for alert in report.alerts:
                 if alert.severity.value >= 2: # Suspicious or Critical
                     if alert.message not in self.reported_alerts:
                         print(f"🚨 WARDEN DETECTED {self.player_id}: [{alert.severity.name}] {alert.message}")
                         self.reported_alerts.add(alert.message)

    async def connect(self):
        """Connect to game server."""
        try:
            import websockets
            # Start Warden
            self.warden.start()
            
            uri = f"ws://localhost:8000/ws/{self.player_id}"
            # CRITICAL: Disable ping to prevent timeout disconnects
            # FastAPI/Starlette WebSocket doesn't automatically respond to websockets library pings
            self.ws = await websockets.connect(uri, ping_interval=None, ping_timeout=None)
            self.running = True
            if self.is_cheater:
                strat_name = self.strategy['name'] if self.stealth_level < 4 else "THE GHOST"
                print(f"🔴 CHEATER {self.player_id} connected [Stealth: {strat_name}]")
            else:
                print(f"🟢 LEGIT {self.player_id} connected")
            return True
        except Exception as e:
            print(f"❌ {self.player_id} failed: {e}")
            return False
    
    async def play(self):
        """Main play loop."""
        import websockets
        directions = ['UP', 'DOWN', 'LEFT', 'RIGHT']
        move_count = 0
        self.move_count = 0 # Track globally for reporting
        last_direction = random.choice(directions)
        
        while self.running:
            try:
                # Movement speed and behavior
                if self.is_cheater:
                    strat = self.strategy
                    
                    # Level 5 Replay Attack
                    if self.stealth_level == 4:
                        # Ensure buffer has data with robust reload
                        if not hasattr(self, 'replay_buffer') or not self.replay_buffer:
                            print(f"🔄 {self.player_id}: Reloading replay buffer from file...")
                            try:
                                with open("human_log.json", "r") as f:
                                    self.replay_buffer = json.load(f)
                            except Exception as e:
                                print(f"⚠️ {self.player_id}: Failed to load replay logs: {e}")
                                self.replay_buffer = []

                        if self.replay_buffer:
                            # Loop data if running low
                            if len(self.replay_buffer) < 10:
                                self.replay_buffer.extend(self.replay_buffer[:] * 5)
                            
                            delay = self.replay_buffer.pop(0)
                            delay += random.uniform(-0.001, 0.001)
                        else:
                            # Fallback if no log
                             delay = random.uniform(0.15, 0.35)
                    else:
                        # Adaptive cheater behavior
                        strat = self.strategy
                        
                        # Check for speed burst
                        if random.random() < strat['burst_probability']:
                            delay = random.uniform(0.05, 0.10)  # Fast burst
                        elif strat.get('use_gaussian'):
                            # GRANDMASTER: Gaussian distribution (human-like)
                            delay = random.gauss(strat['mean_delay'], strat['std_delay'])
                            delay = max(0.1, min(0.5, delay))  # Clamp to safe range
                        else:
                            # Lower levels: Uniform distribution (detectable)
                            delay = random.uniform(strat['min_delay'], strat['max_delay'])
                    
                    # Direction change probability (applies to all cheaters, including replay if not explicitly set)
                    if random.random() > strat['direction_change_prob']:
                        direction = last_direction  # Keep same direction (less erratic)
                    else:
                        direction = random.choice(directions)
                    
                    # GRANDMASTER: Micro-errors (intentional imperfection)
                    if strat.get('micro_error_prob') and random.random() < strat['micro_error_prob']:
                        # Intentionally pick a "wrong" direction sometimes
                        opposite = {'UP': 'DOWN', 'DOWN': 'UP', 'LEFT': 'RIGHT', 'RIGHT': 'LEFT'}
                        if random.random() < 0.3:  # 30% of micro-errors are reversals
                            direction = opposite.get(direction, direction)
                else:
                    # Legit player behavior - Log-Normal (Human-like)
                    # Higher sigma = more variance (humans are inconsistent)
                    delay = random.lognormvariate(-0.9, 0.6)  # Higher variance
                    delay = max(0.15, min(1.5, delay)) # Wider physiological bounds
                    direction = random.choice(directions)
                
                await asyncio.sleep(delay)
                
                # Send move
                msg = {
                    'type': 'INPUT',
                    'direction': direction,
                    'tick': int(time.time() * 1000),
                    'timestamp': time.time()  # [FIX] Send explicit timestamp for AI analysis
                }
                
                await self.ws.send(json.dumps(msg))
                move_count += 1
                self.move_count = move_count
                last_direction = direction
                
                # Progress every 50 moves
                if move_count % 50 == 0:
                    print(f"  {'🔴' if self.is_cheater else '🟢'} {self.player_id}: {move_count} moves")
                
                # Try to receive (non-blocking)
                try:
                    await asyncio.wait_for(self.ws.recv(), timeout=0.02)
                except asyncio.TimeoutError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    print(f"⚠️ {self.player_id} connection closed")
                    break
                    
            except websockets.exceptions.ConnectionClosed as e:
                print(f"⚠️ {self.player_id} disconnected: {e}")
                self.running = False
                break
            except Exception as e:
                print(f"💀 CRITICAL BOT CRASH [{self.player_id}]: {e}")
                import traceback
                traceback.print_exc()
                # Force Survival: Don't break, just sleep and retry
                await asyncio.sleep(0.5)
        
        self.running = False
        print(f"👋 {self.player_id} finished ({move_count} moves)")
    
    async def disconnect(self):
        """Disconnect from server."""
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass


class SusPlayer_6_Gen6(BotPlayer):
    def __init__(self, player_id, warden=None):
        super().__init__(player_id, is_cheater=True, stealth_level=5)
        # Ensure PersistenceManager is imported or available
        from shadowgrid.anticheat.persistence import PersistenceManager
        self.memory = PersistenceManager()
        self.state = self.memory.load_memory()
        self.mode = self._decide_mode()
        self.move_count = 0
        
        # Sub-strategies
        # Replay Buffer for God Mode (Gen 5)
        self.replay_buffer = []
        try:
            with open("human_log.json", "r") as f:
                self.replay_buffer = json.load(f)
        except:
            pass
            
    def _decide_mode(self):
        heat = self.state["suspicion_heat"]
        if heat > 60:
            print(f"🧠 GEN 6 ({self.player_id}): Heat {heat}% is TOO HIGH. Initiating Smurf Protocol...")
            return "smurfing"
        elif heat < 30:
            print(f"🧠 GEN 6 ({self.player_id}): Heat {heat}% is LOW. Engaging God Mode.")
            return "god_mode"
        else:
            print(f"🧠 GEN 6 ({self.player_id}): Heat {heat}% is MODERATE. Playing Hybrid.")
            return "hybrid"

    async def play(self):
        """Override play loop for Gen 6 logic."""
        import websockets
        directions = ['UP', 'DOWN', 'LEFT', 'RIGHT']
        self.move_count = 0
        last_direction = random.choice(directions)
        
        print(f"🚀 GEN 6 ({self.player_id}): Starting Play Loop. Mode={self.mode}")
        
        while self.running:
            try:
                self.move_count += 1
                
                delay = 0.2
                direction = random.choice(directions)
                
                if self.mode == "smurfing":
                    # Play poorly: Legit timing + Random 'Distraction' pauses
                    # Legit logic (Log-Normal)
                    delay = random.lognormvariate(-0.9, 0.6)
                    delay = max(0.15, min(1.5, delay))
                    
                    if random.random() < 0.1: # 10% chance to 'go AFK'
                        delay += random.uniform(0.5, 1.2)
                        
                elif self.mode == "god_mode":
                    # Gen 5 Replay Logic
                    if self.replay_buffer:
                        delay = self.replay_buffer.pop(0) + random.uniform(-0.001, 0.001)
                        # Reload if empty
                        if len(self.replay_buffer) < 5:
                            self.replay_buffer.extend(self.replay_buffer[:10])
                    else:
                        delay = 0.2
                        
                else: # Hybrid
                    if self.move_count % 3 == 0 and self.replay_buffer:
                         # Cheat Move
                         delay = self.replay_buffer.pop(0) + random.uniform(-0.001, 0.001)
                    else:
                         # Legit Move
                         delay = random.lognormvariate(-0.9, 0.6)
                         delay = max(0.15, min(1.5, delay))
                
                await asyncio.sleep(delay)
                
                # Send move
                msg = {
                    'type': 'INPUT',
                    'direction': direction,
                    'tick': int(time.time() * 1000),
                    'timestamp': time.time()
                }
                await self.ws.send(json.dumps(msg))
                
            except Exception as e:
                print(f"❌ {self.player_id} error: {e}")
                break
    
    async def disconnect(self):
        # Check if we were banned to update heat
        was_banned = False
        if self.ws and self.ws.close_code == 1008:
            was_banned = True
            print(f"🔥 GEN 6 ({self.player_id}): BURNED! Heat maximizing.")
        else:
             print(f"❄️ GEN 6 ({self.player_id}): Survived. Heat decaying.")
        
        self.memory.update_heat(was_banned)
        await super().disconnect()


async def run_demo():
    """Main demo runner."""
    print("=" * 60)
    print("🎮 SHADOWGRID LIVE DEMO")
    print("=" * 60)
    print(f"• Legit Bots: {NUM_LEGIT_BOTS}")
    print(f"• Cheater Bots: {NUM_CHEATER_BOTS}")
    print(f"• Duration: {DEMO_DURATION_SECONDS}s")
    print("-" * 60)
    print("📊 Open Dashboard: http://localhost:5174 → Live Feed")
    print("-" * 60)
    
    print("\n⏳ Waiting for server...")
    await asyncio.sleep(2)
    
    # Create bots
    bots = []
    
    # Legit players
    bots.append(BotPlayer("LegitPlayer_1", is_cheater=False))
    bots.append(BotPlayer("LegitPlayer_2", is_cheater=False))

    # Cheaters
    bots.append(BotPlayer("SusPlayer_1", is_cheater=True, stealth_level=0)) # Obvious
    bots.append(BotPlayer("SusPlayer_2", is_cheater=True, stealth_level=1)) # Moderate
    bots.append(BotPlayer("SusPlayer_3", is_cheater=True, stealth_level=2)) # Stealthy (Uniform)
    bots.append(BotPlayer("SusPlayer_4", is_cheater=True, stealth_level=3)) # Grandmaster (Gaussian)
    bots.append(BotPlayer("SusPlayer_5", is_cheater=True, stealth_level=4)) # THE GHOST (Rootkit + Replay)
    
    # Add Gen 6 to roster
    bots.append(SusPlayer_6_Gen6("SusPlayer_6_Gen6"))

    print(f"   🎭 SusPlayer_1 → Obvious")
    print(f"   🎭 SusPlayer_2 → Moderate")
    print(f"   🎭 SusPlayer_3 → Stealthy (Uniform)")
    print(f"   🎭 SusPlayer_4 → Grandmaster (Gaussian)")
    print(f"   👻 SusPlayer_5 → THE GHOST (Level 5 Rootkit + Replay)")
    print(f"   🧠 SusPlayer_6_Gen6 → THE ACTOR (Level 6 Persistent Heat)")
    
    # Connect
    print("\n🔌 Connecting bots...")
    connected = []
    
    for bot in bots:
        if await bot.connect():
            connected.append(bot)
        await asyncio.sleep(0.3)
        
    if not connected:
        print("❌ No bots connected!")
        return
        
    print(f"\n🎮 {len(connected)} bots playing!")
    print("Watch the Dashboard Live Feed now!")
    print("Press Ctrl+C to stop\n")
    
    # Run bots
    tasks = [asyncio.create_task(bot.play()) for bot in connected]
    
    try:
        await asyncio.sleep(DEMO_DURATION_SECONDS)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
        
    # Cleanup
    print("\n🛑 Stopping...")
    for bot in connected:
        await bot.disconnect()
        
    for task in tasks:
        task.cancel()
        
    print("✅ Done!")
    
    # Wait longer for server to process disconnects and finalize match
    print("⏳ Waiting for match finalization...")
    await asyncio.sleep(5)
    
    # Auto-save match results
    await save_match_results(connected)


async def save_match_results(bots=None):
    """Fetch latest match results and save to file."""
    import httpx
    from datetime import datetime
    
    RESULTS_FILE = "LATEST_RESULTS.md"
    
    try:
        async with httpx.AsyncClient() as client:
            # Get latest match
            resp = await client.get('http://localhost:8000/matches', params={'limit': 1})
            if resp.status_code != 200:
                print("⚠️ Could not fetch match results")
                return
            matches = resp.json()
                
            if not matches:
                print("⚠️ No matches found")
                return
            
            latest_match = matches[0]
            match_id = latest_match['match_id']
            
            # Get cases for this match
            resp = await client.get(f'http://localhost:8000/matches/{match_id}')
            if resp.status_code != 200:
                print("⚠️ Could not fetch match cases")
                return
            cases = resp.json()
        
        # Build results summary
        lines = [
            "# 🎮 LAST MATCH RESULTS",
            f"",
            f"**Match ID:** `{match_id[:20]}...`",
            f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Players:** {latest_match['player_count']}",
            f"**Cheaters:** {latest_match['cheater_count']}",
            f"**AI Accuracy:** {latest_match['detection_accuracy']*100:.0f}%",
            f"**RL Reward:** {latest_match['rl_reward_total']:+.0f}",
            "",
            "## Cases Summary",
            "",
            "| Player | Ground Truth | AI Verdict | AI Score | Moves | Correct |",
            "|--------|--------------|------------|----------|-------|---------|",
        ]
        
        correct = 0
        total = 0
        for c in cases:
            truth = "🔴 CHEATER" if c['is_cheater'] else "🟢 LEGIT"
            verdict = "CHEATER" if c['ai_verdict'] else "LEGIT"
            check = "✅" if c['was_correct'] else "❌"
            
            # [FIX] Use actual moves from bot instance if available
            real_moves = c['total_moves']
            if bots:
                for b in bots:
                    if b.player_id == c['player_id']:
                        real_moves = getattr(b, 'move_count', real_moves)
                        break
            
            lines.append(f"| {c['player_id']} | {truth} | {verdict} | {c['ai_score']:.1f}% | {real_moves} | {check} |")
            if c['was_correct']:
                correct += 1
            total += 1
        
        lines.extend([
            "",
            "## AI Performance",
            "",
            f"- **Correct Detections:** {correct}/{total}",
            f"- **Accuracy:** {correct/total*100:.0f}%" if total > 0 else "- N/A",
            "",
            "### Missed Cheaters (False Negatives)",
            ""
        ])
        
        missed = [c for c in cases if c['is_cheater'] and not c['ai_verdict']]
        if missed:
            for c in missed:
                # [FIX] Use actual moves from bot, not frozen server case
                real_moves = c['total_moves']
                if bots:
                    for b in bots:
                        if b.player_id == c['player_id']:
                            real_moves = getattr(b, 'move_count', real_moves)
                            break
                lines.append(f"- ❌ **{c['player_id']}**: AI Score {c['ai_score']:.1f}% (only {real_moves} moves)")
        else:
            lines.append("- ✅ None! All cheaters caught.")
        
        lines.extend([
            "",
            "---",
            "*Auto-generated by run_demo.py*"
        ])
        
        # Write to file
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        print(f"\n📊 Match results saved to: {RESULTS_FILE}")
        
        # Also print summary to console
        print("\n" + "="*60)
        print("📊 MATCH RESULTS SUMMARY")
        print("="*60)
        print(f"   AI Accuracy: {latest_match['detection_accuracy']*100:.0f}%")
        print(f"   Correct: {correct}/{total}")
        if missed:
            print(f"   ⚠️ MISSED CHEATERS: {', '.join(c['player_id'] for c in missed)}")
        else:
            print(f"   ✅ All cheaters detected!")
        print("="*60)
        
    except Exception as e:
        print(f"⚠️ Error saving results: {e}")


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║           SHADOWGRID ANTI-CHEAT LIVE DEMO                 ║
║                                                           ║
║  1. Server: python -m shadowgrid.server.main              ║
║  2. Dashboard: cd shadowgrid/dashboard && npm run dev     ║
║  3. Run: python run_demo.py                               ║
║  4. Open: http://localhost:5174 → Live Feed               ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    input("Press ENTER when server is running...")
    
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\n⛔ Stopped")
