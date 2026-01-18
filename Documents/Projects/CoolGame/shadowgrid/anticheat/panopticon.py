import numpy as np
from scipy import stats
from typing import Dict, Any, Optional

class DistributionAnalyzer:
    """
    The Panopticon: Advanced Statistical Detection Layer.
    Analyzes the distribution of player reaction times to detect:
    1. Uniformity (SusPlayer_3 / Level 2)
    2. Synthetic Normality (SusPlayer_4 / Level 3)
    3. Deviation from Human Log-Normal distribution
    """
    
    def __init__(self, window_size: int = 15): # Forensic Fix: 15 samples for statistical reliability
        self.delays = []
        self.window_size = window_size
        
        # Reference: Human Reaction Time ~ Log-Normal
        # mu=0.4, sigma=0.25 simulates typical gamer reaction times
        self.human_ref = stats.lognorm(s=0.4, scale=0.25) 

    def push_delay(self, delay_seconds: float) -> None:
        """Add a new delay sample to the window."""
        self.delays.append(delay_seconds)
        if len(self.delays) > self.window_size:
            self.delays.pop(0)
        
        # Debug: Print first 15 delays to verify correct values
        if len(self.delays) == 15:
            import numpy as np
            print(f"[PANOPTICON DEBUG] First 15 delays: {[f'{d:.3f}' for d in self.delays[:5]]}... StdDev={np.std(self.delays):.4f}")

    @property
    def std_dev(self) -> float:
        """Return current standard deviation of delays."""
        if len(self.delays) < 2:
            return 0.0
        return float(np.std(self.delays))

    def analyze(self, player_id: str = "unknown") -> Dict[str, Any]:
        """Run statistical tests on the current window."""
        # Need enough data for significance (at least 15 samples for reliable stats)
        if len(self.delays) < 15:
            # [DEBUG] Log insufficient data with current std_dev
            current_std = self.std_dev
            print(f"[PANOPTICON] {player_id}: insufficient_data (n={len(self.delays)}, std_dev={current_std:.4f})")
            return {"status": "insufficient_data", "verdict": "LEGIT", "std_dev": current_std, "n_delays": len(self.delays)}

        data = np.array(self.delays)
        std_dev = np.std(data)
        
        # DEBUG: Print stats for tuning
        msg = f"[Panopticon] {player_id} N={len(data)} Mean={np.mean(data):.3f} StdDev={std_dev:.4f}"
        print(msg)

        # 1. Kolmogorov-Smirnov Test for Uniformity
        data_range = max(data) - min(data)
        if data_range == 0:
            return {"status": "constant_data", "verdict": "LEGIT"}
            
        ks_stat_uniform, _ = stats.kstest(
            data, 
            'uniform', 
            args=(min(data), data_range)
        )
        uniformity_score = max(0.0, 1.0 - ks_stat_uniform)
        
        # 2. Shapiro-Wilk Test for Normality
        shapiro_stat, _ = stats.shapiro(data)
        
        # 3. Test for "Humanity" (Log-Normal Fit)
        # p-value < 0.05 means "Reject Null Hypothesis" (Not Log-Normal -> Not Human)
        ks_stat_human, ks_pvalue_human = stats.kstest(
            data,
            self.human_ref.cdf
        )
        
        return {
            "status": "analyzed",
            "sample_size": len(data),
            "std_dev": float(std_dev),  # [FIX] Add to result for logging
            "uniformity_score": float(uniformity_score),
            "shapiro_score": float(shapiro_stat),
            "ks_human_stat": float(ks_stat_human),
            "ks_human_pvalue": float(ks_pvalue_human),
            "verdict": self._get_verdict(shapiro_stat, ks_pvalue_human, uniformity_score)
        }

    def _get_verdict(self, shapiro: float, ks_p_human: float, uniformity: float) -> str:
        """Determines if the distribution is Bot-like."""
        
        std_dev = np.std(self.delays)
        mean_delay = np.mean(self.delays)
        
        print(f"[DEBUG] Shapiro: {shapiro:.4f}, KS_Human_P: {ks_p_human:.4f}, Uniformity: {uniformity:.4f}")
        print(f"[DEBUG] StdDev: {std_dev:.4f}, Mean: {mean_delay:.4f}")
        
        # =============================================================
        # PRIMARY DETECTOR: Low Variance (Catches ALL bots)
        # =============================================================
        # Human log-normal has std_dev ~0.15-0.40
        # All cheater bots (uniform, gaussian, replay) have std_dev < 0.10
        # However, system timing jitter can add ~0.10-0.20 variance
        # So we use 0.30 as a safe threshold that won't flag humans
        if std_dev < 0.30 and len(self.delays) >= 15:
            print(f"[PANOPTICON] LOW VARIANCE BOT DETECTED: std_dev={std_dev:.4f}")
            return "BOT_LOW_VARIANCE"
        
        # =============================================================
        # SECONDARY: Perfect Gaussian (High Shapiro + Not Human Log-Normal)
        # =============================================================
        is_synthetic_gaussian = (shapiro > 0.95) and (ks_p_human < 0.05)
        if is_synthetic_gaussian:
            return "BOT_SYNTHETIC_GAUSSIAN"
        
        # =============================================================
        # TERTIARY: Uniform Distribution (KS test)
        # =============================================================
        if uniformity > 0.85:
            return "BOT_UNIFORM"
            
        return "LEGIT"

