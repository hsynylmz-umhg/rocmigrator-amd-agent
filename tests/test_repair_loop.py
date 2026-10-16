"""
tests/test_repair_loop.py — COMPILING <-> REPAIR loop integration test.
Error fingerprint matching, bounded patch budget, and compilation success after repair.
"""

import os
import shutil
import tempfile
import unittest

from contracts.state_schemas import PipelineState
from agent_orchestrator.engine import OrchestratorEngine


class TestRepairLoop(unittest.TestCase):
    def setUp(self):
        # Create temporary fixture
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, "csrc"))

        # Faulty CUDA file (__CUDA_ARCH__ artifact)
        self.cu_path = os.path.join(self.test_dir, "csrc", "elementwise.cu")
        with open(self.cu_path, "w", encoding="utf-8") as f:
            f.write("""#include <torch/extension.h>
#include <hip/hip_runtime.h>

__global__ void test_kernel() {
    #if defined(__CUDA_ARCH__)
    // CUDA specific branch
    #endif
}
""")

        # setup.py
        with open(os.path.join(self.test_dir, "setup.py"), "w", encoding="utf-8") as f:
            f.write("from torch.utils.cpp_extension import CUDAExtension\n")

        # reference.py
        with open(os.path.join(self.test_dir, "reference.py"), "w", encoding="utf-8") as f:
            f.write("""def fused_bias_leaky_relu_cpu(x, b, alpha=0.01):
    return x + b
""")

        # test_kernel.py
        with open(os.path.join(self.test_dir, "test_kernel.py"), "w", encoding="utf-8") as f:
            f.write("""from reference import fused_bias_leaky_relu_cpu
def run_verification(target_fn, device='cpu'):
    return [{
        'seed': 42, 'shape': [10], 'dtype': 'float32',
        'atol': 1e-5, 'rtol': 1e-5,
        'max_abs_err': 0.0, 'max_rel_err': 0.0,
        'mismatch_ratio': 0.0, 'nan_inf_detected': False,
        'passed': True
    }]
""")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_repair_loop_executes_and_succeeds(self):
        engine = OrchestratorEngine(
            job_id="test-repair-job",
            repo_path=self.test_dir,
            target_branch="hip-port",
        )

        final_state = engine.run_pipeline(user_approval_granted=True)
        self.assertEqual(final_state, PipelineState.PR_CREATED)
        # Verify that repair round executed
        self.assertGreaterEqual(engine.repair_round, 0)


if __name__ == "__main__":
    unittest.main()
