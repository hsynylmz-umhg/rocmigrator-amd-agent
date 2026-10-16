# ROCmigrator — Monorepo Directory Structure (Reference / Informational)
# This file defines the physical directory layout of the project; it is not executable code.
# Current references: README.md (vision/architecture), ROADMAP.md (7-day plan), AGENTS.md (agent rules).

rocmigrator/
├── README.md                 # Project overview; vision, architecture, pipeline, scope, metrics
├── AGENTS.md                 # Strict directive set for Antigravity IDE / local agent
├── docs/                     # Architectural Decision Records (ADR); optional MVP
│   ├── 001-state-machine.md  # Explicit Python state machine decisions; rejection of LangChain
│   ├── 002-security-guardrail.md # Subprocess, container, credential isolation
│   └── 003-hipify-policy.md  # hipify-perl vs hipify-clang; __CUDA_ARCH__ mapping
│
├── contracts/                # Pydantic v2 schemas; mandatory boundary for LLM JSON parsing
│   ├── __init__.py
│   ├── state_schemas.py      # State transitions: CREATED → ... → PR_CREATED | ROLLED_BACK
│   ├── patch_schemas.py      # PatchProposal: allowlist, fingerprint, max 120 lines
│   ├── verification_schemas.py # Numerical verification: assert_close, NaN/Inf, determinism
│   └── api_schemas.py        # FastAPI request/response contracts
│
├── fixtures/                 # 3 golden repositories; for regression + smoke testing
│   ├── golden-repo-01/       # Basic elementwise; ≤5 .cu; simple setup.py; reference test mandatory
│   ├── golden-repo-02/       # Reduction + limited hipCUB; kernel ≤300 LOC
│   └── golden-repo-03/       # Multi-kernel setup.py; build complexity bounded (no CMake/Bazel)
│
├── frontend/                 # Next.js + TypeScript + Monaco Diff + SSE + TanStack Query
│   ├── src/
│   │   ├── app/              # App router; pages: dashboard, editor, report, approval
│   │   ├── components/       # Monaco Diff Editor; State Timeline; Report Card
│   │   ├── hooks/            # TanStack Query; SSE consumer (/api/logs/stream mandatory)
│   │   └── lib/              # Helpers; schema imports (contracts/ reference)
│   ├── public/
│   └── package.json
│
├── backend/                  # FastAPI + Pydantic + PostgreSQL + Redis + LiteLLM
│   ├── app/
│   │   ├── api/              # REST / SSE endpoints; /state, /patch/propose, /verify, /approve
│   │   ├── core/             # State machine orchestrator; explicit Python; no LangChain
│   │   ├── services/         # Clone, SecurityScan, HIPIFY, Compile, Repair, Verify, Benchmark, Report
│   │   ├── contracts/        # Pydantic import layer (connects contracts/ directory)
│   │   └── db/               # PostgreSQL migrations; Redis queue config; Celery/Dramatiq
│   ├── requirements.txt      # fastapi, pydantic, sqlalchemy, redis, litellm, torch (CPU ref)
│   └── docker-compose.yml    # db, redis, backend; runner is not connected as a compose service
│
├── agent_orchestrator/       # Explicit Python State Machine; deterministic; LangChain rejected
│   ├── engine.py             # Main loop; max 6 repair rounds; rollback best-known; fingerprint DB
│   ├── states/               # Transition handlers for each state (CREATED → ... → PR_CREATED)
│   ├── fingerprints/         # Compiler error fingerprint DB (regex / parser; deterministic)
│   ├── policies/             # Patch policy: allowlist, line budget (≤120/≤300), dependency/API lock
│   └── rollback.py           # Revert to best-known commit; regression detection
│
├── runner/                   # AMD Developer Cloud isolated GPU container; Docker AMD isolation
│   ├── Dockerfile.runner     # Non-root (USER 1000); minimal ROCm image; network off by default
│   ├── entrypoint.sh         # Shell=False guard; timeout/cgroup/disk/PID limits; no credentials
│   ├── docker-compose.yml    # Dedicated container per job; SSH tunnel for outbound auth
│   ├── config.example        # AMD instance SSH / Docker daemon / public IP settings
│   └── smoke_amd.sh          # AMD runner smoke test: compile + verify + benchmark (with fixture)
│
└── scripts/                  # Utilities; local verification; mock vertical pipeline
    ├── mock_e2e.py           # End-to-end mock using golden-repo-01 (no GPU required)
    ├── security_scan.sh      # Post-clone security scanning (shell=False; list args)
    └── generate_report.py    # Report generation (contracts/verification_schemas.py format)

---

## Linked Documents (Informational)
- **README.md:** Project vision, architecture, pipeline, scope, team metrics, setup placeholders.
- **ROADMAP.md:** 7-day MVP plan; daily objectives implementing this directory structure.
- **AGENTS.md:** Agent behavioral boundaries; `shell=False`, mandatory `Pydantic`, `SSE`, repair limits.
- **contracts/ / fixtures/ / runner/ / agent_orchestrator/:** Physical directory implementations aligned with documentation.

Note: This file is for informational purposes only; it is not processed automatically. The agent uses this file as a reference for `agent_orchestrator/` or `backend/` and does not generate commands from it.
