"""Run offline fixture checks in a disposable copy without touching real fixtures."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
CHECK_ROOT = (ROOT / "build" / "contract_checks").resolve()
PYTHON = Path(sys.executable)


def fixture_hashes():
    return {
        str(path.relative_to(ROOT / "fixtures")): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (ROOT / "fixtures").rglob("*")
        if path.is_file()
    }


before = fixture_hashes()
checkout = Path(tempfile.mkdtemp(prefix="diff-repair-regression-", dir=CHECK_ROOT)).resolve()
assert checkout.parent == CHECK_ROOT
print(f"CHECKOUT={checkout}", flush=True)
environment = os.environ.copy()
environment.pop("OPENAI_API_KEY", None)
environment["PYTHONDONTWRITEBYTECODE"] = "1"
environment["PYTHONIOENCODING"] = "utf-8"


def run(command, label):
    result = subprocess.run(
        command, cwd=checkout, env=environment, shell=False,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    (checkout / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        print(result.stdout[-5000:])
        print(result.stderr[-5000:])
        raise RuntimeError(f"{label} failed with exit {result.returncode}")
    return result.stdout


try:
    for directory in ("contracts", "agent_orchestrator", "scripts", "fixtures", "backend/app"):
        shutil.copytree(
            ROOT / directory, checkout / directory,
            ignore=shutil.ignore_patterns(".git", ".env", ".env.*", "__pycache__", "*.pyc"),
        )
    run(["git", "init", "--quiet"], "git-init")
    run(["git", "config", "user.name", "Offline Fixture Regression"], "git-name")
    run(["git", "config", "user.email", "fixtures@example.invalid"], "git-email")
    run(["git", "add", "contracts", "agent_orchestrator", "scripts", "fixtures", "backend"], "git-add")
    run(["git", "commit", "--quiet", "-m", "Disposable fixture baseline"], "git-baseline")
    no_network = (
        "import socket; "
        "socket.socket.connect=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('Network disabled for fixture checks')); "
    )
    output = run(
        [str(PYTHON), "-c", no_network + "import runpy; runpy.run_path('scripts/mock_e2e.py', run_name='__main__')"],
        "mock-e2e",
    )
    assert "Exit code: 0" in output
    print("Legacy mock E2E: passed (local mock PR_CREATED only).", flush=True)
    for number, expected, invocation in (
        (1, 18, "run_verification(__import__('reference').fused_bias_leaky_relu_cpu, device='cpu')"),
        (2, 6, "run_verification(__import__('reference').sum_reduction_cpu, device='cpu')"),
        (3, 8, "run_verification(device='cpu')"),
    ):
        program = no_network + (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0, str(Path('fixtures/golden-repo-{number:02d}').resolve())); "
            "from test_kernel import run_verification; "
            f"results={invocation}; "
            f"assert len(results)=={expected}, len(results); "
            "assert all(item['passed'] for item in results), results; "
            f"print('Golden {number:02d}: {expected}/{expected} CPU cases passed')"
        )
        print(run([str(PYTHON), "-c", program], f"golden-{number:02d}").strip(), flush=True)
    golden = json.loads((ROOT / "fixtures/golden-repo-01/verification_report.json").read_text(encoding="utf-8"))
    actual = json.loads((checkout / "fixtures/golden-repo-01/verification_report.json").read_text(encoding="utf-8"))
    for item in (golden, actual):
        item.pop("timestamp", None)
        item.pop("summary", None)
    assert golden == actual, "Stable golden report fields differ"
    print("Golden report: all fields match, excluding timestamp and translated summary.", flush=True)
finally:
    after = fixture_hashes()
    assert before == after, "Original fixture hashes changed"
    print(f"Original fixtures unchanged: {len(before)} file hashes match.", flush=True)
