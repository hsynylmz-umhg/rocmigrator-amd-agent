"""
agent_orchestrator/fingerprints/db.py — Compiler and HIPIFY Error Fingerprint Database.
Regex and parser-based deterministic error classifier.
Enforces the maximum 2 occurrences per fingerprint rule.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Fingerprint:
    id: str
    name: str
    pattern: str
    description: str
    suggested_fix: str
    occurrence_count: int = 0
    max_allowed: int = 2


class FingerprintDB:
    def __init__(self):
        self.fingerprints: Dict[str, Fingerprint] = {
            "FP_CUDA_HEADER": Fingerprint(
                id="FP_CUDA_HEADER",
                name="CUDA Header Not Hipified",
                pattern=r"(cuda_runtime\.h|#include <cuda\.h>|cuda/cuda\.h)",
                description="CUDA header files are not replaced with HIP counterparts.",
                suggested_fix="#include <hip/hip_runtime.h>",
            ),
            "FP_CUDA_ARCH": Fingerprint(
                id="FP_CUDA_ARCH",
                name="CUDA Arch Macro Usage",
                pattern=r"(__CUDA_ARCH__|use of undeclared identifier '__CUDA_ARCH__')",
                description="__CUDA_ARCH__ macro is undefined on AMD architecture.",
                suggested_fix="Convert macro definition to __HIP_ARCH_GFX__ or AMD equivalent.",
            ),
            "FP_CUDA_ERR_STRING": Fingerprint(
                id="FP_CUDA_ERR_STRING",
                name="cudaGetErrorString / cudaGetLastError",
                pattern=r"(cudaGetErrorString|cudaGetLastError|cudaError_t)",
                description="CUDA runtime error functions used directly.",
                suggested_fix="Replace with hipGetErrorString, hipGetLastError, hipError_t.",
            ),
            "FP_WARP_SIZE": Fingerprint(
                id="FP_WARP_SIZE",
                name="Hardcoded Warp Size 32",
                pattern=r"(warpSize\s*==\s*32|threads\s*=\s*32)",
                description="On AMD GPUs, default wavefront size may be 64 or 32.",
                suggested_fix="Use dynamic hipGetDeviceProperties query or wavefront-aware logic instead of hardcoded warpSize.",
            ),
            "FP_CUDA_EXTENSION": Fingerprint(
                id="FP_CUDA_EXTENSION",
                name="setup.py CUDAExtension Without ROCm Guard",
                pattern=r"CUDAExtension\(",
                description="CUDAExtension in setup.py is not properly configured for ROCm environment.",
                suggested_fix="torch.utils.cpp_extension BuildExtension / CUDAExtension must delegate to ROCm compiler.",
            ),
        }

    def classify(self, compiler_log: str) -> List[Fingerprint]:
        """
        Analyzes compilation or HIPIFY log and returns matching fingerprints.
        """
        matched = []
        for fp in self.fingerprints.values():
            if re.search(fp.pattern, compiler_log, re.IGNORECASE):
                matched.append(fp)
        return matched

    def record_occurrence(self, fp_id: str) -> bool:
        """
        Increments the occurrence count of the fingerprint.
        Returns False if maximum allowed occurrences (2) is exceeded.
        """
        if fp_id not in self.fingerprints:
            return False
        fp = self.fingerprints[fp_id]
        fp.occurrence_count += 1
        return fp.occurrence_count <= fp.max_allowed

    def get_occurrence(self, fp_id: str) -> int:
        return self.fingerprints.get(fp_id, Fingerprint(id="", name="", pattern="", description="", suggested_fix="")).occurrence_count
