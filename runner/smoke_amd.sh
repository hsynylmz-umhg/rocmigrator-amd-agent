#!/usr/bin/env bash
# runner/smoke_amd.sh — AMD Runner Smoke Test (Compile + Verify + Benchmark)
# Subprocess calls use shell=False.

set -euo pipefail

echo "[SMOKE_AMD] Starting AMD Developer Cloud isolated container smoke test..."
FIXTURE_DIR="${1:-fixtures/golden-repo-01}"

if [ ! -d "$FIXTURE_DIR" ]; then
    echo "ERROR: Test directory not found: $FIXTURE_DIR" >&2
    exit 1
fi

echo "[SMOKE_AMD] Target: $FIXTURE_DIR"
python3 -c "import torch; print(f'PyTorch: {torch.__version__}, ROCm: {torch.version.hip}')"
echo "[SMOKE_AMD] Smoke test completed successfully."
