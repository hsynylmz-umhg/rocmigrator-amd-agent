# ROCmigrator

### Autonomous CUDA-to-ROCm Migration Agent

**From CUDA source code to a verified AMD ROCm/HIP pull request — with real GPU execution and human approval.**

ROCmigrator is an autonomous engineering agent designed to migrate PyTorch CUDA C++ extensions to the AMD ROCm/HIP ecosystem.

It combines deterministic CUDA-to-HIP source transformation, isolated compilation, real AMD GPU execution, numerical verification, bounded AI-assisted repair, and an explicit human approval gate before creating a GitHub pull request.

Unlike tools that stop after source translation, ROCmigrator attempts to complete the engineering workflow: **analyze, transform, compile, verify, benchmark, review, and deliver.**

The project was developed for **AMD Developer Hackathon — ACT III** and successfully validated on an **AMD Instinct MI300X VF**.

---

## Watch the Demo

[![ROCmigrator — AMD Developer Hackathon ACT III](https://img.youtube.com/vi/9kzPMyuCNyk/hqdefault.jpg)](https://youtu.be/9kzPMyuCNyk)

### [▶ Watch the ROCmigrator Demo on YouTube](https://youtu.be/9kzPMyuCNyk)

The approximately two-minute demonstration shows an actual migration performed through the ROCmigrator interface.

The recording includes:

- Repository configuration and migration launch.
- Execution of the migration state machine.
- Security scanning and CPU reference generation.
- Deterministic CUDA-to-HIP transformation.
- Inspection of the generated code changes.
- Real HIP compilation targeting AMD `gfx942`.
- Real AMD Instinct MI300X GPU verification.
- Numerical correctness and determinism results.
- Explicit human approval.
- Automatic creation of GitHub Pull Request #1.

The technical execution footage is based on a real application run. Cinematic opening and closing visuals are presentation elements, not simulated GPU execution.

**Verified result: 18/18 numerical tests passed · CPU reference verified · Determinism passed · GitHub PR #1 created**

[Source Repository](https://github.com/hsynylmz-umhg/rocmigrator-amd-agent) |
[Verified GitHub Pull Request #1](https://github.com/hsynylmz-umhg/rocmigrator-amd-agent/pull/1)

---

## Table of Contents

1. [Overview](#overview)
2. [The Problem](#the-problem)
3. [How ROCmigrator Works](#how-rocmigrator-works)
4. [Verified Results on AMD Instinct MI300X](#verified-results-on-amd-instinct-mi300x)
5. [System Architecture](#system-architecture)
6. [Migration State Machine](#migration-state-machine)
7. [Technology Stack](#technology-stack)
8. [Prerequisites](#prerequisites)
9. [Quick Start](#quick-start)
10. [Configuring the AMD GPU Runner](#configuring-the-amd-gpu-runner)
11. [Reproducing the Golden 01 Migration](#reproducing-the-golden-01-migration)
12. [Numerical Verification](#numerical-verification)
13. [Compilation and Repair](#compilation-and-repair)
14. [Benchmarking](#benchmarking)
15. [Human Approval and GitHub Integration](#human-approval-and-github-integration)
16. [Security and Isolation](#security-and-isolation)
17. [Running Tests](#running-tests)
18. [Repository Structure](#repository-structure)
19. [Troubleshooting](#troubleshooting)
20. [Limitations](#limitations)
21. [Reproducibility and Evidence](#reproducibility-and-evidence)
22. [Hackathon](#hackathon)

---

# Overview

ROCmigrator is an engineering workflow for migrating supported PyTorch CUDA extension repositories to AMD ROCm/HIP.

The system coordinates multiple stages that would otherwise require manual interaction between source transformation tools, compilers, GPU test environments, numerical verification scripts, and GitHub.

Its primary objective is not simply to produce HIP-compatible source code.

Its objective is to produce a **reviewable migration backed by compilation and verification evidence**.

The workflow combines:

1. Repository acquisition and security checks.
2. CUDA source analysis.
3. CPU reference preparation.
4. Deterministic HIPIFY transformation.
5. ROCm/HIP compilation.
6. Bounded repair when compilation fails.
7. Real GPU execution.
8. Numerical correctness verification.
9. Determinism testing.
10. GPU benchmarking.
11. Human review and approval.
12. GitHub pull request creation.

The successful Golden 01 demonstration completed this workflow without requiring an AI repair round.

---

# The Problem

Migrating custom PyTorch CUDA extensions to AMD ROCm is more complicated than replacing CUDA API names.

A source transformation can produce code that appears compatible with HIP while leaving important engineering questions unanswered.

For example:

- Does the translated extension compile with the installed ROCm toolchain?
- Are the generated HIP headers and runtime APIs correct?
- Does the extension execute on an actual AMD GPU?
- Does it produce numerically equivalent results?
- Are numerical differences within acceptable tolerances?
- Does the implementation behave consistently across repeated executions?
- Can a failed compilation be repaired without introducing unsafe modifications?
- Can the final changes be reviewed before they are submitted upstream?

A translation-only workflow cannot answer these questions.

ROCmigrator addresses this gap by connecting source migration to real compilation, execution, verification, and review.

## Design Principles

ROCmigrator follows several principles:

**Deterministic transformation first**

Use established CUDA-to-HIP transformation tools before considering AI-generated changes.

**Real execution over simulated success**

A successful GPU verification requires actual execution on compatible AMD hardware.

**Numerical evidence**

Correctness is established by comparing GPU results against a CPU reference rather than relying only on successful compilation.

**Bounded automation**

Repair attempts are constrained by an explicit budget and validation policies.

**Human-controlled delivery**

The agent must obtain explicit user approval before creating a GitHub pull request.

**Auditable results**

State transitions, generated changes, compiler results, and verification outcomes are exposed through the application interface.

---

# How ROCmigrator Works

At a high level, the workflow is:

```text
                        CUDA Extension Repository
                                   |
                                   v
                         +-------------------+
                         | Repository Import |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | Security Analysis |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | Source Inspection |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         |   CPU Baseline    |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | Deterministic     |
                         | HIPIFY Conversion |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | ROCm HIP Compiler |
                         +-------------------+
                              |          |
                           Success     Failure
                              |          |
                              |          v
                              |    +-------------+
                              |    | Bounded AI  |
                              |    | Repair      |
                              |    +-------------+
                              |          |
                              |          |
                              |     Retry Compile
                              |          |
                              +<---------+
                              |
                              v
                         +-------------------+
                         | AMD GPU Execution |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | Numerical Tests   |
                         | CPU Comparison    |
                         | Determinism       |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | GPU Benchmarking  |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | Verification      |
                         | Report            |
                         +-------------------+
                                   |
                                   v
                         +-------------------+
                         | Human Approval    |
                         +-------------------+
                                   |
                              Approved?
                              /       \
                            Yes        No
                             |          |
                             v          v
                       GitHub PR     Rollback
                             |
                             v
                         PR_CREATED
```

This diagram describes the intended control flow. The repair branch is conditional and was not exercised during the successful Golden 01 run.

---

# Verified Results on AMD Instinct MI300X

ROCmigrator was successfully tested on a real AMD Instinct MI300X virtual function through AMD Developer Cloud.

## Hardware Environment

| Component | Verified Environment |
|---|---|
| GPU | AMD Instinct MI300X VF |
| GPU architecture | `gfx942` |
| GPU memory | 192 GB class |
| Operating system | Linux |
| GPU execution | Real AMD hardware |
| Compiler | ROCm HIP compiler (`hipcc`) |
| Execution isolation | Docker-based runner |
| Workload | Golden 01 PyTorch CUDA extension |
| Pipeline outcome | `PR_CREATED` |

The successful test used an AMD ROCm-enabled PyTorch environment and an isolated runner container.

The observed GPU architecture identifier included:

```text
gfx942:sramecc+:xnack-
```

The ROCm compiler was invoked with the AMD architecture target:

```text
--offload-arch=gfx942
```

## Golden 01 Verification Results

| Metric | Observed Result |
|---|---|
| Numerical comparisons | **18/18 PASS** |
| CPU reference verification | **PASS** |
| Determinism | **PASS** |
| NaN/Inf validation | **PASS** |
| Security scan | **0 violations** |
| HIP compilation | **SUCCESS** |
| AMD GPU execution | **SUCCESS** |
| AI repair rounds | **0** |
| Human approval | **GRANTED** |
| Final pipeline state | **PR_CREATED** |
| GitHub pull request | **#1 created** |

These results describe the successful Golden 01 demonstration, not a claim that arbitrary CUDA repositories will migrate successfully.

## Verification Coverage

The demonstrated numerical verification used:

**Random seeds**

```python
[42, 1337, 2026]
```

**Tensor shapes**

```python
[
    [128, 64],
    [32, 128, 256],
    [1024],
]
```

**Data types**

```python
[
    "torch.float32",
    "torch.float64",
]
```

This produces:

```text
3 seeds
× 3 shapes
× 2 data types
= 18 verification cases
```

All 18 required cases passed.

## Real GitHub Evidence

The verified migration resulted in a real GitHub pull request:

**[Pull Request #1 — Port verified extension to ROCm/HIP](https://github.com/hsynylmz-umhg/rocmigrator-amd-agent/pull/1)**

The pull request was created after successful verification and explicit user approval.

Creation of a pull request does not mean it has been merged.

---

# System Architecture

ROCmigrator separates the user interface, orchestration logic, migration contracts, and GPU execution environment.

```text
+---------------------------------------------------------+
|                  Developer Browser                      |
|                                                         |
|                 ROCmigrator Web UI                      |
|                                                         |
|          Next.js / TypeScript / Tailwind CSS             |
+----------------------------+----------------------------+
                             |
                             | HTTP / Live Updates
                             |
                             v
+---------------------------------------------------------+
|                    FastAPI Backend                      |
|                                                         |
|  Job Management                                         |
|  Explicit State Machine                                 |
|  Migration Orchestration                                |
|  Security Policies                                      |
|  Verification Reports                                   |
|  User Approval                                          |
|  GitHub Integration                                     |
+----------------------------+----------------------------+
                             |
                             | Validated Contracts
                             |
                             v
+---------------------------------------------------------+
|                  Migration Components                   |
|                                                         |
|  Repository Analysis                                    |
|  CPU Reference                                          |
|  HIPIFY Transformation                                  |
|  Compilation Coordination                               |
|  Bounded Repair                                         |
|  Verification                                           |
|  Benchmarking                                           |
+----------------------------+----------------------------+
                             |
                             | Isolated Execution
                             |
                             v
+---------------------------------------------------------+
|                  AMD GPU Runner                         |
|                                                         |
|  Linux + ROCm                                           |
|  Docker Isolation                                       |
|  hipcc                                                  |
|  PyTorch ROCm                                           |
|  AMD Instinct MI300X                                    |
+---------------------------------------------------------+
```

## Frontend

The frontend provides the main interface for configuring and observing migration jobs.

Its responsibilities include:

- Repository and target branch configuration.
- Repair-budget configuration.
- Starting migration jobs.
- Displaying state-machine progress.
- Showing live execution output.
- Inspecting generated source changes.
- Displaying numerical verification results.
- Presenting the explicit approval action.
- Reporting the final GitHub PR outcome.

The frontend is implemented using Next.js, TypeScript, and Tailwind CSS.

## Backend

The FastAPI backend coordinates the migration lifecycle.

It manages:

- Job creation.
- State transitions.
- Migration execution.
- Runner integration.
- Verification reports.
- Approval decisions.
- GitHub pull request creation.

The pipeline is controlled by an explicit Python state machine rather than allowing an LLM to select arbitrary tools.

## Contracts

Pydantic v2 models provide structured validation boundaries for application data.

Contracts are used to represent migration requests, state transitions, patch proposals, verification results, and related workflow objects.

## AMD Runner

The AMD runner is responsible for operations that require the real ROCm execution environment.

These include:

- Running HIPIFY-related tooling.
- Invoking the HIP compiler.
- Building the translated extension.
- Executing GPU workloads.
- Comparing GPU output with reference results.
- Collecting benchmark evidence.

For real-mode operation, the runner requires access to compatible AMD GPU devices.

---

# Migration State Machine

ROCmigrator implements the following lifecycle:

```text
CREATED
   |
   v
CLONING
   |
   v
SECURITY_SCAN
   |
   v
ANALYSIS
   |
   v
BASELINE
   |
   v
HIPIFICATION
   |
   v
COMPILING <------+
   |             |
   | failure     |
   v             |
REPAIR ----------+
   |
   | compilation succeeds
   v
VERIFYING
   |
   v
BENCHMARKING
   |
   v
REPORT
   |
   v
USER_APPROVAL
   |
   | explicit approval
   v
PR_CREATED
```

Failure or rejection can lead to:

```text
ROLLED_BACK
```

## Stage Descriptions

### 1. CREATED

Initializes the migration job and its configuration.

The job includes information such as the source repository, target branch, and repair budget.

### 2. CLONING

Acquires or exports the source repository into the controlled migration workspace.

The original repository should remain unchanged during analysis and verification.

### 3. SECURITY_SCAN

Checks the input repository against the implemented security policies.

A repository that violates required safety checks must not proceed as a verified migration.

### 4. ANALYSIS

Inspects CUDA source files and relevant build configuration.

The analysis helps determine which files and APIs need transformation.

### 5. BASELINE

Prepares or evaluates CPU reference results used for correctness verification.

A successful compilation alone is not sufficient to establish numerical correctness.

### 6. HIPIFICATION

Applies deterministic CUDA-to-HIP transformation.

HIPIFY is used before AI-assisted repair.

### 7. COMPILING

Builds the translated extension using the ROCm/HIP toolchain.

The demonstrated MI300X run targeted:

```text
gfx942
```

### 8. REPAIR

If compilation fails, the bounded repair mechanism may propose constrained changes.

Repair is conditional.

**The successful Golden 01 migration required zero repair rounds.**

### 9. VERIFYING

Runs the compiled extension and compares results with the CPU reference.

The verification stage evaluates numerical correctness and determinism.

### 10. BENCHMARKING

Collects performance measurements from the supported execution environment.

Benchmark data should be interpreted together with the test configuration and hardware context.

### 11. REPORT

Produces the verification information presented to the user.

### 12. USER_APPROVAL

The workflow pauses for an explicit human decision.

A GitHub pull request must not be created before approval.

### Final State: PR_CREATED

After successful verification and user approval, ROCmigrator creates the migration pull request.

---

# Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js |
| Frontend language | TypeScript |
| Styling | Tailwind CSS |
| Backend | FastAPI |
| Data validation | Pydantic v2 |
| Orchestration | Python state machine |
| CUDA transformation | HIPIFY |
| GPU compiler | ROCm HIP compiler (`hipcc`) |
| GPU framework | PyTorch with ROCm |
| Execution environment | Linux |
| Isolation | Docker |
| GPU hardware | AMD Instinct MI300X |
| AI-assisted repair | OpenAI integration |
| Source control integration | GitHub API |
| Numerical verification | PyTorch reference comparison |

Some components require environment-specific configuration.

The presence of an AI-assisted repair capability does not imply that every migration invokes an LLM.

---

# Prerequisites

ROCmigrator has two distinct execution environments:

1. The development and application environment.
2. A compatible AMD ROCm GPU environment for real migration execution.

These can run on the same Linux machine or be separated across a development computer and a remote AMD GPU host.

## Development Requirements

Recommended tools:

- Git.
- Python 3.
- Node.js and npm.
- A modern browser.
- Docker, where required by the selected execution environment.

Use a Python version compatible with the project's dependency files.

For the frontend, use a Node.js version supported by the installed Next.js release.

## Real AMD GPU Requirements

To reproduce real HIP compilation and GPU verification, you need:

- A supported Linux environment.
- A compatible AMD GPU.
- Working AMD GPU kernel drivers.
- A compatible ROCm installation.
- ROCm/HIP compiler tools.
- Docker with access to the AMD GPU device nodes.
- A PyTorch build compatible with the ROCm environment.

The original successful verification used:

```text
AMD Instinct MI300X VF
gfx942
```

Other supported AMD devices may require different architecture targets, runner images, and build settings.

## Optional GitHub Integration Requirements

To create pull requests automatically, configure GitHub authentication with only the permissions required by the integration.

Use a repository-scoped token where possible.

Never commit GitHub tokens to source control.

## Optional AI Repair Requirements

An OpenAI API key may be required when the configured repair workflow needs an LLM.

The Golden 01 success did not require an AI repair round.

---

# Quick Start

The following setup describes the general development layout used during the demonstration:

- Frontend on a Windows development machine.
- Backend and real runner on an AMD ROCm-enabled Linux host.
- SSH port forwarding between the two environments.

You can adapt this arrangement to your infrastructure.

## 1. Clone the Repository

```bash
git clone https://github.com/hsynylmz-umhg/rocmigrator-amd-agent.git
cd rocmigrator-amd-agent
```

## 2. Configure the Backend

On the Linux machine that will run the backend:

```bash
cd backend
```

Create a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install backend dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Configure environment variables using the repository's example configuration, if provided.

For example:

```bash
cp .env.example .env
```

Do not overwrite an existing `.env` file containing valid configuration.

Configure the variables required by your deployment before starting the backend.

### Real-Mode Environment Example

The successful MI300X deployment used the following runner-related settings:

```dotenv
ROCMIGRATOR_MODE=real

RUNNER_IMAGE=rocmigrator-runner:mi300x

AMD_RENDER_DEVICE=/dev/dri/renderD129

AMD_RENDER_GID=992
AMD_KFD_GID=992

PYTORCH_ROCM_ARCH=gfx942
```

**These are values from one verified environment, not universal defaults.**

In particular:

- The render device may not be `/dev/dri/renderD129`.
- The render and KFD group IDs may be different.
- The runner image name may differ.
- The GPU architecture target must match your hardware.

Do not blindly copy these values to another server.

## 3. Start the Backend

From the backend directory, with the Python environment activated:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This assumes the repository's FastAPI application is exposed as `app` in `app/main.py`.

If your checkout uses a different module path, use the actual application entry point.

The backend should become available at:

```text
http://127.0.0.1:8000
```

Do not expose development API endpoints directly to the public internet without appropriate authentication and network protections.

## 4. Start the Frontend

On the development machine:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend must be configured to reach the correct backend API endpoint.

## 5. Connect to a Remote Backend

If the backend is running on a remote AMD GPU machine, SSH port forwarding can make it available locally.

Example:

```bash
ssh -N -L 8000:127.0.0.1:8000 USER@AMD_GPU_HOST
```

Replace:

```text
USER
AMD_GPU_HOST
```

with your own SSH username and server hostname or IP address.

Do not use credentials belonging to another deployment.

With the tunnel active, the remote backend can be accessed locally through:

```text
http://127.0.0.1:8000
```

This setup avoids publicly exposing the backend port.

---

# Configuring the AMD GPU Runner

Real ROCm compilation and GPU execution require a correctly configured Linux host.

## 1. Verify GPU Availability

On the AMD GPU host:

```bash
ls -l /dev/kfd
ls -l /dev/dri/
```

A working ROCm installation should expose the appropriate AMD GPU device nodes.

Inspect the available render devices:

```bash
ls -l /dev/dri/renderD*
```

Do not assume the first render node corresponds to the compute GPU.

On systems with multiple graphics or accelerator devices, different render nodes may represent different hardware.

## 2. Identify the Correct GPU

If available, inspect the GPU with:

```bash
rocminfo
```

You can also use:

```bash
rocm-smi
```

depending on the installed ROCm environment.

For the original MI300X deployment, the relevant architecture was:

```text
gfx942
```

## 3. Check Device Group IDs

Inspect the ownership of the selected devices.

For example:

```bash
stat -c '%n %a %U %G %g' /dev/kfd /dev/dri/renderD*
```

The numeric group IDs may be required when passing GPU access to a non-root Docker container.

The verified MI300X deployment used:

```text
AMD_RENDER_GID=992
AMD_KFD_GID=992
```

Your system may use different values.

## 4. Configure the Runner Image

The demonstrated environment used:

```text
rocmigrator-runner:mi300x
```

The image must provide the toolchain and runtime expected by ROCmigrator.

At minimum, the real execution workflow requires compatible versions of:

- ROCm/HIP.
- The HIP compiler.
- PyTorch with ROCm support.
- Python dependencies required by the workload.
- Build tools and headers required by the extension.

Use the runner Dockerfile and build configuration included in the repository.

The image tag above identifies the successful deployment's runner image; it does not imply that the image is publicly published.

## 5. Verify Docker GPU Access

The container must receive access to the correct AMD GPU devices.

Typical AMD GPU device mappings include:

```text
/dev/kfd
/dev/dri/renderD*
```

Only the render device corresponding to the intended GPU should be selected.

The successful deployment required the correct numerical device group IDs.

This matters because a container can have access to `/dev/kfd` while still being unable to use the selected GPU if render-node permissions are incorrect.

## 6. Select the GPU Architecture

For MI300X:

```dotenv
PYTORCH_ROCM_ARCH=gfx942
```

The HIP compiler uses an architecture-specific target.

For example:

```text
--offload-arch=gfx942
```

Other GPUs require their corresponding architecture configuration.

## 7. Enable Real Execution Mode

Configure:

```dotenv
ROCMIGRATOR_MODE=real
```

Real mode must use the actual runner, compiler, and GPU execution path.

Do not treat simulated execution or mock verification as evidence of successful AMD GPU migration.

---

# Reproducing the Golden 01 Migration

The Golden 01 fixture is the demonstrated workload used to validate the end-to-end pipeline.

It represents a supported PyTorch CUDA extension migration scenario.

## 1. Start the Application

Ensure:

- The AMD GPU is visible to the ROCm environment.
- The runner image is available.
- The backend can communicate with the runner execution environment.
- The frontend can access the backend.
- Required environment variables are configured.

Open the ROCmigrator web interface.

## 2. Configure the Migration

In the migration configuration panel, use:

**Repository path**

```text
fixtures/golden-repo-01
```

**Target branch**

```text
hip-port
```

**Repair budget**

```text
3
```

These are the values shown in the recorded Golden 01 demonstration.

The repair budget specifies the maximum permitted number of repair attempts.

It does not mean the system will necessarily perform repair.

## 3. Start Migration

Click:

**Start migration**

The application begins executing the state machine.

The live interface displays the current stage and execution output.

## 4. Observe Repository Analysis

The demonstrated run analyzed a small CUDA fixture.

The runner reported that it analyzed:

```text
1 CUDA source
14 CUDA lines
```

This is a deliberately bounded example intended to make the complete migration workflow reproducible and inspectable.

## 5. Observe Security Scanning

The successful run reported:

```text
Security scan completed successfully
0 violations
```

This result applies to the tested fixture.

It does not imply that every repository will pass the scan.

## 6. Observe CPU Baseline Evaluation

The workflow evaluates the CPU reference cases before accepting the migrated GPU results.

Golden 01 uses 18 verification combinations across:

```text
3 seeds
3 shapes
2 data types
```

## 7. Inspect HIPIFY Changes

Open the **Changes** tab.

The demonstration shows a deterministic source transformation affecting:

```text
csrc/elementwise.cu
```

One visible generated change includes:

```cpp
#include "hip/hip_runtime.h"
```

The application identifies the transformation as deterministic HIPIFY output.

No LLM repair was requested during the successful run.

## 8. Observe Real HIP Compilation

The runner invokes the real ROCm compiler.

The demonstrated build targets:

```text
gfx942
```

The compiler command includes:

```text
--offload-arch=gfx942
```

The compilation must complete successfully before GPU verification can proceed.

## 9. Observe GPU Verification

The translated extension executes on the configured AMD GPU.

Golden 01 compares its output against the PyTorch CPU reference.

The successful result includes:

```text
Verification: VERIFIED

Numerical tests:
18 / 18 PASS

CPU reference:
PASS

Determinism:
PASS
```

The application also reports numerical error metrics and checks for invalid values.

## 10. Inspect Benchmark Results

The pipeline collects benchmark evidence from the real execution environment.

Results depend on:

- GPU model.
- ROCm and PyTorch versions.
- Input shape.
- Data type.
- Warmup count.
- Iteration count.
- Synchronization.
- System load.

Do not compare a measured GPU kernel latency with an unrelated CPU or NVIDIA measurement.

ROCmigrator does not claim a verified H100 speedup.

## 11. Review the Approval Gate

After successful verification and reporting, the workflow pauses at:

```text
USER_APPROVAL
```

The interface displays the verification evidence.

Review:

- Generated source changes.
- Numerical correctness results.
- Determinism status.
- Hardware information.
- Benchmark data.
- Final report.

## 12. Approve Pull Request Creation

Click:

**Approve & Open Pull Request**

Only approve a migration after reviewing the results.

In the demonstrated run, explicit approval was followed by:

```text
PR_CREATED
```

The application reported completion of all 12 stages.

## 13. Inspect the Created Pull Request

The successful demonstration created:

[GitHub Pull Request #1](https://github.com/hsynylmz-umhg/rocmigrator-amd-agent/pull/1)

The PR contains the migration changes and verification-related evidence.

The pull request remains subject to normal code review.

A created PR is not equivalent to a merged PR.

---

# Numerical Verification

Correctness verification is one of ROCmigrator's central features.

## Why Compilation Is Not Enough

A HIP extension can compile successfully while still producing incorrect output.

Potential issues include:

- Numerical precision differences.
- Incorrect indexing.
- Thread or block mapping errors.
- Synchronization problems.
- Unsupported assumptions about CUDA behavior.
- Invalid values.
- Nondeterministic execution.

ROCmigrator therefore separates compilation success from verification success.

## CPU Reference Comparison

The demonstrated workflow compares GPU outputs with a PyTorch CPU reference.

Verification evidence includes numerical difference metrics and the final pass/fail outcome.

For Golden 01:

```text
18 required comparisons
18 passed
0 failed
```

## Multiple Random Seeds

The successful test used:

```python
SEEDS = [42, 1337, 2026]
```

Using multiple seeds helps detect input-dependent correctness problems.

## Multiple Shapes

The test covered:

```python
SHAPES = [
    (128, 64),
    (32, 128, 256),
    (1024,),
]
```

This includes two-dimensional, three-dimensional, and one-dimensional inputs.

## Multiple Data Types

The test covered:

```python
DTYPES = [
    torch.float32,
    torch.float64,
]
```

Different data types can expose different numerical behavior.

## Determinism

The Golden 01 verification reported:

```text
Determinism: True
```

This means the configured determinism checks passed for the tested workload.

It does not establish determinism for every possible input or CUDA extension.

## Invalid Value Checks

The verification process also checks for invalid numerical output, including NaN and infinity.

The demonstrated report showed no detected NaN/Inf values.

## Verification Boundary

A job must not be presented as numerically verified solely because:

- HIPIFY completed.
- Compilation returned exit code zero.
- A container launched successfully.
- A GPU was detected.

Numerical verification requires the configured reference comparisons to pass.

---

# Compilation and Repair

ROCmigrator uses deterministic transformation as the first migration strategy.

## Deterministic HIPIFY

CUDA-to-HIP conversion begins with HIPIFY tooling.

This makes the initial transformation reproducible and easier to inspect.

The generated changes are exposed through the application interface.

## Real HIP Compilation

The transformed extension is compiled using the ROCm toolchain.

For the demonstrated MI300X environment:

```text
hipcc
```

was used with:

```text
--offload-arch=gfx942
```

## Bounded AI-Assisted Repair

When compilation fails, ROCmigrator includes a bounded repair mechanism designed to propose constrained changes.

The repair workflow is not an unrestricted autonomous coding agent.

It operates within the application's configured policies and repair budget.

## Repair Budget

A migration job can define a maximum repair budget.

The recorded demonstration used:

```text
Maximum repair rounds: 3
```

The successful Golden 01 execution reported:

```text
Repair rounds: 0
```

Therefore, the demonstration verifies successful compilation without repair.

It does not establish a measured AI repair success rate.

## Why This Distinction Matters

A successful deterministic migration and a successful AI-repaired migration are different outcomes.

Both can be useful, but they should be evaluated separately.

ROCmigrator reports the number of repair rounds so users can understand which path was taken.

---

# Benchmarking

ROCmigrator includes a benchmarking stage after verification.

The objective is to collect performance evidence from the compiled extension running in the selected environment.

## Measurement Considerations

GPU benchmarks require careful measurement practices.

Important variables include:

- Device synchronization.
- Warmup iterations.
- Measurement iterations.
- Kernel launch overhead.
- Tensor shape.
- Data type.
- Compiler configuration.
- GPU architecture.
- Runtime version.
- Container configuration.

A benchmark number without this context can be misleading.

## Demonstrated Hardware

The Golden 01 benchmark ran on:

```text
AMD Instinct MI300X VF
gfx942
```

## Performance Claims

This repository does not claim a measured speedup over NVIDIA H100.

It also does not claim that all migrated workloads run faster on AMD GPUs.

The primary demonstrated success is:

**A CUDA extension was transformed, compiled, executed, numerically verified, benchmarked, and submitted for review through a real AMD GPU workflow.**

---

# Human Approval and GitHub Integration

ROCmigrator deliberately separates automated engineering execution from final repository delivery.

## Approval Gate

The pipeline pauses after verification and reporting.

The user can inspect the migration before authorizing GitHub operations.

This is important because successful tests do not eliminate the need for code review.

## Explicit Approval

Pull request creation requires an affirmative user action.

In the demonstration, the user selected:

```text
Approve & Open Pull Request
```

The workflow then proceeded to GitHub PR creation.

## GitHub Pull Request

The demonstrated pull request is:

[Port verified extension to ROCm/HIP — PR #1](https://github.com/hsynylmz-umhg/rocmigrator-amd-agent/pull/1)

The PR is evidence that the workflow reached the delivery stage.

It does not mean the changes were automatically merged.

## GitHub Authentication

If using the GitHub integration in your own environment:

- Create an appropriately scoped token.
- Use only the permissions required by the integration.
- Store the token outside source control.
- Do not place credentials inside migration repositories.
- Do not expose tokens to the frontend.
- Review generated changes before approval.

---

# Security and Isolation

Migrating third-party extension repositories involves processing source code and potentially executing build operations.

ROCmigrator therefore treats repository input and generated patches as security-sensitive.

## Controlled Repository Processing

The workflow performs repository acquisition, security checks, and source analysis before accepting a migration.

## Isolated Execution

Real compilation and verification execute through a Docker-based runner.

Container isolation helps separate the migration workload from the application control plane.

However, Docker isolation is not a complete security boundary against every possible malicious workload.

Users should deploy the runner on appropriately isolated infrastructure.

## GPU Device Access

The runner receives access to the AMD GPU devices required for execution.

GPU access should be limited to the necessary device nodes and permissions.

## Credential Separation

Sensitive credentials must remain outside untrusted migration workloads.

Examples include:

- GitHub access tokens.
- OpenAI API keys.
- SSH private keys.
- Cloud provider credentials.

Do not mount these credentials into build containers.

## Command Execution

The implementation is designed around controlled subprocess execution rather than arbitrary shell commands generated by an LLM.

Security-sensitive operations should use validated argument lists and explicit policies.

## Patch Review

Generated source changes should remain inspectable.

The user approval gate provides an additional control before publishing changes through GitHub.

## Important Security Limitation

ROCmigrator is a hackathon MVP.

It should not be treated as a fully audited sandbox for arbitrary malicious repositories.

For untrusted code, use dedicated infrastructure with appropriate resource limits, network restrictions, and monitoring.

---

# Running Tests

Testing is divided into two categories.

## Local Tests

Some application components can be tested without an AMD GPU.

These may include:

- Contract validation.
- State-machine behavior.
- API behavior.
- Frontend functionality.
- Pure-Python transformation logic.
- Security policy checks.

The exact commands depend on the test files and dependencies present in the checked-out version.

Inspect the repository's test configuration before running the available local test suite.

For example, if the backend tests use pytest:

```bash
python -m pytest
```

Run this command from the directory expected by the repository's test configuration.

## AMD GPU Integration Tests

Real migration verification requires a compatible AMD GPU.

GPU-dependent operations include:

- Real HIP compilation.
- Loading or executing the translated extension.
- GPU numerical verification.
- GPU benchmarking.

A development machine without compatible AMD hardware cannot reproduce these results locally.

## Recommended Test Sequence

For a new environment:

1. Confirm Python dependencies install correctly.
2. Confirm the frontend builds or starts.
3. Verify backend health and API connectivity.
4. Confirm ROCm detects the intended GPU.
5. Confirm the runner image exists.
6. Confirm GPU device permissions.
7. Run the Golden 01 migration.
8. Inspect the generated changes.
9. Confirm numerical verification results.
10. Review benchmark evidence.
11. Test GitHub PR creation only when explicitly intended.

Avoid repeatedly creating pull requests during routine local testing.

---

# Repository Structure

The project is organized around the application, orchestration, contracts, runner, and test fixtures.

```text
rocmigrator-amd-agent/
|
|-- backend/
|   |-- FastAPI application
|   |-- API endpoints
|   |-- Backend configuration
|   `-- Backend dependencies
|
|-- frontend/
|   |-- Next.js application
|   |-- TypeScript components
|   |-- Migration dashboard
|   |-- Live execution views
|   `-- Verification and approval interface
|
|-- agent_orchestrator/
|   |-- Migration state machine
|   |-- Pipeline coordination
|   `-- Repair orchestration
|
|-- contracts/
|   `-- Pydantic data contracts
|
|-- runner/
|   |-- Isolated execution components
|   |-- HIP compilation
|   |-- GPU verification
|   `-- Benchmark execution
|
|-- fixtures/
|   `-- golden-repo-01/
|       `-- Golden 01 CUDA extension fixture
|
|-- README.md
|
`-- Additional project configuration and documentation
```

This is a conceptual directory overview. The exact files and nested paths should be checked against the current repository.

---

# Troubleshooting

## ROCm Cannot Detect the GPU

Check:

```bash
rocminfo
```

Verify that the expected GPU architecture is visible.

Inspect:

```bash
ls -l /dev/kfd /dev/dri/
```

Confirm that the AMD driver and ROCm stack are correctly installed.

## Wrong Render Device

A system may expose multiple render nodes.

For example:

```text
/dev/dri/renderD128
/dev/dri/renderD129
```

The correct node depends on the host.

The original MI300X environment used:

```text
/dev/dri/renderD129
```

Do not assume this is correct for other systems.

## Docker GPU Permission Errors

Check device ownership:

```bash
stat -c '%n %a %U %G %g' /dev/kfd /dev/dri/renderD*
```

Ensure the runner receives the appropriate devices and numeric group permissions.

The original deployment required numeric group ID configuration.

## HIP Compilation Fails

Verify:

- The ROCm toolchain is installed.
- `hipcc` is available in the runner.
- The GPU architecture target is correct.
- Required ROCm headers are installed.
- PyTorch and ROCm versions are compatible.
- The extension's build configuration is supported.

Successful HIPIFY conversion does not guarantee successful compilation.

## Frontend Cannot Reach the Backend

Check whether the backend is running and listening on the configured port.

If using a remote server, verify that the SSH tunnel is active.

For example:

```bash
ssh -N -L 8000:127.0.0.1:8000 USER@AMD_GPU_HOST
```

Also verify the frontend's API base URL configuration.

## Numerical Verification Fails

Inspect:

- The failing seed.
- Tensor shape.
- Data type.
- CPU reference result.
- GPU output.
- Numerical tolerance.
- NaN/Inf checks.
- Determinism result.

Do not modify tests or tolerances merely to make a failing migration appear successful.

## Pull Request Is Not Created

Check:

- Whether verification completed successfully.
- Whether the workflow reached `USER_APPROVAL`.
- Whether explicit approval was granted.
- Whether GitHub authentication is configured.
- Whether the token has appropriate repository permissions.
- Whether the target branch and repository are accessible.

A successful GPU verification does not automatically authorize GitHub publication.

## Repair Loop Does Not Run

Repair is only relevant when the workflow encounters a supported failure requiring repair.

For Golden 01, the successful run required:

```text
0 repair rounds
```

This is expected behavior.

---

# Limitations

ROCmigrator is a focused hackathon MVP rather than a universal CUDA migration platform.

## Supported Demonstration Scope

The verified demonstration covers a small PyTorch CUDA extension fixture.

The workflow successfully performs:

- CUDA source analysis.
- Deterministic HIPIFY conversion.
- Real HIP compilation.
- AMD GPU execution.
- CPU reference comparison.
- Numerical verification.
- Determinism checks.
- Benchmark collection.
- Human-approved GitHub PR creation.

## Not Demonstrated

The Golden 01 result does not establish support for every CUDA feature or repository architecture.

In particular, it does not prove successful migration of:

- Arbitrary CUDA C++ projects.
- Large multi-module CUDA applications.
- CUTLASS-based workloads.
- NCCL-dependent distributed systems.
- CUDA Graphs.
- Inline PTX.
- TensorRT integrations.
- Complex CMake or Bazel projects.
- Multi-GPU distributed training.
- Arbitrary custom CUDA build systems.

## AI Repair Limitations

The architecture includes bounded AI-assisted repair.

However:

```text
Golden 01 repair rounds: 0
```

The successful demonstration therefore does not constitute evidence of an AI repair success rate.

## Hardware Limitations

The verified environment was:

```text
AMD Instinct MI300X VF
gfx942
```

Other AMD GPUs may require additional validation or environment adjustments.

## Performance Limitations

No verified H100 speedup claim is made.

Performance results should be reproduced on the relevant hardware before drawing comparative conclusions.

## Security Limitations

The project has not been presented as a fully audited execution sandbox.

Do not execute arbitrary untrusted repositories on sensitive infrastructure without additional protections.

---

# Reproducibility and Evidence

ROCmigrator's primary hackathon claim is supported by three types of evidence.

## 1. Real Application Demonstration

The video shows the workflow progressing through actual application states.

[Watch the demonstration](https://youtu.be/9kzPMyuCNyk)

## 2. Real AMD GPU Verification

The demonstrated run used:

```text
AMD Instinct MI300X VF
gfx942
```

The final verification result was:

```text
18/18 tests passed
CPU reference verified
Determinism passed
```

## 3. Real GitHub Pull Request

The workflow created:

[Pull Request #1](https://github.com/hsynylmz-umhg/rocmigrator-amd-agent/pull/1)

The PR was created after successful verification and explicit user approval.

## Evidence Summary

```text
Project:
ROCmigrator

Workload:
Golden 01 PyTorch CUDA extension

Hardware:
AMD Instinct MI300X VF

Architecture:
gfx942

Transformation:
Deterministic HIPIFY

Compilation:
Real ROCm HIP compiler

Execution:
Real AMD GPU

Numerical Verification:
18/18 PASS

CPU Reference:
VERIFIED

Determinism:
PASS

AI Repair Rounds:
0

Human Approval:
GRANTED

Pipeline:
PR_CREATED

GitHub Pull Request:
#1
```

The evidence demonstrates a successful end-to-end migration of the supported Golden 01 fixture.

It should not be interpreted as a universal guarantee for unrelated CUDA repositories.

---

# Hackathon

## AMD Developer Hackathon — ACT III

ROCmigrator was developed as an individual hackathon project focused on practical CUDA-to-ROCm migration.

The central challenge was to move beyond automated source translation and demonstrate a complete engineering workflow on real AMD GPU hardware.

The project combines:

- Deterministic source conversion.
- Explicit workflow orchestration.
- Real ROCm compilation.
- Real AMD GPU execution.
- Numerical correctness verification.
- Controlled AI-assisted repair capability.
- Human approval.
- GitHub delivery.

### Demonstrated Outcome

**A PyTorch CUDA extension was migrated to HIP, compiled and executed on an AMD Instinct MI300X, verified against its CPU reference across 18 numerical test cases, and delivered through a human-approved GitHub pull request.**

### Project Links

**Demo Video**

https://youtu.be/9kzPMyuCNyk

**Source Code**

https://github.com/hsynylmz-umhg/rocmigrator-amd-agent

**Verified Pull Request**

https://github.com/hsynylmz-umhg/rocmigrator-amd-agent/pull/1

---

## Final Note

ROCmigrator approaches CUDA-to-ROCm migration as an engineering verification problem rather than a source translation problem.

HIPIFY produces the initial port.

The ROCm compiler determines whether it builds.

The AMD GPU determines whether it executes.

Numerical verification determines whether its output is correct.

The engineer determines whether the changes should be submitted.

**ROCmigrator connects these steps into one auditable workflow.**

---

**Built for AMD Developer Hackathon — ACT III.**

**ROCmigrator — From CUDA to ROCm. Compiled. Verified. Reviewable.**
