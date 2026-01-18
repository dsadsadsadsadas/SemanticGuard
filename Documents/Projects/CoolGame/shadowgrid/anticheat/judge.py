import os
import json
import asyncio
from groq import AsyncGroq

class Tier3Judge:
    def __init__(self):
        # Load API Key from .env manually to ensure it works
        self.api_key = os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            try:
                with open(".env", "r") as f:
                    for line in f:
                        if line.startswith("GROQ_API_KEY="):
                            self.api_key = line.split("=", 1)[1].strip()
                            break
            except:
                pass

        self.client = None
        if self.api_key:
            try:
                self.client = AsyncGroq(api_key=self.api_key)
                print("⚖️ Tier 3 Judge: Online (Groq Client Initialized)")
            except Exception as e:
                print(f"⚠️ Tier 3 Judge: Init Failed ({e})")
        else:
            print("⚠️ WARNING: Tier 3 Judge disabled (No GROQ_API_KEY found)")

    async def analyze_behavior(self, player_id, metrics):
        """
        metrics: dict containing variance, win_rate, tier2_score, movement_history
        """
        if not self.client:
            return {"verdict": "SKIPPED", "reason": "No API Key"}

        # Construct the Case File for the LLM
        prompt = f"""
        You are an elite Anti-Cheat Analyst. Analyze this player's data for 'Smurfing' or 'Deceptive Cheating'.
        
        PLAYER DATA:
        - ID: {player_id}
        - Suspicion Score (Tier 2): {metrics.get('tier2_score'):.1f}%
        - Move Variance: {metrics.get('variance'):.4f} (Low < 0.10 is robotic)
        - Behavior Profile: Player falls in the 'Gray Zone' (40-80% suspicion).
        
        TASK:
        Determine if this player is:
        1. CLEAN (Legitimate human)
        2. SMURF (High skill player intentionally playing bad to lower rank/suspicion)
        3. CHEATER (Using software assistance logic)
        
        CONTEXT: 
        - Smurfs often have moments of robotic precision mixed with inexplicable errors.
        - Cheaters often have inhumanly low variance (< 0.05).
        
        Return JSON ONLY: {{"verdict": "CLEAN"|"SMURF"|"CHEATER", "reason": "brief explanation"}}
        """

        try:
            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a JSON-only Anti-Cheat system. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                model="llama3-70b-8192",
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            content = chat_completion.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"❌ GROQ ERROR: {e}")
            return {"verdict": "ERROR", "reason": str(e)}
