"""
ShadowGrid Metrics Tracker

Tracks Precision, Recall, and AUC for anti-cheat system.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import numpy as np


@dataclass
class DetectionEvent:
    """A single detection event for metrics calculation."""
    event_id: str
    player_id: str
    timestamp: float
    
    # Predictions
    tier1_prediction: bool = False   # True = flagged
    tier2_prediction: bool = False
    combined_score: float = 0.0
    
    # Ground truth (set after human review)
    ground_truth: Optional[bool] = None  # True = actually cheating
    
    # Outcome
    penalty_applied: Optional[str] = None


class MetricsTracker:
    """
    Tracks anti-cheat performance metrics.
    
    Key metrics:
    - Precision: TP / (TP + FP) - Accuracy of positive detections
    - Recall: TP / (TP + FN) - Coverage of actual cheaters
    - F1: Harmonic mean of precision and recall
    - AUC: Area under ROC curve
    - False Positive Rate: FP / (FP + TN)
    """
    
    def __init__(self):
        self.events: Dict[str, DetectionEvent] = {}
        self.tier1_scores: List[tuple] = []  # (score, ground_truth)
        self.tier2_scores: List[tuple] = []
        self.combined_scores: List[tuple] = []
    
    def record_detection(
        self,
        event_id: str,
        player_id: str,
        tier1_flagged: bool,
        tier2_flagged: bool,
        combined_score: float
    ) -> DetectionEvent:
        """Record a detection event."""
        event = DetectionEvent(
            event_id=event_id,
            player_id=player_id,
            timestamp=time.time(),
            tier1_prediction=tier1_flagged,
            tier2_prediction=tier2_flagged,
            combined_score=combined_score
        )
        
        self.events[event_id] = event
        return event
    
    def set_ground_truth(
        self,
        event_id: str,
        is_cheater: bool
    ) -> bool:
        """Set ground truth after human review."""
        event = self.events.get(event_id)
        if not event:
            return False
        
        event.ground_truth = is_cheater
        
        # Record for AUC calculation
        self.tier1_scores.append((
            1.0 if event.tier1_prediction else 0.0,
            is_cheater
        ))
        self.tier2_scores.append((
            1.0 if event.tier2_prediction else 0.0,
            is_cheater
        ))
        self.combined_scores.append((
            event.combined_score,
            is_cheater
        ))
        
        return True
    
    def calculate_tier1_metrics(self) -> dict:
        """Calculate metrics for Tier 1 detector."""
        return self._calculate_binary_metrics(
            [(score > 0.5, truth) for score, truth in self.tier1_scores]
        )
    
    def calculate_tier2_metrics(self) -> dict:
        """Calculate metrics for Tier 2 detector."""
        return self._calculate_binary_metrics(
            [(score > 0.5, truth) for score, truth in self.tier2_scores]
        )
    
    def calculate_combined_metrics(
        self,
        threshold: float = 0.5
    ) -> dict:
        """Calculate metrics for combined system."""
        predictions = [
            (score >= threshold, truth)
            for score, truth in self.combined_scores
        ]
        
        metrics = self._calculate_binary_metrics(predictions)
        metrics['auc'] = self._calculate_auc(self.combined_scores)
        
        return metrics
    
    def _calculate_binary_metrics(
        self,
        predictions: List[tuple]
    ) -> dict:
        """Calculate binary classification metrics."""
        if not predictions:
            return {
                'precision': 0.0,
                'recall': 0.0,
                'f1': 0.0,
                'accuracy': 0.0,
                'false_positive_rate': 0.0,
                'true_positives': 0,
                'false_positives': 0,
                'true_negatives': 0,
                'false_negatives': 0,
                'total_samples': 0
            }
        
        tp = fp = tn = fn = 0
        
        for pred, truth in predictions:
            if truth is None:
                continue
            
            if pred and truth:
                tp += 1
            elif pred and not truth:
                fp += 1
            elif not pred and truth:
                fn += 1
            else:
                tn += 1
        
        total = tp + fp + tn + fn
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        accuracy = (tp + tn) / total if total > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'accuracy': accuracy,
            'false_positive_rate': fpr,
            'true_positives': tp,
            'false_positives': fp,
            'true_negatives': tn,
            'false_negatives': fn,
            'total_samples': total
        }
    
    def _calculate_auc(
        self,
        scores_truths: List[tuple]
    ) -> float:
        """
        Calculate AUC (Area Under ROC Curve).
        
        Uses the trapezoidal rule for approximation.
        """
        if len(scores_truths) < 2:
            return 0.5
        
        # Filter out None ground truths
        valid = [(s, t) for s, t in scores_truths if t is not None]
        
        if len(valid) < 2:
            return 0.5
        
        # Sort by score descending
        valid.sort(key=lambda x: x[0], reverse=True)
        
        scores = [s for s, _ in valid]
        truths = [t for _, t in valid]
        
        # Calculate TPR and FPR at each threshold
        n_pos = sum(truths)
        n_neg = len(truths) - n_pos
        
        if n_pos == 0 or n_neg == 0:
            return 0.5
        
        tpr_points = []
        fpr_points = []
        
        tp = fp = 0
        
        for i, truth in enumerate(truths):
            if truth:
                tp += 1
            else:
                fp += 1
            
            tpr = tp / n_pos
            fpr = fp / n_neg
            
            tpr_points.append(tpr)
            fpr_points.append(fpr)
        
        # Calculate AUC using trapezoidal rule
        auc = 0.0
        for i in range(1, len(fpr_points)):
            auc += (fpr_points[i] - fpr_points[i-1]) * (tpr_points[i] + tpr_points[i-1]) / 2
        
        return auc
    
    def get_threshold_analysis(
        self,
        thresholds: Optional[List[float]] = None
    ) -> List[dict]:
        """
        Analyze metrics at different thresholds.
        
        Helps tune threshold for desired precision/recall tradeoff.
        """
        if thresholds is None:
            thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        
        results = []
        
        for threshold in thresholds:
            metrics = self.calculate_combined_metrics(threshold)
            results.append({
                'threshold': threshold,
                **metrics
            })
        
        return results
    
    def get_summary(self) -> dict:
        """Get summary of all metrics."""
        return {
            'tier1': self.calculate_tier1_metrics(),
            'tier2': self.calculate_tier2_metrics(),
            'combined': self.calculate_combined_metrics(),
            'total_events': len(self.events),
            'reviewed_events': sum(
                1 for e in self.events.values() if e.ground_truth is not None
            ),
            'pending_review': sum(
                1 for e in self.events.values() if e.ground_truth is None
            )
        }
    
    def export_for_retraining(self) -> dict:
        """Export labeled data for model retraining."""
        labeled = [
            e for e in self.events.values()
            if e.ground_truth is not None
        ]
        
        return {
            'samples': len(labeled),
            'positive_samples': sum(1 for e in labeled if e.ground_truth),
            'negative_samples': sum(1 for e in labeled if not e.ground_truth),
            'events': [
                {
                    'event_id': e.event_id,
                    'player_id': e.player_id,
                    'combined_score': e.combined_score,
                    'ground_truth': e.ground_truth
                }
                for e in labeled
            ]
        }


# Global instance
metrics_tracker = MetricsTracker()
