"""
ShadowGrid Tier 1 Training Pipeline

Generates training data and trains the XGBoost detector.
"""

from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np

from .model import XGBoostDetector, Tier1Detector


class SyntheticDataGenerator:
    """
    Generates synthetic training data for the detector.
    
    Creates realistic normal player patterns and
    various types of cheat patterns for training.
    """
    
    def __init__(self, n_features: int = 50, seed: int = 42):
        self.n_features = n_features
        self.rng = np.random.RandomState(seed)
    
    def generate_normal(self, n_samples: int = 1000) -> np.ndarray:
        """Generate normal player feature vectors."""
        X = np.zeros((n_samples, self.n_features))
        
        for i in range(n_samples):
            X[i] = self._generate_normal_player()
        
        return X
    
    def generate_cheater(self, n_samples: int = 1000) -> np.ndarray:
        """Generate cheater feature vectors."""
        X = np.zeros((n_samples, self.n_features))
        
        for i in range(n_samples):
            # Random cheat type
            cheat_type = self.rng.choice([
                'speedhack', 'wallhack', 'aimbot', 'macro', 'mixed'
            ])
            X[i] = self._generate_cheater(cheat_type)
        
        return X
    
    def _generate_normal_player(self) -> np.ndarray:
        """Generate single normal player."""
        features = np.zeros(self.n_features)
        
        # Movement (0-9): Natural human variance
        features[0:3] = self.rng.normal(0, 0.5, 3)  # velocities
        features[3:6] = self.rng.normal(0, 0.2, 3)  # accelerations
        features[6] = self.rng.uniform(0.2, 0.6)    # direction change rate
        features[7] = self.rng.uniform(0.3, 0.8)    # path straightness
        features[8] = self.rng.uniform(0, 0.15)     # wall collision rate
        features[9] = self.rng.uniform(0, 0.3)      # lava proximity
        
        # Timing (10-19): Human reaction times
        features[10] = self.rng.uniform(3, 10)      # input frequency
        features[11] = self.rng.uniform(50, 200)    # input regularity std
        features[12] = self.rng.uniform(150, 400)   # reaction time avg
        features[13] = self.rng.uniform(30, 100)    # reaction time std
        features[14] = self.rng.uniform(10, 60)     # time between kills
        features[15] = self.rng.uniform(5, 30)      # time to first crystal
        features[16] = self.rng.uniform(0.05, 0.3)  # idle time ratio
        features[17] = self.rng.uniform(0.1, 0.5)   # sprint time ratio
        features[18] = self.rng.uniform(200, 500)   # decision latency
        features[19] = self.rng.uniform(0.3, 0.6)   # prediction accuracy
        
        # Aiming (20-29): Human-like variance
        features[20:23] = self.rng.uniform(0.2, 0.5, 3)  # yaw deltas
        features[23:26] = self.rng.uniform(0.2, 0.5, 3)  # pitch deltas
        features[26] = self.rng.randint(0, 3)       # snap count
        features[27] = self.rng.uniform(0.5, 0.9)   # smoothness
        features[28] = self.rng.uniform(0, 0.5)     # target lock
        features[29] = self.rng.uniform(0.2, 0.5)   # pre-aim accuracy
        
        # Combat (30-39)
        features[30] = self.rng.randint(1, 10)      # crystal count
        features[31] = self.rng.randint(0, 5)       # death count
        features[32] = features[30] / max(features[31], 1)  # K/D
        features[33] = self.rng.uniform(0.3, 0.6)   # hit rate
        features[34] = self.rng.uniform(0.1, 0.5)   # crystal rate
        features[35] = self.rng.uniform(0, 10)      # DPS
        features[36] = features[34]                 # collect rate
        features[37] = self.rng.uniform(0.2, 0.8)   # path deviation
        features[38] = self.rng.uniform(0.2, 0.6)   # risk score
        features[39] = self.rng.uniform(0.3, 0.8)   # survival efficiency
        
        # Anomaly (40-49): Low for normal players
        features[40] = 0                            # impossible moves
        features[41] = 0                            # speed violations
        features[42] = 0                            # teleports
        features[43] = 0                            # state desyncs
        features[44] = 0                            # timing anomalies
        features[45] = self.rng.uniform(0.3, 0.6)   # prediction accuracy
        features[46] = 0                            # fog violations
        features[47] = 0                            # knowledge anomaly
        features[48] = self.rng.uniform(0.3, 0.7)   # behavioral consistency
        features[49] = self.rng.uniform(0.1, 0.3)   # session variance
        
        return features
    
    def _generate_cheater(self, cheat_type: str) -> np.ndarray:
        """Generate single cheater based on type."""
        # Start with normal baseline
        features = self._generate_normal_player()
        
        if cheat_type == 'speedhack':
            features[2] = self.rng.uniform(2, 5)    # High velocity
            features[5] = self.rng.uniform(1, 3)    # High acceleration
            features[41] = self.rng.randint(3, 20)  # Speed violations
            features[10] = self.rng.uniform(15, 30) # High input frequency
        
        elif cheat_type == 'wallhack':
            features[46] = self.rng.randint(2, 10)  # Fog violations
            features[47] = self.rng.uniform(0.5, 1) # Knowledge anomaly
            features[7] = self.rng.uniform(0.9, 1)  # Too straight paths
            features[37] = self.rng.uniform(0, 0.1) # Near-optimal pathing
            features[15] = self.rng.uniform(1, 5)   # Fast to first crystal
        
        elif cheat_type == 'aimbot':
            # Too consistent
            features[11] = self.rng.uniform(5, 20)  # Low input std
            features[13] = self.rng.uniform(5, 15)  # Low reaction std
            features[26] = self.rng.randint(5, 20)  # Many snaps
            features[27] = self.rng.uniform(0.95, 1) # Too smooth
            features[29] = self.rng.uniform(0.9, 1) # Too accurate
            features[33] = self.rng.uniform(0.9, 1) # High hit rate
        
        elif cheat_type == 'macro':
            # Perfect timing
            features[11] = self.rng.uniform(0, 5)   # Very low std
            features[48] = self.rng.uniform(0.95, 1) # Too consistent
            features[49] = self.rng.uniform(0, 0.05) # No variance
            features[44] = self.rng.randint(5, 15)  # Timing anomalies
        
        elif cheat_type == 'mixed':
            # Combination
            features[41] = self.rng.randint(1, 5)   # Some speed violations
            features[46] = self.rng.randint(1, 5)   # Some fog violations
            features[26] = self.rng.randint(3, 10)  # Some snaps
            features[48] = self.rng.uniform(0.85, 0.95)  # Slightly too consistent
        
        return features


class Tier1Trainer:
    """
    Training pipeline for Tier 1 detector.
    """
    
    def __init__(
        self,
        output_dir: str = "models",
        n_features: int = 50
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.n_features = n_features
    
    def train_model(
        self,
        n_normal: int = 2000,
        n_cheater: int = 2000,
        test_split: float = 0.2,
        seed: int = 42
    ) -> Tuple[Tier1Detector, dict]:
        """
        Train a new Tier 1 detector.
        
        Args:
            n_normal: Number of normal samples
            n_cheater: Number of cheater samples
            test_split: Fraction for testing
            seed: Random seed
            
        Returns:
            (trained detector, metrics)
        """
        # Generate data
        generator = SyntheticDataGenerator(self.n_features, seed)
        
        X_normal = generator.generate_normal(n_normal)
        X_cheater = generator.generate_cheater(n_cheater)
        
        X = np.vstack([X_normal, X_cheater])
        y = np.hstack([
            np.zeros(n_normal),
            np.ones(n_cheater)
        ])
        
        # Shuffle
        rng = np.random.RandomState(seed)
        indices = rng.permutation(len(X))
        X = X[indices]
        y = y[indices]
        
        # Split
        split_idx = int(len(X) * (1 - test_split))
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        
        # Train
        model_path = self.output_dir / "tier1_xgboost.pkl"
        detector = Tier1Detector(str(model_path))
        
        train_metrics = detector.train(X_train, y_train, X_test, y_test)
        
        # Evaluate on test set
        test_predictions = []
        for i in range(len(X_test)):
            result = detector.analyze(X_test[i])
            test_predictions.append(1 if result['flagged'] else 0)
        
        test_predictions = np.array(test_predictions)
        
        # Calculate test metrics
        tp = np.sum((y_test == 1) & (test_predictions == 1))
        fp = np.sum((y_test == 0) & (test_predictions == 1))
        fn = np.sum((y_test == 1) & (test_predictions == 0))
        
        test_metrics = {
            'precision': tp / (tp + fp) if (tp + fp) > 0 else 0,
            'recall': tp / (tp + fn) if (tp + fn) > 0 else 0,
        }
        test_metrics['f1'] = (
            2 * test_metrics['precision'] * test_metrics['recall'] /
            (test_metrics['precision'] + test_metrics['recall'])
            if (test_metrics['precision'] + test_metrics['recall']) > 0 else 0
        )
        
        # Save metrics
        all_metrics = {
            'train': train_metrics,
            'test': test_metrics,
            'samples': {
                'normal': n_normal,
                'cheater': n_cheater
            },
            'threshold': detector.xgb.threshold
        }
        
        with open(self.output_dir / "tier1_metrics.json", 'w') as f:
            json.dump(all_metrics, f, indent=2)
        
        return detector, all_metrics
    
    def train_from_replays(
        self,
        replay_dir: str,
        labels_file: str
    ) -> Tuple[Tier1Detector, dict]:
        """
        Train from actual replay data.
        
        Args:
            replay_dir: Directory containing replay files
            labels_file: JSON file mapping replay_id to label (0/1)
            
        Returns:
            (trained detector, metrics)
        """
        # TODO: Implement replay-based training
        # This would extract features from real game replays
        raise NotImplementedError("Replay-based training not yet implemented")


def main():
    """Train Tier 1 detector from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Train Tier 1 Detector")
    parser.add_argument("--output", default="models", help="Output directory")
    parser.add_argument("--normal", type=int, default=2000, help="Normal samples")
    parser.add_argument("--cheater", type=int, default=2000, help="Cheater samples")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    
    args = parser.parse_args()
    
    trainer = Tier1Trainer(args.output)
    detector, metrics = trainer.train_model(
        n_normal=args.normal,
        n_cheater=args.cheater,
        seed=args.seed
    )
    
    print("Training complete!")
    print(f"Test Recall: {metrics['test']['recall']:.2%}")
    print(f"Test Precision: {metrics['test']['precision']:.2%}")
    print(f"Model saved to: {args.output}/tier1_xgboost.pkl")


if __name__ == "__main__":
    main()
