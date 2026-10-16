"""
scripts/mock_e2e.py — Golden Repo 01 End-to-End Mock Verification.
Executes PyTorch CUDAExtension, hipify-clang, compilation, error fingerprint classification,
rule-governed repair (repair <= 6), VERIFYING, REPORT, USER_APPROVAL, and PR_CREATED
stages from start to finish.

Verification criterion: Exit code 0.
shell=True is STRICTLY FORBIDDEN.
"""

import os
import sys

# Add repository root to sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from contracts.state_schemas import PipelineState
from agent_orchestrator.engine import OrchestratorEngine
from scripts.generate_report import generate_html_report


def run_mock_e2e():
    print("=" * 60)
    print("ROCmigrator — Starting AMD Hackathon ACT III Mock E2E")
    print("=" * 60)

    target_repo = os.path.join(REPO_ROOT, "fixtures", "golden-repo-01")
    job_id = "mock-job-001"

    engine = OrchestratorEngine(
        job_id=job_id,
        repo_path=target_repo,
        target_branch="hip-port",
    )

    # Run state machine with user approval granted
    final_state = engine.run_pipeline(user_approval_granted=True)

    print("\n" + "=" * 60)
    print(f"Pipeline Completed. Final State: {final_state.value}")
    print("=" * 60)

    if final_state != PipelineState.PR_CREATED:
        print(f"ERROR: Expected state PR_CREATED but finished with {final_state.value}!")
        sys.exit(1)

    # Generate HTML report
    report_json_path = os.path.join(target_repo, "verification_report.json")
    if os.path.exists(report_json_path):
        report_html_path = os.path.join(target_repo, "verification_report.html")
        generate_html_report(engine.verification_report, report_html_path)
        print(f"Report generated: {report_html_path}")

    print("\n[MOCK_E2E] All checks, guardrails, and numerical verifications passed successfully!")
    print("[MOCK_E2E] Exit code: 0")
    sys.exit(0)


if __name__ == "__main__":
    run_mock_e2e()
