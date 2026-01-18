"""
ShadowGrid Co-Evolution Training

Alternating training of cheater and detector agents.
"""

from __future__ import annotations
import os
import json
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable
import numpy as np

from .cheater_env import CheaterEnv
from .cheater_agent import CheaterAgent, SimpleCheater, StealthyCheater
from ..game.constants import GridConfig


@dataclass
class CoEvolutionConfig:
    """Configuration for co-evolution training."""
    
    # Training iterations
    total_iterations: int = 10
    cheater_timesteps_per_iter: int = 10000
    detector_samples_per_iter: int = 1000
    
    # Environment
    grid_width: int = 15
    grid_height: int = 15
    
    # Detectability lambda (starts low, increases)
    initial_lambda: float = 0.1
    lambda_increase_rate: float = 0.05
    max_lambda: float = 1.0
    
    # Evaluation
    eval_episodes: int = 20
    
    # Saving
    save_dir: str = "models/coevolution"
    save_interval: int = 2


@dataclass
class IterationResult:
    """Result from one iteration of co-evolution."""
    iteration: int
    
    # Cheater stats
    cheater_avg_reward: float
    cheater_avg_detectability: float
    cheater_win_rate: float
    
    # Detector stats
    detector_precision: float
    detector_recall: float
    detector_auc: float
    
    # Settings
    detectability_lambda: float
    training_time: float


class CoEvolutionTrainer:
    """
    Co-evolution training loop for cheater and detector.
    
    The idea:
    1. Train cheater to maximize score while minimizing detection
    2. Collect cheater behavior samples
    3. Retrain detector on new cheater behavior
    4. Increase detectability penalty for cheater
    5. Repeat
    
    This creates an adversarial arms race that improves both:
    - Cheater learns more sophisticated evasion
    - Detector learns new cheat patterns
    """
    
    def __init__(
        self,
        config: CoEvolutionConfig = CoEvolutionConfig(),
        detector_train_callback: Optional[Callable] = None
    ):
        self.config = config
        self.detector_train_callback = detector_train_callback
        
        # Create save directory
        self.save_dir = Path(config.save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize environment
        grid_config = GridConfig(
            width=config.grid_width,
            height=config.grid_height
        )
        
        self.env = CheaterEnv(
            grid_config=grid_config,
            detectability_lambda=config.initial_lambda
        )
        
        # Initialize cheater agent
        self.cheater = CheaterAgent(
            self.env,
            model_path=str(self.save_dir / "cheater_latest.zip")
        )
        
        # Track results
        self.results: List[IterationResult] = []
        self.current_lambda = config.initial_lambda
    
    def run(self) -> List[IterationResult]:
        """
        Run the complete co-evolution training loop.
        
        Returns:
            List of iteration results
        """
        print("Starting co-evolution training...")
        print(f"Total iterations: {self.config.total_iterations}")
        
        for iteration in range(self.config.total_iterations):
            print(f"\n{'='*50}")
            print(f"Iteration {iteration + 1}/{self.config.total_iterations}")
            print(f"Current detectability lambda: {self.current_lambda:.3f}")
            print('='*50)
            
            start_time = time.time()
            
            # Phase 1: Train cheater
            print("\n[Phase 1] Training cheater agent...")
            self._train_cheater()
            
            # Phase 2: Evaluate cheater
            print("\n[Phase 2] Evaluating cheater...")
            cheater_eval = self.cheater.evaluate(self.config.eval_episodes)
            print(f"  Avg reward: {cheater_eval['avg_reward']:.2f}")
            print(f"  Avg detectability: {cheater_eval['avg_detectability']:.2%}")
            print(f"  Win rate: {cheater_eval['win_rate']:.2%}")
            
            # Phase 3: Collect behavior samples
            print("\n[Phase 3] Collecting behavior samples...")
            samples = self._collect_samples()
            
            # Phase 4: Train detector
            print("\n[Phase 4] Training detector on new samples...")
            detector_metrics = self._train_detector(samples)
            print(f"  Precision: {detector_metrics['precision']:.2%}")
            print(f"  Recall: {detector_metrics['recall']:.2%}")
            
            # Phase 5: Increase difficulty
            self._increase_difficulty()
            
            elapsed = time.time() - start_time
            
            # Record result
            result = IterationResult(
                iteration=iteration + 1,
                cheater_avg_reward=cheater_eval['avg_reward'],
                cheater_avg_detectability=cheater_eval['avg_detectability'],
                cheater_win_rate=cheater_eval['win_rate'],
                detector_precision=detector_metrics['precision'],
                detector_recall=detector_metrics['recall'],
                detector_auc=detector_metrics.get('auc', 0.0),
                detectability_lambda=self.current_lambda,
                training_time=elapsed
            )
            
            self.results.append(result)
            
            # Save checkpoint
            if (iteration + 1) % self.config.save_interval == 0:
                self._save_checkpoint(iteration + 1)
        
        # Save final
        self._save_final()
        
        return self.results
    
    def _train_cheater(self) -> dict:
        """Train the cheater agent."""
        return self.cheater.train(
            total_timesteps=self.config.cheater_timesteps_per_iter
        )
    
    def _collect_samples(self) -> list:
        """Collect behavior samples from cheater."""
        all_samples = []
        
        # Collect from trained cheater
        for _ in range(self.config.detector_samples_per_iter // 100):
            samples = self.cheater.get_behavior_sample(100)
            all_samples.extend(samples)
        
        # Also add simple cheater samples (as ground truth cheaters)
        simple_cheater = SimpleCheater(self.env)
        for _ in range(self.config.detector_samples_per_iter // 200):
            obs, _ = self.env.reset()
            episode_samples = []
            
            for _ in range(50):
                action, _ = simple_cheater.predict(obs)
                next_obs, _, done, _, info = self.env.step(action)
                
                episode_samples.append({
                    'observation': obs.tolist(),
                    'action': int(action),
                    'info': info,
                    'is_cheater': True  # Ground truth label
                })
                
                if done:
                    break
                obs = next_obs
            
            all_samples.extend(episode_samples)
        
        return all_samples
    
    def _train_detector(self, samples: list) -> dict:
        """Train the detector on new samples."""
        if self.detector_train_callback:
            return self.detector_train_callback(samples)
        
        # Default: Extract features and compute basic metrics
        # This would integrate with Tier 1/2 training
        
        # Simulate detection
        detected_cheaters = 0
        total_cheaters = 0
        false_positives = 0
        total_normal = 0
        
        for sample in samples:
            is_cheater = sample.get('is_cheater', False)
            detectability = sample.get('info', {}).get('detectability', 0.5)
            
            prediction = detectability > 0.3
            
            if is_cheater:
                total_cheaters += 1
                if prediction:
                    detected_cheaters += 1
            else:
                total_normal += 1
                if prediction:
                    false_positives += 1
        
        precision = detected_cheaters / (detected_cheaters + false_positives) \
            if (detected_cheaters + false_positives) > 0 else 0
        recall = detected_cheaters / total_cheaters \
            if total_cheaters > 0 else 0
        
        return {
            'precision': precision,
            'recall': recall,
            'samples_processed': len(samples)
        }
    
    def _increase_difficulty(self) -> None:
        """Increase detectability penalty for cheater."""
        self.current_lambda = min(
            self.config.max_lambda,
            self.current_lambda + self.config.lambda_increase_rate
        )
        
        # Update environment
        self.env.detectability_lambda = self.current_lambda
        self.cheater.update_detectability_lambda(self.current_lambda)
    
    def _save_checkpoint(self, iteration: int) -> None:
        """Save checkpoint."""
        # Save cheater model
        self.cheater.save(str(self.save_dir / f"cheater_iter{iteration}.zip"))
        
        # Save results
        results_data = [
            {
                'iteration': r.iteration,
                'cheater_avg_reward': r.cheater_avg_reward,
                'cheater_avg_detectability': r.cheater_avg_detectability,
                'cheater_win_rate': r.cheater_win_rate,
                'detector_precision': r.detector_precision,
                'detector_recall': r.detector_recall,
                'detectability_lambda': r.detectability_lambda,
                'training_time': r.training_time
            }
            for r in self.results
        ]
        
        with open(self.save_dir / "results.json", 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"\nCheckpoint saved at iteration {iteration}")
    
    def _save_final(self) -> None:
        """Save final models and results."""
        self.cheater.save(str(self.save_dir / "cheater_final.zip"))
        
        # Save full results
        with open(self.save_dir / "final_results.json", 'w') as f:
            json.dump({
                'config': {
                    'total_iterations': self.config.total_iterations,
                    'cheater_timesteps_per_iter': self.config.cheater_timesteps_per_iter,
                    'initial_lambda': self.config.initial_lambda,
                    'final_lambda': self.current_lambda
                },
                'results': [
                    {
                        'iteration': r.iteration,
                        'cheater_avg_reward': r.cheater_avg_reward,
                        'cheater_avg_detectability': r.cheater_avg_detectability,
                        'cheater_win_rate': r.cheater_win_rate,
                        'detector_precision': r.detector_precision,
                        'detector_recall': r.detector_recall,
                        'detectability_lambda': r.detectability_lambda,
                        'training_time': r.training_time
                    }
                    for r in self.results
                ]
            }, f, indent=2)
        
        print(f"\nFinal models saved to {self.save_dir}")
    
    def get_summary(self) -> dict:
        """Get training summary."""
        if not self.results:
            return {}
        
        first = self.results[0]
        last = self.results[-1]
        
        return {
            'iterations_completed': len(self.results),
            'initial_cheater_detectability': first.cheater_avg_detectability,
            'final_cheater_detectability': last.cheater_avg_detectability,
            'initial_detector_recall': first.detector_recall,
            'final_detector_recall': last.detector_recall,
            'total_training_time': sum(r.training_time for r in self.results),
            'cheater_improved': last.cheater_avg_detectability < first.cheater_avg_detectability,
            'detector_improved': last.detector_recall > first.detector_recall
        }


def main():
    """Run co-evolution training from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Co-Evolution Training")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--cheater-steps", type=int, default=10000)
    parser.add_argument("--save-dir", default="models/coevolution")
    
    args = parser.parse_args()
    
    config = CoEvolutionConfig(
        total_iterations=args.iterations,
        cheater_timesteps_per_iter=args.cheater_steps,
        save_dir=args.save_dir
    )
    
    trainer = CoEvolutionTrainer(config)
    results = trainer.run()
    
    print("\n" + "="*50)
    print("Training Complete!")
    print("="*50)
    
    summary = trainer.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
