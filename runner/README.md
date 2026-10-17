# Isolated AMD runner

This image executes HIPIFY, compilation, and trusted numerical harnesses on a
Linux AMD host. `runner/verification` contains the reviewed Golden 01 CPU
reference, GPU verification, and benchmark adapters. These files implement the
checks; only captured results from an actual AMD run establish GPU execution.

## Image preparation

The requested default image is preserved exactly:
`rocm/pytorch:rocm6.0_ubuntu22.04_py3.10_pytorch_2.1.0`. The registry check during
implementation found that this exact tag was unavailable. Building with the
default will remain blocked until the image is available. An explicitly reviewed
`BASE_IMAGE` build argument can select an available compatible image; there is no
automatic fallback or silent version change.

Build from the repository root with BuildKit:

```sh
docker build --network=none -f runner/Dockerfile.runner -t rocmigrator-runner:local .
```

The trusted provisioning instruction explicitly uses `RUN --network=default` to
install pinned pytest, Ninja, and Pydantic packages. No migration checkout is
copied into or executed by that instruction. All subsequent build instructions
use `RUN --network=none`. Repository compilation happens only at runtime with
networking disabled. A fully disconnected image build requires a previously
provisioned, reviewed local base and dependency artifacts; it cannot download
packages or pull an uncached image offline.

## Host configuration

Use Docker Engine on the AMD Linux host, cgroup v2, and Docker Compose 2.15 or
newer. Keep Docker's default seccomp filter enabled. Configure remote host
authentication outside the container; never mount SSH keys, cloud credentials,
LLM credentials, the Docker socket, or the host home directory.

Set these nonsecret host-side variables before using Compose:

| Variable | Required value |
| --- | --- |
| `JOB_ID` | Exact engine job identifier: 1–128 ASCII letters, digits, underscores, or hyphens; starts with a letter or digit. |
| `RUNNER_IMAGE` | Reviewed local image; defaults to `rocmigrator-runner:latest`. |
| `RUNNER_INPUT_DIR` | Absolute path on the Docker host to a credential-free, immutable repository export. |
| `PYTORCH_ROCM_ARCH` | One reviewed GPU architecture, such as `gfx90a`; match the actual AMD device. |
| `AMD_RENDER_DEVICE` | Exactly one reviewed render node, such as `/dev/dri/renderD128`. |
| `AMD_RENDER_GID` | Numeric group ID owning that render node. |
| `AMD_KFD_GID` | Numeric group ID owning `/dev/kfd`; it may differ from the render group. |
| `TRUSTED_VERIFICATION_DIR` | Absolute Docker-host path to `runner/verification`, containing reviewed `verify.py`, `baseline.py`, and `benchmark.py`; required for those three phases. |

Read actual device group IDs with `stat -c %g` on the selected device paths. Give
UID 1000 read access to the exported input and trusted harness. The input export
must remain unchanged on the host while the container runs; a read-only bind
mount does not prevent another host process from modifying its source. Export
ordinary files without `.git`, credentials, sockets, devices, symlinks, or
hardlinks. The runner stages at most 2,048 filesystem entries (files and
directories) and 32 MiB into a fresh workspace.
Do not bind the original working checkout as a writable mount.

The base Compose file adds the render node's numeric group. When `/dev/kfd`
has a different group, also pass `-f runner/docker-compose.kfd-group.yml` after
the base `-f` argument; its additional group preserves access to both devices.
When both groups are equal, omit that override to avoid duplicate group entries.

Compose applies UID/GID 1000, a read-only root filesystem, no network, a private
cgroup namespace, a four-core CPU limit, 16 GiB memory with no swap, and at most
256 processes. It drops all capabilities, prevents privilege escalation, and
exposes `/dev/kfd` plus only the selected render node. Writable storage is bounded
to an 8 GiB workspace, 1 GiB temporary directory, and 1 GiB shared memory. The
workspace allows executable mappings so compiled extensions can load; `/tmp`
does not. All three are temporary filesystems, with `nosuid` and `nodev`.

The entrypoint checks isolation before executing repository code and refuses
missing or excessive limits. Do not override the entrypoint, enable `init`, use
privileged mode, share host PID/IPC namespaces, disable seccomp, or add mounts.
Dockerfile `USER` and environment settings cannot enforce these runtime limits;
use the supplied Compose configuration.

## Commands and results

Run from the repository root after preparing the image and host variables:

```sh
docker compose -f runner/docker-compose.yml config --quiet
docker compose -f runner/docker-compose.yml --profile verify run --rm -T verification baseline "$JOB_ID"
docker compose -f runner/docker-compose.yml run --rm -T runner hipify "$JOB_ID" csrc/elementwise.cu
docker compose -f runner/docker-compose.yml run --rm -T runner compile "$JOB_ID"
docker compose -f runner/docker-compose.yml --profile verify run --rm -T verification
docker compose -f runner/docker-compose.yml --profile verify run --rm -T verification benchmark "$JOB_ID"
```

Only `hipify JOB_ID relative/file.cu` and `compile`, `verify`, `baseline`, or
`benchmark` followed by `JOB_ID` are accepted. HIPIFY also accepts `.cuh`; paths
must be canonical and relative. The
script never accepts arbitrary commands or extra compiler flags. Each invocation
has one shared 295-second execution budget, reserving five seconds of the
300-second maximum for termination and result emission. The trusted host
controller must also impose a 300-second container deadline and forcibly remove
the container on timeout, cancellation, missing output, or connection loss.
Stopping only the local Docker client does not reliably stop a remote container.

Standard output contains one JSON document. HIPIFY and compilation produce a
strict `LogEvent`; failures use `level="ERROR"` and a nonzero exit status. Compiler
exit codes and bounded stdout/stderr appear as diagnostic text in `message`.
On successful HIPIFY, `message` is the complete translated source, not a compiler
diagnostic. The host must validate the event and stage that source in its next
immutable input export. Source changes and compiled artifacts inside the
temporary workspace disappear when the invocation ends. Verification therefore
rebuilds its own workspace before running the harness.

A completed numerical harness produces a strict `VerificationReport` instead of
a `LogEvent`. `VERIFIED` returns exit status zero; a validated `FAILED` report
returns nonzero. Preflight, build, harness, or report-validation errors return an
ERROR `LogEvent`. The controller must distinguish these two existing contracts,
validate the exact job identifier, and reject malformed, absent, or extra output.
No compilation success or successful HIPIFY result establishes verification.

Baseline returns a `BASELINE` LogEvent after executing all 18 CPU reference
cases. Benchmark rebuilds in its own isolated workspace and returns a
`BENCHMARKING` LogEvent with `BenchmarkLogData`. It measures 100 actual extension
calls after 20 warmups, with GPU synchronization around wall-clock timing, on
shape `[32,128,256]`, float32. Timing includes launch overhead. No CPU speedup is
claimed because CPU timing is not collected.

## Trusted verification harness

Mount an independently reviewed harness at `/verification/verify.py`, read-only.
It is invoked with isolated Python startup and two arguments: the job identifier
and `/workspace/verification_report.json`. It must explicitly import the compiled
extension from `/workspace`, exercise the real AMD GPU, compare it against an
independent CPU reference using the existing tolerances and
`torch.testing.assert_close`, check NaN/Inf and mismatch ratios, and test
determinism. It must write a fresh `VerificationReport` to the supplied output
path. Successful reports require at least two distinct seeds, shapes, and dtypes.
The harness and CPU reference must never come from an LLM patch or a mutable
target repository.

The bundled adapter verifies only Golden 01's `fused_elementwise_cuda.forward`
on gfx942. It directly loads a native extension, never workspace Python modules.
Seeds 42, 1337, and 2026 cover shapes `[128,64]`, `[32,128,256]`, and `[1024]` in
float32 and float64. Existing tolerances remain 1e-5 and 1e-7 respectively;
elementwise mismatch counts and `torch.testing.assert_close` determine success.
Three repeated GPU calls per case must equal the initial output. Nonfinite error
metrics produce FAILED with an explicit explanation because the immutable
contract cannot represent NaN/Inf metrics; they are never replaced with zero.

The runner checks ROCm PyTorch, an available single GPU, report schema, job ID,
case coverage, counts, and recorded evidence. The reviewed harness remains
responsible for establishing that evidence; report validation alone cannot prove
which code executed. The fixture `run_verification` functions are useful inputs
to a reviewed adapter but are not standalone pytest tests. CPU self-checks are
regressions only and must never establish GPU verification.

Docker references: [runtime resource constraints](https://docs.docker.com/engine/containers/resource_constraints/),
[disabled networking](https://docs.docker.com/engine/network/drivers/none/), and
[Compose service settings](https://docs.docker.com/reference/compose-file/services/).
