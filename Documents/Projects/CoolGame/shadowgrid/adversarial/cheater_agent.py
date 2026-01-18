"""
ShadowGrid Cheater Agent

Adversarial RL agent that learns to cheat while evading detection.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False
    PPO = None
    BaseCallback = object

from .cheater_env import CheaterEnv


class DetectabilityCallback(BaseCallback):
    """Callback to track detectability during training."""
    
    def __init__(self, verbose: int = 0):
        super().__init__(verbose)
        self.detectabilities = []
        self.rewards = []
    
    def _on_step(self) -> bool:
        # Get detectability from info
        infos = self.locals.get('infos', [])
        for info in infos:
            if 'detectability' in info:
                self.detectabilities.append(info['detectability'])
            if 'game_reward' in info:
                self.rewards.append(info['game_reward'])
        
        return True
    
    def get_stats(self) -> dict:
        """Get training statistics."""
        if not self.detectabilities:
            return {}
        
        return {
            'avg_detectability': np.mean(self.detectabilities[-100:]),
            'min_detectability': np.min(self.detectabilities[-100:]),
            'avg_game_reward': np.mean(self.rewards[-100:]) if self.rewards else 0
        }


class CheaterAgent:
    """
    PPO-based cheater agent.
    
    Learns to:
    1. Play the game effectively (maximize score)
    2. Avoid detection (minimize detectability)
    3. Use stealth mode strategically
    """
    
    PPO_PARAMS = {
        'learning_rate': 3e-4,
        'n_steps': 2048,
        'batch_size': 64,
        'n_epochs': 10,
        'gamma': 0.99,
        'gae_lambda': 0.95,
        'clip_range': 0.2,
        'ent_coef': 0.01,
        'vf_coef': 0.5,
        'max_grad_norm': 0.5
    }
    
    def __init__(
        self,
        env: CheaterEnv,
        model_path: Optional[str] = None,
        params: Optional[dict] = None
    ):
        if not SB3_AVAILABLE:
            raise ImportError(
                "stable-baselines3 is required for cheater agent. "
                "Install with: pip install stable-baselines3"
            )
        
        self.env = env
        self.model_path = model_path
        self.params = {**self.PPO_PARAMS, **(params or {})}
        
        self.model: Optional[PPO] = None
        self.callback = DetectabilityCallback()
        
        if model_path and os.path.exists(model_path):
            self.load(model_path)
        else:
            self.model = PPO(
                "MlpPolicy",
                self.env,
                verbose=1,
                **self.params
            )
    
    def train(
        self,
        total_timesteps: int = 100000,
        save_freq: int = 10000
    ) -> dict:
        """
        Train the cheater agent.
        
        Args:
            total_timesteps: Total training steps
            save_freq: Steps between model saves
            
        Returns:
            Training statistics
        """
        self.callback = DetectabilityCallback()
        
        # Train
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=self.callback
        )
        
        # Save if path specified
        if self.model_path:
            self.save(self.model_path)
        
        return {
            'timesteps': total_timesteps,
            **self.callback.get_stats()
        }
    
    def predict(
        self,
        observation: np.ndarray,
        deterministic: bool = True
    ) -> tuple:
        """
        Get action for observation.
        
        Args:
            observation: Environment observation
            deterministic: Whether to use deterministic policy
            
        Returns:
            (action, state)
        """
        action, state = self.model.predict(
            observation,
            deterministic=deterministic
        )
        return action, state
    
    def evaluate(
        self,
        n_episodes: int = 10
    ) -> dict:
        """
        Evaluate agent performance.
        
        Returns:
            Dict with performance metrics
        """
        total_rewards = []
        total_crystals = []
        detectabilities = []
        wins = 0
        
        for _ in range(n_episodes):
            obs, _ = self.env.reset()
            done = False
            episode_reward = 0
            
            while not done:
                action, _ = self.predict(obs)
                obs, reward, terminated, truncated, info = self.env.step(action)
                done = terminated or truncated
                episode_reward += reward
            
            total_rewards.append(episode_reward)
            total_crystals.append(info.get('crystals_collected', 0))
            detectabilities.append(info.get('detectability', 0))
            
            if info.get('crystals_remaining', 1) == 0:
                wins += 1
        
        return {
            'avg_reward': np.mean(total_rewards),
            'std_reward': np.std(total_rewards),
            'avg_crystals': np.mean(total_crystals),
            'avg_detectability': np.mean(detectabilities),
            'win_rate': wins / n_episodes
        }
    
    def get_behavior_sample(
        self,
        n_steps: int = 100
    ) -> list:
        """
        Get sample of agent behavior for analysis.
        
        Returns:
            List of (observation, action, info) tuples
        """
        samples = []
        obs, _ = self.env.reset()
        
        for _ in range(n_steps):
            action, _ = self.predict(obs)
            next_obs, _, terminated, truncated, info = self.env.step(action)
            
            samples.append({
                'observation': obs.tolist(),
                'action': int(action),
                'info': info
            })
            
            if terminated or truncated:
                break
            
            obs = next_obs
        
        return samples
    
    def save(self, path: str) -> bool:
        """Save model to file."""
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.model.save(str(path))
            return True
        except Exception as e:
            print(f"Error saving cheater model: {e}")
            return False
    
    def load(self, path: str) -> bool:
        """Load model from file."""
        try:
            self.model = PPO.load(path, env=self.env)
            return True
        except Exception as e:
            print(f"Error loading cheater model: {e}")
            return False
    
    def update_detectability_lambda(self, new_lambda: float) -> None:
        """Update the detectability penalty weight."""
        self.env.detectability_lambda = new_lambda


class SimpleCheater:
    """
    Simple rule-based cheater for testing detection.
    
    Always takes optimal actions with no stealth.
    """
    
    def __init__(self, env: CheaterEnv):
        self.env = env
    
    def predict(self, observation: np.ndarray) -> tuple:
        """Get optimal action (no stealth)."""
        action = self.env.get_optimal_action()
        return action, None
    
    def evaluate(self, n_episodes: int = 10) -> dict:
        """Evaluate simple cheater."""
        total_rewards = []
        detectabilities = []
        
        for _ in range(n_episodes):
            obs, _ = self.env.reset()
            done = False
            episode_reward = 0
            
            while not done:
                action, _ = self.predict(obs)
                obs, reward, terminated, truncated, info = self.env.step(action)
                done = terminated or truncated
                episode_reward += reward
            
            total_rewards.append(episode_reward)
            detectabilities.append(info.get('detectability', 0))
        
        return {
            'avg_reward': np.mean(total_rewards),
            'avg_detectability': np.mean(detectabilities)
        }


class StealthyCheater:
    """
    Cheater that uses stealth mode when outside fog-of-war.
    """
    
    def __init__(self, env: CheaterEnv):
        self.env = env
    
    def predict(self, observation: np.ndarray) -> tuple:
        """Get action with stealth when needed."""
        base_action = self.env.get_optimal_action()
        
        # Check if we're moving toward something outside fog
        # If so, use stealth (action + 5)
        player_x = self.env.player.x
        player_y = self.env.player.y
        
        crystal_positions = [
            (x, y)
            for x in range(self.env.width)
            for y in range(self.env.height)
            if self.env.grid.get_tile(x, y).tile_type.value == 2  # CRYSTAL
        ]
        
        if crystal_positions:
            nearest = min(
                crystal_positions,
                key=lambda p: abs(p[0] - player_x) + abs(p[1] - player_y)
            )
            
            dist = abs(nearest[0] - player_x) + abs(nearest[1] - player_y)
            
            # Outside 3x3 visibility, use stealth
            if dist > 2:
                return base_action + 5, None
        
        return base_action, None
