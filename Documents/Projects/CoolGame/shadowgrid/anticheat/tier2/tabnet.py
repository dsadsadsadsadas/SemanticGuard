"""
ShadowGrid Tier 2 TabNet Detector

Heavy server-side model for deep analysis with feature attention.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass, field
import numpy as np

try:
    import torch
    from pytorch_tabnet.tab_model import TabNetClassifier
    TABNET_AVAILABLE = True
except ImportError:
    TABNET_AVAILABLE = False
    TabNetClassifier = None


@dataclass
class PlayerHistory:
    """Historical statistics for a player."""
    player_id: str
    
    # Session statistics
    total_sessions: int = 0
    total_playtime_hours: float = 0.0
    
    # Performance history
    avg_kd_ratio: float = 0.0
    avg_crystal_rate: float = 0.0
    avg_time_to_kill: float = 0.0
    
    # Accuracy metrics
    avg_hit_rate: float = 0.0
    avg_hit_rate_moving: float = 0.0  # Hit rate while moving
    avg_precision: float = 0.0
    
    # Progression
    level: int = 1
    level_up_speed: float = 0.0       # Levels per hour
    
    # Anti-cheat history
    previous_flags: int = 0
    previous_bans: int = 0
    tier1_flag_rate: float = 0.0      # % of sessions flagged by Tier 1
    
    # Behavioral baselines
    avg_input_frequency: float = 0.0
    avg_reaction_time: float = 0.0
    movement_entropy: float = 0.0
    
    def to_features(self) -> np.ndarray:
        """Convert to feature vector."""
        return np.array([
            self.total_sessions / 100,
            self.total_playtime_hours / 100,
            self.avg_kd_ratio,
            self.avg_crystal_rate,
            self.avg_time_to_kill / 10,
            self.avg_hit_rate,
            self.avg_hit_rate_moving,
            self.avg_precision,
            self.level / 50,
            self.level_up_speed,
            self.previous_flags / 10,
            self.previous_bans,
            self.tier1_flag_rate,
            self.avg_input_frequency / 20,
            self.avg_reaction_time / 500,
            self.movement_entropy
        ], dtype=np.float32)


class TabNetDetector:
    """
    TabNet-based Tier 2 detector.
    
    Features:
    - Attention mechanism for feature selection
    - Handles both session and historical features
    - Provides explainable importance scores
    - High precision (minimize false positives)
    """
    
    # Input dimensions
    SESSION_FEATURES = 50    # From Tier 1
    HISTORY_FEATURES = 16    # From PlayerHistory
    TOTAL_FEATURES = 66
    
    DEFAULT_PARAMS = {
        'n_d': 32,           # Width of decision prediction layer
        'n_a': 32,           # Width of attention embedding
        'n_steps': 4,        # Number of decision steps
        'gamma': 1.3,        # Coefficient for feature reuse
        'lambda_sparse': 1e-3,
        'optimizer_fn': None,  # Will be set to Adam
        'optimizer_params': {'lr': 2e-2},
        'mask_type': 'entmax',
        'scheduler_params': {'step_size': 10, 'gamma': 0.9},
        'scheduler_fn': None,  # Will be set to StepLR
    }
    
    def __init__(
        self,
        threshold: float = 0.7,  # High threshold for precision
        params: Optional[dict] = None
    ):
        if not TABNET_AVAILABLE:
            raise ImportError(
                "PyTorch TabNet is required for Tier 2 detection. "
                "Install with: pip install pytorch-tabnet"
            )
        
        self.threshold = threshold
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self.model: Optional[TabNetClassifier] = None
        self.is_trained = False
        self.feature_importances_: Optional[np.ndarray] = None
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        max_epochs: int = 100,
        patience: int = 10
    ) -> dict:
        """
        Train the TabNet detector.
        
        Args:
            X: Training features (session + history)
            y: Labels (0=normal, 1=cheater)
            X_val: Validation features
            y_val: Validation labels
            max_epochs: Maximum training epochs
            patience: Early stopping patience
            
        Returns:
            Training metrics
        """
        self.model = TabNetClassifier(**self.params)
        
        eval_set = [(X_val, y_val)] if X_val is not None else None
        eval_name = ['val'] if eval_set else None
        
        self.model.fit(
            X, y,
            eval_set=eval_set,
            eval_name=eval_name,
            eval_metric=['auc', 'accuracy'],
            max_epochs=max_epochs,
            patience=patience,
            batch_size=256,
            virtual_batch_size=128,
            num_workers=0,
            drop_last=False
        )
        
        self.feature_importances_ = self.model.feature_importances_
        self.is_trained = True
        
        # Calculate metrics
        y_pred_proba = self.model.predict_proba(X)[:, 1]
        y_pred = (y_pred_proba >= self.threshold).astype(int)
        
        return self._calculate_metrics(y, y_pred, y_pred_proba)
    
    def predict(
        self,
        session_features: np.ndarray,
        history: Optional[PlayerHistory] = None
    ) -> Tuple[float, bool, np.ndarray]:
        """
        Predict cheat probability with attention weights.
        
        Args:
            session_features: Current session features (50 dims)
            history: Player's historical statistics
            
        Returns:
            (probability, is_cheater, attention_weights)
        """
        if not self.is_trained or self.model is None:
            return 0.0, False, np.zeros(self.TOTAL_FEATURES)
        
        # Combine features
        if history:
            history_features = history.to_features()
        else:
            history_features = np.zeros(self.HISTORY_FEATURES, dtype=np.float32)
        
        X = np.concatenate([session_features, history_features])
        X = X.reshape(1, -1)
        
        # Predict with attention
        proba = self.model.predict_proba(X)[:, 1][0]
        
        # Get attention masks
        attention = self._get_attention(X)
        
        return proba, proba >= self.threshold, attention
    
    def _get_attention(self, X: np.ndarray) -> np.ndarray:
        """Get attention weights for features."""
        try:
            # TabNet provides explain() for feature importance per sample
            masks = self.model.explain(X)[0]
            return masks.mean(axis=0)  # Aggregate attention
        except:
            return np.ones(X.shape[1]) / X.shape[1]
    
    def _calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_proba: np.ndarray
    ) -> dict:
        """Calculate evaluation metrics."""
        tp = np.sum((y_true == 1) & (y_pred == 1))
        fp = np.sum((y_true == 0) & (y_pred == 1))
        fn = np.sum((y_true == 1) & (y_pred == 0))
        tn = np.sum((y_true == 0) & (y_pred == 0))
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0,
            'true_positives': int(tp),
            'false_positives': int(fp),
            'false_negatives': int(fn),
            'true_negatives': int(tn)
        }
    
    def get_top_features(
        self,
        attention_weights: np.ndarray,
        feature_names: Optional[List[str]] = None,
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """Get top contributing features."""
        if feature_names is None:
            feature_names = [f"f{i}" for i in range(len(attention_weights))]
        
        indices = np.argsort(attention_weights)[-top_k:][::-1]
        
        return [
            (feature_names[i], float(attention_weights[i]))
            for i in indices
        ]
    
    def save(self, path: str) -> bool:
        """Save model to file."""
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            self.model.save_model(str(path))
            return True
        except Exception as e:
            print(f"Error saving TabNet model: {e}")
            return False
    
    def load(self, path: str) -> bool:
        """Load model from file."""
        try:
            path = Path(path)
            if not path.exists():
                return False
            
            self.model = TabNetClassifier()
            self.model.load_model(str(path))
            self.is_trained = True
            
            return True
        except Exception as e:
            print(f"Error loading TabNet model: {e}")
            return False


class HistoryStore:
    """
    Simple in-memory store for player history.
    
    In production, this would be backed by a database.
    """
    
    def __init__(self):
        self._store: Dict[str, PlayerHistory] = {}
    
    def get(self, player_id: str) -> Optional[PlayerHistory]:
        """Get player history."""
        return self._store.get(player_id)
    
    def update(self, history: PlayerHistory) -> None:
        """Update player history."""
        self._store[history.player_id] = history
    
    def create(self, player_id: str) -> PlayerHistory:
        """Create new player history."""
        history = PlayerHistory(player_id=player_id)
        self._store[player_id] = history
        return history
    
    def get_or_create(self, player_id: str) -> PlayerHistory:
        """Get or create player history."""
        if player_id not in self._store:
            return self.create(player_id)
        return self._store[player_id]
    
    def update_from_session(
        self,
        player_id: str,
        session_stats: dict
    ) -> PlayerHistory:
        """
        Update history with session statistics.
        
        Args:
            player_id: Player ID
            session_stats: Dict with session statistics
            
        Returns:
            Updated history
        """
        history = self.get_or_create(player_id)
        n = history.total_sessions + 1
        
        # Rolling averages
        if 'kd_ratio' in session_stats:
            history.avg_kd_ratio = (
                history.avg_kd_ratio * (n - 1) + session_stats['kd_ratio']
            ) / n
        
        if 'crystal_rate' in session_stats:
            history.avg_crystal_rate = (
                history.avg_crystal_rate * (n - 1) + session_stats['crystal_rate']
            ) / n
        
        if 'input_frequency' in session_stats:
            history.avg_input_frequency = (
                history.avg_input_frequency * (n - 1) + session_stats['input_frequency']
            ) / n
        
        if 'reaction_time' in session_stats:
            history.avg_reaction_time = (
                history.avg_reaction_time * (n - 1) + session_stats['reaction_time']
            ) / n
        
        if 'playtime_hours' in session_stats:
            history.total_playtime_hours += session_stats['playtime_hours']
        
        if 'flagged' in session_stats and session_stats['flagged']:
            history.previous_flags += 1
        
        history.total_sessions = n
        history.tier1_flag_rate = history.previous_flags / n
        
        self.update(history)
        return history
