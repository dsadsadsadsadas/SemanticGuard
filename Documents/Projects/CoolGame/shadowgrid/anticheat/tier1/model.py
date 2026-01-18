"""
ShadowGrid Tier 1 XGBoost Detector

Lightweight client-side cheat detection optimized for high recall.
"""

from __future__ import annotations
import os
import pickle
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from abc import ABC, abstractmethod
import numpy as np

try:
    import xgboost as xgb
except ImportError:
    xgb = None


class BaseDetector(ABC):
    """Abstract base for cheat detectors."""
    
    @abstractmethod
    def predict(self, features: np.ndarray) -> Tuple[float, bool]:
        """
        Predict cheat probability.
        
        Args:
            features: Feature vector
            
        Returns:
            (probability, should_flag)
        """
        pass
    
    @abstractmethod
    def load(self, path: str) -> bool:
        """Load model from file."""
        pass
    
    @abstractmethod
    def save(self, path: str) -> bool:
        """Save model to file."""
        pass


class XGBoostDetector(BaseDetector):
    """
    XGBoost-based Tier 1 detector.
    
    Optimized for:
    - High recall (catch most cheaters)
    - Low latency (client-side execution)
    - Small model size
    
    Features:
    - 50 temporal/spatial features
    - Threshold tuning for 95%+ recall
    - Feature importance tracking
    """
    
    # Default hyperparameters optimized for recall
    DEFAULT_PARAMS = {
        'max_depth': 4,
        'learning_rate': 0.1,
        'n_estimators': 50,
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'use_label_encoder': False,
        'tree_method': 'hist',  # Fast training
        'random_state': 42
    }
    
    def __init__(
        self,
        threshold: float = 0.3,  # Low threshold for high recall
        params: Optional[dict] = None
    ):
        if xgb is None:
            raise ImportError("XGBoost is required for Tier 1 detection")
        
        self.threshold = threshold
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self.model: Optional[xgb.XGBClassifier] = None
        self.feature_importance: Optional[np.ndarray] = None
        self.is_trained = False
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None
    ) -> dict:
        """
        Train the detector.
        
        Args:
            X: Training features (n_samples, n_features)
            y: Training labels (0=normal, 1=cheater)
            X_val: Validation features
            y_val: Validation labels
            
        Returns:
            Training metrics
        """
        self.model = xgb.XGBClassifier(**self.params)
        
        eval_set = [(X, y)]
        if X_val is not None and y_val is not None:
            eval_set.append((X_val, y_val))
        
        self.model.fit(
            X, y,
            eval_set=eval_set,
            verbose=False
        )
        
        self.feature_importance = self.model.feature_importances_
        self.is_trained = True
        
        # Calculate metrics
        y_pred_proba = self.model.predict_proba(X)[:, 1]
        y_pred = (y_pred_proba >= self.threshold).astype(int)
        
        metrics = self._calculate_metrics(y, y_pred, y_pred_proba)
        
        # Tune threshold for target recall
        self.threshold = self._tune_threshold(y, y_pred_proba, target_recall=0.95)
        
        return metrics
    
    def predict(self, features: np.ndarray) -> Tuple[float, bool]:
        """
        Predict cheat probability.
        
        Args:
            features: Feature vector (1D or 2D)
            
        Returns:
            (probability, should_flag)
        """
        if not self.is_trained or self.model is None:
            return 0.0, False
        
        # Ensure 2D
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        probability = self.model.predict_proba(features)[:, 1]
        should_flag = probability >= self.threshold
        
        if len(probability) == 1:
            return float(probability[0]), bool(should_flag[0])
        
        return probability, should_flag
    
    def predict_batch(
        self,
        features_list: List[np.ndarray]
    ) -> List[Tuple[float, bool]]:
        """Predict on multiple feature vectors."""
        if not features_list:
            return []
        
        X = np.stack(features_list)
        probabilities = self.model.predict_proba(X)[:, 1]
        flags = probabilities >= self.threshold
        
        return [(float(p), bool(f)) for p, f in zip(probabilities, flags)]
    
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
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        # AUC
        try:
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(y_true, y_proba)
        except:
            auc = 0.0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'auc': auc,
            'true_positives': int(tp),
            'false_positives': int(fp),
            'false_negatives': int(fn),
            'true_negatives': int(tn)
        }
    
    def _tune_threshold(
        self,
        y_true: np.ndarray,
        y_proba: np.ndarray,
        target_recall: float = 0.95
    ) -> float:
        """
        Tune threshold to achieve target recall.
        
        Args:
            y_true: True labels
            y_proba: Predicted probabilities
            target_recall: Target recall value
            
        Returns:
            Optimal threshold
        """
        cheater_probas = y_proba[y_true == 1]
        
        if len(cheater_probas) == 0:
            return 0.5
        
        # Sort probabilities
        sorted_probas = np.sort(cheater_probas)
        
        # Find threshold that captures target_recall of cheaters
        idx = int((1 - target_recall) * len(sorted_probas))
        threshold = sorted_probas[idx] if idx < len(sorted_probas) else 0.01
        
        return max(0.01, min(0.99, threshold))
    
    def get_feature_importance(
        self,
        feature_names: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """Get feature importance rankings."""
        if self.feature_importance is None:
            return {}
        
        if feature_names is None:
            feature_names = [f"f{i}" for i in range(len(self.feature_importance))]
        
        return {
            name: float(importance)
            for name, importance in zip(feature_names, self.feature_importance)
        }
    
    def load(self, path: str) -> bool:
        """Load model from file."""
        try:
            path = Path(path)
            if not path.exists():
                return False
            
            with open(path, 'rb') as f:
                data = pickle.load(f)
            
            self.model = data['model']
            self.threshold = data['threshold']
            self.feature_importance = data.get('feature_importance')
            self.is_trained = True
            
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
    
    def save(self, path: str) -> bool:
        """Save model to file."""
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'wb') as f:
                pickle.dump({
                    'model': self.model,
                    'threshold': self.threshold,
                    'feature_importance': self.feature_importance
                }, f)
            
            return True
        except Exception as e:
            print(f"Error saving model: {e}")
            return False


class Tier1Detector:
    """
    High-level Tier 1 detection manager.
    
    Combines XGBoost detection with rule-based checks
    for maximum coverage.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        self.xgb = XGBoostDetector()
        self.model_path = model_path
        
        if model_path and os.path.exists(model_path):
            self.xgb.load(model_path)
        
        # Rule-based thresholds for instant flagging
        self.instant_flag_rules = {
            'teleports': 1,           # Any teleport = immediate flag
            'speed_violations': 5,    # 5+ = immediate flag
            'fog_violations': 3       # 3+ = immediate flag
        }
    
    def analyze(
        self,
        features: np.ndarray,
        quick_indicators: Optional[Dict[str, int]] = None
    ) -> dict:
        """
        Analyze player for cheating.
        
        Args:
            features: Feature vector from FeatureExtractor
            quick_indicators: Dict with instant-flag counters
            
        Returns:
            Analysis result with probability and recommendation
        """
        result = {
            'probability': 0.0,
            'flagged': False,
            'reason': None,
            'tier2_required': False
        }
        
        # Check instant-flag rules first
        if quick_indicators:
            for key, threshold in self.instant_flag_rules.items():
                if quick_indicators.get(key, 0) >= threshold:
                    result['probability'] = 1.0
                    result['flagged'] = True
                    result['reason'] = f"Rule violation: {key}"
                    result['tier2_required'] = True
                    return result
        
        # XGBoost prediction
        if self.xgb.is_trained:
            prob, flagged = self.xgb.predict(features)
            result['probability'] = prob
            result['flagged'] = flagged
            
            if flagged:
                result['reason'] = "ML detection"
                result['tier2_required'] = prob > 0.5  # High confidence
        else:
            # Fallback: Rule-based scoring when model not trained
            # Use behavioral features to estimate suspicion
            score = 0.0
            
            if quick_indicators:
                # Speed violations (feature 41)
                speed_violations = quick_indicators.get('speed_violations', 0)
                if speed_violations > 0:
                    score += min(speed_violations * 10, 40)  # Up to 40%
                
                # Teleports (feature 42)
                teleports = quick_indicators.get('teleports', 0)
                if teleports > 0:
                    score += min(teleports * 20, 40)  # Up to 40%
                
                # Invalid moves
                invalid_moves = quick_indicators.get('invalid_moves', 0)
                if invalid_moves > 10:
                    score += min((invalid_moves - 10) * 2, 20)  # Up to 20%
            
            # Check feature-based anomalies
            if len(features) >= 50:
                # Input regularity (feature 11) - very low std = bot-like
                input_std = features[11] if features[11] > 0 else 0
                if 0 < input_std < 20:  # Very regular inputs = suspicious
                    score += 15
                
                # Direction change rate (feature 6) - very high = erratic
                dir_change = features[6] if features[6] > 0 else 0
                if dir_change > 0.7:  # 70%+ direction changes
                    score += 10
            
            result['probability'] = min(score / 100.0, 1.0)
            result['flagged'] = score >= 30
            if result['flagged']:
                result['reason'] = "Behavioral anomaly"
        
        return result
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None
    ) -> dict:
        """Train the detector."""
        metrics = self.xgb.train(X, y, X_val, y_val)
        
        if self.model_path:
            self.xgb.save(self.model_path)
        
        return metrics
