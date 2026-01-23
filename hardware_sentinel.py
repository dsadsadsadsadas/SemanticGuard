#!/usr/bin/env python3
"""
🖥️ TREPAN Hardware Sentinel (TR-01 Enhanced)
Compute Router: Intelligently routes tasks to optimal processor.

Routing Logic:
- AST Parsing → Always CPU (pointer-heavy, recursive, GIL-bound)
- Vector/Embedding Ops → GPU when available AND beneficial
- Small workloads → CPU (avoid GPU transfer overhead)
- Large workloads → GPU (parallel processing wins)
"""

import sys
import time
import logging
from dataclasses import dataclass
from typing import Optional

# Try importing torch for GPU detection, handle absence gracefully
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class ComputeConfig:
    """Hardware configuration detected at startup."""
    device: str  # 'cpu', 'cuda', 'mps' (Mac)
    gpu_name: str = ""
    vram_mb: float = 0.0
    cuda_version: str = ""
    cpu_cores: int = 1
    
    # Thresholds for smart routing
    small_workload_threshold: int = 100  # Tokens/chars below which CPU is faster
    gpu_transfer_overhead_ms: float = 5.0  # Estimated GPU memory transfer time


class HardwareSentinel:
    """
    Detects available hardware and intelligently routes tasks.
    
    Smart Routing Rules:
    1. AST_PARSING → Always CPU (tree traversal is not parallelizable)
    2. VECTOR_SEARCH with small input → CPU (avoid transfer overhead)
    3. VECTOR_SEARCH with large input → GPU (matrix ops benefit from parallelism)
    4. LLM_INFERENCE → GPU if available (always beneficial)
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Trepan.Hardware")
        self.config = self._detect_hardware()
        self._log_startup()

    def _detect_hardware(self) -> ComputeConfig:
        """Detect available GPU hardware and capabilities."""
        import os
        cpu_cores = os.cpu_count() or 1
        
        if not HAS_TORCH:
            self.logger.warning("⚠️ PyTorch not installed - GPU detection disabled")
            return ComputeConfig(device='cpu', cpu_cores=cpu_cores)
        
        # Check for CUDA GPU
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return ComputeConfig(
                device='cuda',
                gpu_name=props.name,
                vram_mb=props.total_memory / 1024 / 1024,
                cuda_version=torch.version.cuda or "",
                cpu_cores=cpu_cores
            )
        
        # Check for Apple Metal (MPS)
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return ComputeConfig(
                device='mps',
                gpu_name='Apple Metal',
                cpu_cores=cpu_cores
            )
        
        # CPU only
        return ComputeConfig(device='cpu', cpu_cores=cpu_cores)

    def _log_startup(self):
        """Log hardware detection results."""
        if self.config.device == 'cuda':
            self.logger.info(
                f"🚀 GPU DETECTED: {self.config.gpu_name} "
                f"({self.config.vram_mb:.0f}MB VRAM, CUDA {self.config.cuda_version})"
            )
        elif self.config.device == 'mps':
            self.logger.info("🍎 GPU DETECTED: Apple Metal (MPS)")
        else:
            self.logger.warning(
                f"🐢 NO GPU DETECTED: Using CPU ({self.config.cpu_cores} cores)"
            )

    def route_task(
        self, 
        task_type: str, 
        payload_size: int = 0,
        force_device: Optional[str] = None
    ) -> str:
        """
        Intelligently route task to optimal compute device.
        
        Args:
            task_type: 'AST_PARSING', 'VECTOR_SEARCH', 'LLM_INFERENCE', 'EMBEDDING'
            payload_size: Estimated input size (chars/tokens)
            force_device: Override automatic routing ('cpu', 'cuda', 'mps')
        
        Returns:
            Device string: 'cpu', 'cuda', or 'mps'
        """
        # Allow manual override
        if force_device:
            return force_device
        
        # Rule 1: AST parsing is ALWAYS CPU
        # Tree traversal is sequential, pointer-heavy, and GIL-bound
        if task_type == "AST_PARSING":
            return "cpu"
        
        # Rule 2: No GPU available → CPU
        if self.config.device == 'cpu':
            return "cpu"
        
        # Rule 3: Small workloads → CPU (avoid transfer overhead)
        # GPU transfer takes ~5ms, so small jobs are faster on CPU
        if payload_size > 0 and payload_size < self.config.small_workload_threshold:
            self.logger.debug(
                f"Small payload ({payload_size} chars) - routing to CPU to avoid transfer overhead"
            )
            return "cpu"
        
        # Rule 4: Vector/Embedding operations → GPU (matrix multiplication)
        if task_type in ("VECTOR_SEARCH", "EMBEDDING"):
            # Check VRAM availability for large payloads
            if payload_size > 50000 and self.config.vram_mb > 0:
                estimated_vram_mb = payload_size / 1000  # Rough estimate
                if estimated_vram_mb > self.config.vram_mb * 0.8:
                    self.logger.warning(
                        f"⚠️ Large payload may exceed VRAM - routing to CPU"
                    )
                    return "cpu"
            return self.config.device
        
        # Rule 5: LLM inference → Always GPU if available (always faster)
        if task_type == "LLM_INFERENCE":
            return self.config.device
        
        # Default: CPU for unknown task types
        return "cpu"

    def benchmark_devices(self, test_size: int = 1000) -> dict:
        """
        Run quick benchmark to compare CPU vs GPU performance.
        
        Returns:
            Dict with timing results for each device
        """
        if not HAS_TORCH:
            return {"error": "PyTorch not installed"}
        
        results = {}
        
        # CPU benchmark
        start = time.perf_counter()
        a = torch.randn(test_size, test_size)
        b = torch.randn(test_size, test_size)
        c = a @ b
        results['cpu_ms'] = (time.perf_counter() - start) * 1000
        
        # GPU benchmark (if available)
        if self.config.device == 'cuda':
            start = time.perf_counter()
            a = torch.randn(test_size, test_size, device='cuda')
            b = torch.randn(test_size, test_size, device='cuda')
            c = a @ b
            torch.cuda.synchronize()  # Wait for GPU to finish
            results['gpu_ms'] = (time.perf_counter() - start) * 1000
            results['gpu_speedup'] = results['cpu_ms'] / results['gpu_ms']
        
        return results

    def get_status(self) -> dict:
        """Return current hardware status for diagnostics."""
        return {
            "device": self.config.device,
            "gpu_name": self.config.gpu_name,
            "vram_mb": self.config.vram_mb,
            "cuda_version": self.config.cuda_version,
            "cpu_cores": self.config.cpu_cores,
            "gpu_available": self.config.device != 'cpu',
            "torch_installed": HAS_TORCH
        }

    def is_gpu_available(self) -> bool:
        """Quick check if GPU is available."""
        return self.config.device != 'cpu'


# Global Instance
sentinel = HardwareSentinel()

