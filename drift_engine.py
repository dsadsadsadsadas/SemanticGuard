#!/usr/bin/env python3
"""
🧠 TREPAN Drift Engine (TR-02)
Semantic Vector Engine: Measures code "drift" from intent using embeddings.

Uses local embedding model (no cloud calls) routed to GPU via Hardware Sentinel.
Converts text/code into vectors and calculates cosine similarity.
"""

import logging

# Graceful import handling
try:
    from sentence_transformers import SentenceTransformer, util
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

try:
    from hardware_sentinel import sentinel as hardware
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False


class DriftEngine:
    """
    Semantic drift detection using local embeddings.
    Measures how far code has "drifted" from its original intent.
    """
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize the semantic vector engine on the hardware-routed device.
        
        Args:
            model_name: HuggingFace model name (cached locally after first download)
        """
        self.logger = logging.getLogger("Trepan.DriftEngine")
        self.is_ready = False
        self.model = None
        self.device = 'cpu'
        
        if not HAS_TRANSFORMERS:
            self.logger.warning("⚠️ sentence-transformers not installed - Drift Engine disabled")
            self.logger.warning("   Install with: pip install sentence-transformers")
            return
        
        # Ask Hardware Sentinel where to run vector math
        if HAS_HARDWARE:
            self.device = hardware.route_task("VECTOR_SEARCH")
        
        self.logger.info(f"[*] Loading Drift Model '{model_name}' on: {self.device.upper()}")

        try:
            # Load the model locally (caches to ~/.cache/torch/sentence_transformers)
            self.model = SentenceTransformer(model_name, device=self.device)
            self.is_ready = True
            self.logger.info(f"✅ Drift Engine loaded successfully")
        except Exception as e:
            self.logger.error(f"[!] Failed to load vector model: {e}")
            self.is_ready = False

    def embed(self, text: str):
        """
        Convert text/code into a high-dimensional vector.
        
        Args:
            text: The text or code snippet to embed
            
        Returns:
            Tensor embedding or None if not ready
        """
        if not self.is_ready:
            return None
        # Encode directly on GPU if available
        return self.model.encode(text, convert_to_tensor=True, device=self.device)

    def calculate_drift_score(self, reference_text: str, candidate_text: str) -> float:
        """
        Calculate semantic drift between two pieces of text/code.
        
        Args:
            reference_text: The original/expected text
            candidate_text: The new text to compare
            
        Returns:
            Drift score from 0.0 (Identical) to 1.0 (Complete Drift/Unrelated)
        """
        if not self.is_ready:
            return 0.0

        # Vectorize both inputs
        ref_embedding = self.embed(reference_text)
        cand_embedding = self.embed(candidate_text)

        if ref_embedding is None or cand_embedding is None:
            return 0.0

        # Calculate Cosine Similarity (1.0 = Same, 0.0 = Opposite)
        similarity = util.pytorch_cos_sim(ref_embedding, cand_embedding).item()

        # Convert to "Drift Score" (Invert similarity)
        # If similarity is 0.9 (Very close), Drift is 0.1 (Low drift)
        drift_score = 1.0 - max(0.0, similarity)
        
        return drift_score

    def check_safety_drift(self, original_ast_summary: str, new_code_snippet: str, threshold: float = 0.4) -> bool:
        """
        High-level safety check: Returns True if drift exceeds threshold.
        
        Args:
            original_ast_summary: Summary of the original code intent
            new_code_snippet: New code to check for drift
            threshold: Drift threshold (0.0-1.0), default 0.4
            
        Returns:
            True if drift is dangerous (exceeds threshold), False if safe
        """
        score = self.calculate_drift_score(original_ast_summary, new_code_snippet)
        
        if score > threshold:
            self.logger.warning(f"⚠️ HIGH DRIFT DETECTED: Score {score:.2f} > {threshold}")
            return True  # Drift Detected
        
        return False  # Safe
    
    def get_status(self) -> dict:
        """Return current engine status for diagnostics."""
        return {
            "is_ready": self.is_ready,
            "device": self.device,
            "transformers_installed": HAS_TRANSFORMERS,
            "hardware_sentinel_available": HAS_HARDWARE
        }


# Global Instance
drift_monitor = DriftEngine()
