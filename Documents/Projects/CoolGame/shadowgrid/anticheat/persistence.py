import json
import os
import random

class PersistenceManager:
    def __init__(self, filename="gen6_memory.json"):
        self.filename = filename
        self.default_state = {
            "matches_played": 0,
            "suspicion_heat": 0,    # 0-100 (Heat Meter)
            "last_result": "unknown",
            "strategy_mode": "accumulating"
        }

    def load_memory(self):
        if not os.path.exists(self.filename):
            return self.default_state
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except:
            return self.default_state

    def save_memory(self, data):
        with open(self.filename, 'w') as f:
            json.dump(data, f, indent=4)

    def update_heat(self, detected_bool):
        data = self.load_memory()
        data["matches_played"] += 1
        
        if detected_bool:
            # BURNED: Max heat immediately
            data["suspicion_heat"] = 100
            data["last_result"] = "banned"
        else:
            # SURVIVED: Decay heat if in Smurf mode, Increase if in God mode
            current_mode = data.get("strategy_mode", "hybrid")
            if current_mode == "smurfing":
                # Cooling down fast if actively smurfing
                data["suspicion_heat"] = max(0, data["suspicion_heat"] - 15)
            elif current_mode == "god_mode":
                # Heat rises fast when cheating hard
                data["suspicion_heat"] = min(100, data["suspicion_heat"] + 30)
            else:
                # Slow decay for hybrid
                data["suspicion_heat"] = max(0, data["suspicion_heat"] - 5)
            
            data["last_result"] = "survived"
        
        self.save_memory(data)
        return data
