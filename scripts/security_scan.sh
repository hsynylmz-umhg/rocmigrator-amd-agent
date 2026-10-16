#!/usr/bin/env bash
# scripts/security_scan.sh — Security Scan
# Subprocess calls must use shell=False; user input is never passed directly to commands.

set -euo pipefail

TARGET_DIR="${1:-.}"
echo "[SECURITY_SCAN] Scanning: $TARGET_DIR"

# 1. shell=True usage check
if grep -rn --include="*.py" "shell\s*=\s*True" "$TARGET_DIR"; then
    echo "SECURITY VIOLATION: 'shell=True' usage detected!" >&2
    exit 1
fi

# 2. Hardcoded credential check
if grep -rnE --include="*.py" --include="*.sh" "(AWS_SECRET|GITHUB_TOKEN|PASSWORD|PRIVATE_KEY)\s*=" "$TARGET_DIR"; then
    echo "SECURITY VIOLATION: Hardcoded credential detected!" >&2
    exit 1
fi

echo "[SECURITY_SCAN] Security scan completed successfully (0 violations)."
exit 0
