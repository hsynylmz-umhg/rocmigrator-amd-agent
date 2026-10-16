# ROCmigrator — 7-Day MVP Roadmap (AMD Developer Hackathon ACT III)
# Lead Architect / Strategist output; consistent with AGENTS.md + README.md + STRUCTURE.md.
# Scope expansion is forbidden; strictly enforces existing architecture and MVP boundaries.

---

## 1. Fixed Scope and Exclusions (Invariant Throughout Roadmap)

- `setup.py` / `torch.utils.cpp_extension.CUDAExtension`; 1–5 `.cu/.cuh` files; total CUDA LOC ≤ 2,000; kernel ≤ 300 LOC.
- Single Linux / AMD GPU; core runtime API; elementwise / reduction; limited hipCUB.
- CPU / PyTorch reference mandatory; automated testing mandatory; determinism mandatory.
- Maximum 6 repair rounds; same error fingerprint at most 2 times; single patch ≤ 120 lines; total ≤ 300 lines or 15% of CUDA LOC.
- Adding dependencies, modifying tests / tolerances, modifying public APIs, fake pass via CPU fallback, and emptying kernels are strictly forbidden.
- CUTLASS, NCCL, CUDA Graphs, inline PTX, dynamic parallelism, WMMA, NVRTC, TensorRT, complex CMake / Bazel, and multi-GPU are strictly out of scope.
- LLM is strictly limited to `propose_patch()`; temperature 0–0.1; structured JSON / unified diff; 1–3 errors + 80–150 lines; no terminal / tool / GitHub access.
- Build container non-root (`USER 1000`); `network=none`; `shell=False`; `cgroup`; credentials never mounted into container; runner outbound-authenticated channel.
- PR opened strictly after verification + user approval (`USER_APPROVAL`); agent never opens a PR autonomously.
- Windows development in WSL2; actual GPU workloads strictly run on AMD Developer Cloud runner.

---

## 2. Day-by-Day Plan (Aligned with State Machine)

### Day 1 — CREATED → CLONING + SECURITY_SCAN
- **Pipeline Objective:** Create job; clone 3 golden repos; run security scan; validate agent directives parse.
- **Deliverables:** `fixtures/golden-repo-01/02/03/`; `scripts/security_scan.sh`; agent rules verification report.
- **Role:** Lead Architect / Strategist + Cloud / DevOps.
- **Success Criteria (Your success):** 3 repos successfully cloned; zero orphan containers; zero credential leaks; `AGENTS.md` cleanly parseable.
- **Guardrails:** No additional repos added; each repo ≤5 `.cu` files; `shell=False` mandatory in every `subprocess`.

### Day 2 — ANALYSIS + BASELINE
- **Pipeline Objective:** Source discovery (`.cu/.cuh`, `setup.py`, verify absence of CMake/Bazel); derive CPU / PyTorch reference tests.
- **Deliverables:** Source mapping report; reference test code based on `contracts/verification_schemas.py`; simple elementwise reference working in `fixtures/`.
- **Role:** Migration / Compiler + Verification.
- **Success Criteria:** All `.cu/.cuh` files mapped; CPU reference tests running; `BASELINE` state valid.
- **Guardrails:** HIPIFY not started yet; no LLM patches used; build not yet on AMD runner (analysis only).

### Day 3 — HIPIFICATION
- **Pipeline Objective:** Deterministic conversion via `hipify-perl` or `hipify-clang`; `__CUDA_ARCH__` → `__HIP_ARCH_GFX__` mapping; header mapping.
- **Deliverables:** Converted source (branch `hipified/`); initial compiler errors for `agent_orchestrator/fingerprints/`; LOC per kernel verified.
- **Role:** Migration / Compiler.
- **Success Criteria:** 3 repos successfully hipified; ≤300 LOC per kernel maintained; no new dependencies.
- **Guardrails:** No manual rewrites; deterministic tools prioritized; `hipify-clang` AST-based preferred (when headers available).

### Day 4 — COMPILING (Initial Isolated Build)
- **Pipeline Objective:** First isolated container compilation on AMD Developer Cloud runner; `runner/Dockerfile.runner` (non-root, `network=none`), `entrypoint.sh` (timeout/cgroup); error classification begins.
- **Deliverables:** First `COMPILING` attempt completed; `fingerprints/` DB updated; container logs streamed to `backend/` via SSE.
- **Role:** Cloud / DevOps + Migration / Compiler.
- **Success Criteria:** Initial compilation attempt completed; errors classified via regex/parser; container non-root, `shell=False`, `network=none`; zero orphan containers.
- **Guardrails:** Repair loop not started yet (diagnose only); max 6 repair budget untouched; no dependencies added.

### Day 5 — REPAIR (Bounded, Constrained)
- **Pipeline Objective:** `COMPILING ↔ REPAIR` loop; deterministic tools prioritized; bounded LLM `propose_patch()` only for low-confidence semantic errors; rollback testing.
- **Deliverables:** Repair rounds (≤6); patch ≤120 lines; total ≤300 lines; `git apply --check`; `best-known` rollback mechanism verified.
- **Role:** Migration / Compiler + Lead Architect (guardrail check at the end of each round).
- **Success Criteria:** Repair rounds completed successfully; same fingerprint at most 2 times; rollback executes if no progress for 2 rounds; no dependency/API/test/tolerance changes.
- **Guardrails:** `allowlist` check mandatory; LLM temperature 0–0.1; 1–3 errors + 80–150 lines; patch rejected if `git apply --check` fails.

### Day 6 — VERIFYING + BENCHMARKING
- **Pipeline Objective:** Multi-seed / shape / dtype; `torch.testing.assert_close`; max absolute / relative error; mismatch ratio; NaN / Inf; determinism; comparison with CPU reference.
- **Deliverables:** Report in `contracts/verification_schemas.py` format; `benchmarking/` results; ready for `REPORT` state.
- **Role:** Verification.
- **Success Criteria:** All repos pass verification; max absolute/relative error within tolerance; determinism test passes; zero NaN/Inf leakage.
- **Guardrails:** Cannot be `VERIFIED` without CPU reference; tests / tolerances cannot be altered; fake pass forbidden.

### Day 7 — REPORT → USER_APPROVAL → PR_CREATED (or ROLLED_BACK)
- **Pipeline Objective:** Generate reports (JSON + HTML); `USER_APPROVAL`; PR creation; clear demo under 5 minutes; video/slides deliverable; regression repeated across all `fixtures/`.
- **Deliverables:** `REPORT`; PR draft (user approved); visualization with `frontend/` Monaco Diff + SSE log stream; demo recording.
- **Role:** Frontend / GitHub + Entire Team (for demo).
- **Success Criteria:** Clear end-to-end demo under 5 minutes; PR opened strictly after verification + user approval; zero false verification passes; zero orphan containers.
- **Guardrails:** Agent does not open PR autonomously; if user rejects, transitions to `ROLLED_BACK`; reverts to best-known commit; no new features added.

---

## 3. Integration Points (Connection to Existing Directory Structure)

- **contracts/ ↔ backend/api/:** `Pydantic v2` schemas; LLM JSON output parsed strictly here; `PatchProposal`, `VerificationReport`, `StateRequest` mandatory.
- **fixtures/ ↔ runner/:** 3 golden repos; `smoke_amd.sh`; regression tests run at the end of each day or after each repair.
- **agent_orchestrator/ ↔ backend/core/:** Explicit Python state machine (`engine.py`); no `LangChain`; state transitions defined under `states/`; rollback to best-known commit via `rollback.py`.
- **AGENTS.md ↔ agent/ (Antigravity IDE):** Parseable bullet directives; scope, rejection of LangChain, `shell=True` forbidden, `Pydantic` mandatory, SSE mandatory, repair limits, PR approval — agent cannot override these rules.
- **frontend/ ↔ backend/:** SSE `/api/logs/stream`; Monaco Diff Editor; TanStack Query; user approval triggered via `USER_APPROVAL` event.
- **docs/ (optional ADR):** `001-state-machine.md` (rejection of LangChain), `002-security-guardrail.md` (subprocess/container isolation), `003-hipify-policy.md` (hipify-clang vs perl) — kept for architectural reference.

---

## 4. Risk, Fallback, and Boundary Controls

| Risk | Impact | Control / Fallback |
|---|---|---|
| `hipify-perl` macro/template error | Incomplete conversion | Prefer AST-based `hipify-clang`; manual mapping only within allowlist; rollback to `best-known` |
| LLM hallucination / incorrect patch | Compiler errors increase or API changes | `temperature 0–0.1`; `schema` + `allowlist` + `git apply --check`; 1–3 errors + 80–150 line limit; same fingerprint max 2x; stop after 2 rounds with no progress |
| AMD runner connectivity outage | Compilation halts | Use local `mock_e2e.py` with `fixtures/`; real GPU strictly on runner; rollback protects last successful commit |
| Missing CPU reference | Verification cannot run | `BASELINE` mandatory; cannot be `VERIFIED` without reference; PR cannot be opened |
| Security / credential leak | Container / runner compromise | `shell=False`; `network=none`; credentials never mounted into container; outbound-authenticated channel; non-root `USER 1000` |
| Scope creep (CUTLASS, NCCL, multi-GPU) | 1-week MVP failure | Re-check `README.md` Scope section at start of each day; reject any command violating rule 1 of `AGENTS.md` |

---

## 5. Document Relationships (How This File Relates to Others)

- **README.md:** Vision, architecture, pipeline, scope, team metrics, setup placeholders — strategic counterpart to this roadmap.
- **STRUCTURE.md (Reference / Informational):** Defines physical monorepo directory layout; not an executable code file. Deliverables mentioned on each day of this roadmap (`contracts/`, `fixtures/`, `runner/`, `agent_orchestrator/`, `frontend/`, `backend/`) reside in this tree. Agent uses `STRUCTURE.md` as reference for `agent_orchestrator/` or `backend/`, does not generate commands from it; read alongside `AGENTS.md`. Daily plan connects directly to these directories (e.g., Day 1: `fixtures/` cloning; Day 3: `agent_orchestrator/` state transition; Day 5: `contracts/` schema check; Day 6: `runner/` smoke test).
- **AGENTS.md:** Agent behavioral boundaries — every step in this roadmap obeys `AGENTS.md` rules (e.g., Day 4 `shell=False`; Day 5 `patch ≤120 lines`; Day 7 mandatory PR approval).
- **contracts/ / fixtures/ / runner/ / agent_orchestrator/:** Physical directories where daily deliverables are produced; roadmap directly references them.

---

## 6. .gitignore Notes (Which Files Are Tracked)

- **ROADMAP.md (this file):** Strategic document; required for Antigravity IDE agent; **must not** be added to `.gitignore`; must be tracked.
- **TASKS.md (if present):** Granular task tracking or agent scratch file; can be added to `.gitignore` if used; currently only `ROADMAP.md` is generated; `TASKS.md` does not exist and is not in `.gitignore`.
- **Standard exclusions:** Standard entries like `__pycache__/`, `.env`, `node_modules/`, `*.pyc`, `.venv/`, `build/`, `dist/`, `.idea/` are in `.gitignore`; documentation files are not excluded.

---

## 7. Deliverables Summary (Day 7 Goal — MVP Completed)

- `CREATED` → `PR_CREATED` or `ROLLED_BACK` state is valid.
- `HIPIFY` + `COMPILING` + `REPAIR` (≤6 rounds) + `VERIFYING` + `BENCHMARKING` + `REPORT` + `USER_APPROVAL` completed for 3 golden repos.
- Report available in `contracts/verification_schemas.py` format; visualized via `frontend/`; `backend/` SSE log streaming operational.
- Security guardrails: zero orphan containers; zero credential leaks; `shell=False`; non-root; `network=none`; PR user-approved.
- Out of scope: CUTLASS, NCCL, CUDA Graphs, inline PTX, WMMA, NVRTC, TensorRT, multi-GPU, complex CMake/Bazel; no new dependencies.
- Team metrics: 3/3 repos compile; zero false verification passes; zero orphan containers; 5-minute demo; PR opened only after `USER_APPROVAL`.
