# ROCmigrator

**Vision:** ROCmigrator produces reliable HIP ports from PyTorch Custom CUDA Extension repositories through deterministic HIPIFY conversion, isolated AMD GPU builds, and a bounded repair loop.

**Problem:** When porting CUDA-based PyTorch extensions to the AMD ROCm ecosystem, HIPIFY alone is insufficient; compiler errors, numerical discrepancies, and security vulnerabilities require manual resolution, which is unsustainable within the constraints of a 1-week hackathon.

---

## Architecture

- **Frontend:** Next.js + TypeScript + Monaco Diff Editor + SSE + TanStack Query. User approval, report visualization, status timeline.
- **Control Plane (Backend):** FastAPI + Pydantic v2 + PostgreSQL + Redis + LiteLLM. Explicit Python State Machine (`agent_orchestrator/`); `shell=False`; LLM JSON cannot be parsed without schemas in `contracts/`.
- **AMD Cloud Runner:** Outbound-authenticated daemon on AMD Developer Cloud Linux/ROCm; each job runs in a dedicated non-root GPU container (`runner/`). Local development on Windows WSL2 + VS Code Remote; real compilation occurs exclusively on the AMD runner.

---

## Pipeline (State Machine — Explicit Python)

`CREATED → CLONING → SECURITY_SCAN → ANALYSIS → BASELINE → HIPIFICATION → COMPILING ↔ REPAIR → VERIFYING → BENCHMARKING → REPORT → USER_APPROVAL → PR_CREATED | ROLLED_BACK`

1. **CREATED:** Job definition (repo URL, target branch, repair budget = 6 rounds).
2. **CLONING:** GitHub source acquisition, security scanning (`shell=False`; credentials never enter the container).
3. **ANALYSIS:** Discovery of `.cu/.cuh` and build files; validation of `setup.py` / `torch.utils.cpp_extension.CUDAExtension` boundaries.
4. **BASELINE:** CPU / PyTorch reference derivation (automated tests mandatory; cannot be `VERIFIED` without a reference).
5. **HIPIFICATION:** `hipify-perl` or `hipify-clang` (AST-based); `__CUDA_ARCH__` → `__HIP_ARCH_GFX__`; LOC limit of ≤300 per kernel maintained.
6. **COMPILING ↔ REPAIR:** Error classification (regex/parser fingerprint DB); deterministic tools prioritized; bounded LLM `propose_patch()` only for low-confidence semantic errors. Maximum 6 rounds; same fingerprint at most 2 times.
7. **VERIFYING:** Multi-seed / shape / dtype; `torch.testing.assert_close`; max absolute / relative error; mismatch ratio; NaN / Inf; determinism.
8. **BENCHMARKING:** Execution time / throughput comparison against reference.
9. **REPORT:** JSON (`contracts/verification_schemas.py`) + HTML summary.
10. **USER_APPROVAL:** User approval; followed by PR creation. If not approved, transitions to `ROLLED_BACK`, reverting to the best-known commit.

---

## Scope (MVP — 1 Week / ACT III Hackathon)

**Supported:**
- `setup.py` / `setuptools`; `torch.utils.cpp_extension.CUDAExtension`; `BuildExtension`
- 1–5 `.cu/.cuh` files; total CUDA LOC ≤ 2,000; preferably ≤ 300 LOC per kernel
- Core runtime API; elementwise / reduction; limited `hipCUB`
- Single Linux / AMD GPU; basic compiler errors; CPU / PyTorch reference mandatory
- Automated test mandatory; multi-seed / shape / dtype verification
- Maximum 6 repair rounds; same error fingerprint at most 2 times
- Single patch ≤ 120 lines; total changes ≤ 300 lines or 15% of CUDA LOC
- `git apply --check`; `allowlist`; modifications to dependencies/APIs/tests/tolerances strictly forbidden

**Out of Scope:**
- CUTLASS, NCCL, CUDA Graphs, inline PTX, dynamic parallelism, WMMA, NVRTC, TensorRT
- Complex CMake / Bazel / multi-GPU / distributed training
- Fully autonomous LLM repair (limited semantic errors only; deterministic tools first)
- Windows native GPU compilation (WSL2 developer environment; actual GPU jobs on AMD runner)
- Adding new dependencies; modifying tests / tolerances; modifying public APIs; fake pass via CPU fallback

---

## Setup and Usage (Placeholder)

```bash
# Monorepo
$ git clone <repo> && cd rocmigrator

# 1. Backend (FastAPI + PostgreSQL + Redis)
$ cp backend/.env.example backend/.env
$ docker-compose -f backend/docker-compose.yml up -d db redis
$ pip install -r backend/requirements.txt

# 2. Frontend (Next.js)
$ cd frontend && npm install && npm run dev
# SSE endpoint: /api/logs/stream; Monaco Diff: /editor

# 3. AMD Runner (Cloud — via SSH / Docker daemon)
# runner/config.example → AMD Developer Cloud instance credentials
$ docker-compose -f runner/docker-compose.yml up -d runner
# Build container: non-root (USER 1000), network=none, timeout 300s, cgroup limit

# 4. Mock vertical pipeline (local verification — no physical GPU required)
$ make mock-e2e  # using fixtures/golden-repo-01

# 5. Real end-to-end (AMD runner + user approval + PR)
# Agent engine starts; state machine transitions CREATED → ... → PR_CREATED
```

---

## Team and Measurable Success Metrics

For each role, "Your success depends on":

- **Lead Architect / Strategist (You):** State machine spec, security guardrails, architectural documentation, scope enforcement. *Success: 3/3 golden repos compile + zero orphan containers + zero false verification passes.*
- **Migration / Compiler:** `hipify-clang`/`hipify-perl` integration, error fingerprint DB (regex/parser), deterministic patch policy. *Success: 3/3 repos compile + 100% repair success on matched fingerprints (max 6 rounds).*
- **Cloud / DevOps:** AMD Runner daemon, isolated GPU containers, credential isolation (`network=none`; `shell=False`; credentials never mounted into container). *Success: zero orphan containers + container non-root + outbound-authenticated channel functioning.*
- **Verification:** Numerical verification, determinism, regression fixtures. *Success: max absolute/relative error within tolerance against CPU reference + determinism test passes + 0 NaN/Inf leakage.*
- **Frontend / GitHub:** Monaco Diff, SSE log stream, PR approval flow. *Success: clear end-to-end demo under 5 minutes + PR opened strictly after verification + user approval.*

---

## Security and Guardrails (Fixed Rules)

- `subprocess.run(..., shell=True)` is forbidden; every command executes via argument list (`shell=False`).
- Build container non-root (`USER 1000`); `network=none`; `cgroup` (CPU/memory); disk / PID / timeout limits.
- GitHub / LLM (LiteLLM endpoint) / AMD Cloud credentials are never mounted into containers; runner uses outbound-authenticated channels only.
- LLM is strictly restricted to `propose_patch()`; no terminal / tool / GitHub access; temperature 0–0.1; structured JSON / unified diff mandatory; only 1–3 errors + relevant 80–150 lines sent.
- Patch pipeline: `schema` → `allowlist` → `git apply --check` → `line budget` → `policy check`; rollback to `best-known` commit upon failure.
- No CPU reference means no `VERIFIED`; PR is opened strictly after verification + user approval.
- Maximum 6 repair rounds; stop if no progress for two consecutive rounds; same fingerprint at most 2 times.

---

## Contracts

The `contracts/` directory contains Pydantic v2 schemas; LLM cannot produce JSON without conforming to these schemas. Core models:

- `StateRequest` / `StateTransition` (state machine)
- `PatchProposal` (allowlist, fingerprint, line budget, no dependency/API/test/tolerance change)
- `VerificationReport` (seed/shape/dtype results, assert_close, NaN/Inf, determinism)
- `PRPayload` (user approval flag, rollup report URL)

---

## Hackathon Note

AMD Developer Hackathon ACT III; the 7-day MVP boundary is defined above. Full-scale production, multi-GPU, CUTLASS/NCCL, and autonomous LLM repair are out of scope. Success is measured by completing the engineering loop (build → diagnose → repair → verify → deliver); HIPIFY alone is not enough.

---

## Reference Documents (Informational)
- `STRUCTURE.md`: Physical monorepo directory map; aligned with `README.md` / `ROADMAP.md` / `AGENTS.md`; reference for agents, not an execution script.
- `ROADMAP.md`: 7-day MVP plan; maps directly to directories defined in `STRUCTURE.md` (`contracts/`, `fixtures/`, `runner/`, `agent_orchestrator/`, `frontend/`, `backend/`).
