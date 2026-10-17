"""Real, bounded Golden 01 migration using the isolated AMD Docker runner.

Repository code is only executed by RunnerClient. The backend reads source,
performs fixed Git operations in a private export, and proposes bounded patches.
"""

import asyncio
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

from agent_orchestrator import engine
from agent_orchestrator.fingerprints.db import FingerprintDB
from agent_orchestrator.rollback import RollbackManager
from contracts.api_schemas import AnalysisLogData, BenchmarkLogData, JobCreateRequest, JobStatusResponse, LogEvent
from contracts.patch_schemas import PatchProposal
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import VerificationReport

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_EXPORT_BYTES = 32 * 1024 * 1024
MAX_EXPORT_ENTRIES = 2048
_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_contexts: dict[str, "RealJobContext"] = {}


@dataclass
class RealJobContext:
    job_id: str
    workdir: Path
    source_path: Path
    request: JobCreateRequest
    git_dir: Path
    baseline_commit: str = ""
    source_git_root: Path | None = None
    source_subdir: str = ""
    source_commit: str | None = None
    source_remote: str | None = None
    source_branch: str | None = None
    changed_files: tuple[str, ...] = ()
    verified: bool = False
    verification_sha256: dict[str, str] = field(default_factory=dict)
    verification_report: VerificationReport | None = None
    input_files: tuple[str, ...] = ()
    rollback: RollbackManager | None = None


def get_job_context(job_id: str) -> RealJobContext | None:
    return _contexts.get(job_id)


def _process(arguments: list[str], *, cwd: Path | None = None, data: bytes | None = None) -> subprocess.CompletedProcess:
    # Neither source files nor request strings are ever evaluated as shell code.
    environment = {name: value for name, value in os.environ.items()
                   if name.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": os.devnull,
                        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"})
    return subprocess.run(arguments, cwd=cwd, input=data, capture_output=True,
                          shell=False, timeout=60, check=False, env=environment)


def _git(context: RealJobContext, *arguments: str, data: bytes | None = None) -> str:
    result = _process([
        "git", f"--git-dir={context.git_dir}", f"--work-tree={context.workdir}",
        "-c", "core.bare=false", "-c", "core.autocrlf=false", "-c", "core.hooksPath=/dev/null",
        *arguments,
    ], cwd=context.workdir, data=data)
    if result.returncode:
        raise RuntimeError("Private export Git operation failed: " + result.stderr.decode("utf-8", "replace")[:1500])
    return result.stdout.decode("utf-8", "strict").strip()


def _read_source(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_EXPORT_BYTES:
        raise ValueError("Expected a bounded, ordinary source file.")
    return path.read_text(encoding="utf-8")


def _source_metadata(context: RealJobContext) -> None:
    result = _process(["git", "-C", str(context.source_path), "rev-parse", "--show-toplevel"])
    if result.returncode:
        return
    root = Path(result.stdout.decode().strip()).resolve()
    context.source_git_root = root
    context.source_subdir = context.source_path.relative_to(root).as_posix()
    if context.source_subdir == ".":
        context.source_subdir = ""
    for field_name, args in (
        ("source_commit", ["rev-parse", "HEAD"]),
        ("source_remote", ["remote", "get-url", "origin"]),
        ("source_branch", ["branch", "--show-current"]),
    ):
        value = _process(["git", "-C", str(root), *args])
        if value.returncode == 0:
            setattr(context, field_name, value.stdout.decode().strip() or None)


def prepare_export(job_id: str, request: JobCreateRequest) -> RealJobContext:
    """Copy bounded files, never execute repository code or mount Git metadata."""
    if not _JOB_ID.fullmatch(job_id):
        raise ValueError("Malformed job identifier.")
    allowed_root = Path(os.environ.get("ROCMIGRATOR_REPOSITORY_ROOT", str(PROJECT_ROOT / "fixtures"))).resolve()
    selected = Path(request.repo_path)
    source = (selected if selected.is_absolute() else PROJECT_ROOT / selected).resolve()
    if not source.is_dir() or not source.is_relative_to(allowed_root):
        raise ValueError("Selected repository is outside ROCMIGRATOR_REPOSITORY_ROOT or is missing.")
    jobs_root = Path(os.environ.get("ROCMIGRATOR_JOBS_ROOT", str(PROJECT_ROOT / "build" / "jobs"))).resolve()
    if jobs_root.is_relative_to(source) or source.is_relative_to(jobs_root):
        raise ValueError("Source and private jobs directories must not overlap.")
    job_root = jobs_root / job_id
    job_root.mkdir(parents=True, exist_ok=False)
    workdir = job_root / "input"
    workdir.mkdir()
    context = RealJobContext(job_id, workdir, source, request, job_root / "git")
    # Register immediately so partial preparation can be accounted for on failure.
    _contexts[job_id] = context
    files: list[str] = []
    total = entries = 0
    excluded = {".git", "__pycache__", ".pytest_cache", ".venv", "build", "dist", "node_modules"}
    forbidden = {".ssh", ".aws", ".azure", ".config", ".docker", ".codex", ".agents"}
    for directory, directories, names in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name not in excluded]
        for name in directories + names:
            if name in excluded:
                continue
            path = Path(directory) / name
            relative = path.relative_to(source)
            info = path.lstat()
            entries += 1
            if name in forbidden or name.startswith(".env") or path.suffix.lower() in {".pem", ".key", ".so", ".dll", ".pyd", ".a", ".o"}:
                raise ValueError("Repository contains credential/configuration paths or prebuilt binaries.")
            if not (stat.S_ISDIR(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1)):
                raise ValueError("Repository export rejects symlinks, hardlinks, and special files.")
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
                if entries > MAX_EXPORT_ENTRIES or total > MAX_EXPORT_BYTES:
                    raise ValueError("Repository export exceeds its size or entry budget.")
                target = workdir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
                files.append(relative.as_posix())
            if entries > MAX_EXPORT_ENTRIES:
                raise ValueError("Repository export exceeds its entry budget.")
    context.input_files = tuple(sorted(files))
    _source_metadata(context)
    result = _process(["git", "init", "--bare", str(context.git_dir)])
    if result.returncode:
        raise RuntimeError("Could not initialize the isolated source checkpoint.")
    _git(context, "add", "--", ".")
    _git(context, "-c", "user.name=ROCmigrator", "-c", "user.email=rocmigrator@localhost",
         "commit", "--no-gpg-sign", "-m", "Record isolated source baseline")
    context.baseline_commit = _git(context, "rev-parse", "HEAD")
    context.rollback = RollbackManager(str(workdir))
    context.rollback.record_commit(context.baseline_commit)
    return context


def analyze(context: RealJobContext) -> AnalysisLogData:
    cu_files = tuple(path for path in context.input_files if Path(path).suffix in {".cu", ".cuh"})
    if not 1 <= len(cu_files) <= 5:
        raise ValueError("The supported scope requires 1-5 CUDA source/header files.")
    total = 0
    prohibited = re.compile(r"cutlass|nccl|cudaGraph|\b(?:asm|__asm__)\s*\(|wmma::|nvrtc|nvinfer|cudaLaunchDevice|cudaSetDevice", re.I)
    for relative in cu_files:
        if not engine._safe_source_path(relative):
            raise ValueError("CUDA source path is not canonical.")
        text = _read_source(context.workdir / relative)
        lines = text.splitlines()
        total += len(lines)
        # The conservative file bound also guarantees the per-kernel bound.
        if len(lines) > 300 or prohibited.search(text):
            raise ValueError("Source exceeds the supported kernel scope or uses prohibited GPU features.")
    setup = _read_source(context.workdir / "setup.py")
    if "CUDAExtension" not in setup or any(Path(name).name in {"CMakeLists.txt", "BUILD", "BUILD.bazel"} for name in context.input_files):
        raise ValueError("Only simple setup.py CUDAExtension repositories are supported.")
    # The initial trusted harness implements Golden 01 semantics, not arbitrary code.
    for protected in ("setup.py", "reference.py", "test_kernel.py", "csrc/elementwise.h"):
        if _read_source(context.workdir / protected) != _read_source(PROJECT_ROOT / "fixtures" / "golden-repo-01" / protected):
            raise ValueError("This runner requires the reviewed Golden 01 build, reference, tests, and public API.")
    return AnalysisLogData(cu_files=cu_files, total_loc=total, setup_path="setup.py")


def security_scan(context: RealJobContext) -> str:
    result = _process(["bash", str(PROJECT_ROOT / "scripts" / "security_scan.sh"), str(context.workdir)])
    if result.returncode:
        raise RuntimeError("Security scan rejected the isolated source export.")
    return result.stdout.decode("utf-8", "replace").strip()


async def _event(job_id: str, state: PipelineState, message: str, *, data=None, error: bool = False) -> None:
    await engine._publish(LogEvent(job_id=job_id, state=state, message=message,
                                  level="ERROR" if error else "INFO", data=data))


async def _runner_step(client, context: RealJobContext, operation: str, state: PipelineState, source: str | None = None):
    result = await client.run(context.job_id, operation, context.workdir, source=source)
    evidence = context.workdir.parent / "evidence"
    evidence.mkdir(exist_ok=True)
    sequence = len(tuple(evidence.glob(f"{operation}-*.json"))) + 1
    (evidence / f"{operation}-{sequence}.json").write_text(json.dumps({
        "job_id": context.job_id, "operation": operation, "source": source,
        "returncode": result.returncode, "duration_seconds": result.duration_seconds,
        "stdout": result.stdout, "stderr": result.stderr,
    }, indent=2), encoding="utf-8")
    if result.event is not None:
        await engine._accept_step(result.event, context.job_id, state)
    await _event(context.job_id, state,
                 f"Isolated {operation} exited {result.returncode}; elapsed {result.duration_seconds:.3f} seconds.")
    return result


def _repair_path(context: RealJobContext, analysis: AnalysisLogData, diagnostics: str) -> str:
    referenced = [path for path in analysis.cu_files if path in diagnostics or Path(path).name in diagnostics]
    if len(referenced) == 1:
        return referenced[0]
    if len(analysis.cu_files) == 1:
        return analysis.cu_files[0]
    raise ValueError("Compiler diagnostic does not identify one unambiguous allowlisted source.")


def _known_transform(source: str, fingerprint: str) -> str:
    if fingerprint == "FP_CUDA_HEADER":
        return source.replace("#include <cuda_runtime.h>", "#include <hip/hip_runtime.h>").replace("#include <cuda.h>", "#include <hip/hip_runtime.h>")
    if fingerprint == "FP_CUDA_ERR_STRING":
        for old, new in (("cudaError_t", "hipError_t"), ("cudaGetLastError", "hipGetLastError"), ("cudaGetErrorString", "hipGetErrorString"), ("cudaSuccess", "hipSuccess")):
            source = re.sub(rf"\b{old}\b", new, source)
        return source
    if fingerprint == "FP_WARP_SIZE":
        return re.sub(r"(const\s+int\s+threads\s*=\s*)32(\s*;)", r"\1warpSize\2", source)
    raise ValueError("No reviewed deterministic policy exists for this fingerprint.")


def validate_patch(context: RealJobContext, raw: str, fingerprint: str,
                   analysis: AnalysisLogData, used_lines: int) -> PatchProposal:
    # Required order: strict schema, exact allowlist, applicability, budget, policy.
    proposal = PatchProposal.model_validate_json(raw)
    if (not proposal.allowlisted or proposal.file_path not in analysis.cu_files
            or not engine._safe_source_path(proposal.file_path) or proposal.fingerprint_id != fingerprint):
        raise ValueError("Patch allowlist or fingerprint does not match the observed source error.")
    if len(proposal.diff) > engine.LLM_MAX_RESPONSE_CHARS:
        raise ValueError("Patch exceeds the response budget.")
    lines = proposal.diff.splitlines()
    if lines[:2] != [f"--- a/{proposal.file_path}", f"+++ b/{proposal.file_path}"] or any(
        line.startswith(("diff ", "index ", "--- ", "+++ ", "GIT binary")) for line in lines[2:]
    ):
        raise ValueError("Patch must contain one exact source path and plain unified hunks.")
    _git(context, "apply", "--check", "--whitespace=error-all", "-", data=proposal.diff.encode())
    added = sum(line.startswith("+") for line in lines[2:])
    deleted = sum(line.startswith("-") for line in lines[2:])
    if (added, deleted) != (proposal.lines_added, proposal.lines_deleted):
        raise ValueError("Patch declarations do not match actual diff line counts.")
    if not 0 < added + deleted <= 120 or used_lines + added + deleted > min(300, analysis.total_loc * 15 // 100):
        raise ValueError("Patch exceeds its single or cumulative CUDA line budget.")
    original = _read_source(context.workdir / proposal.file_path)
    expected = _known_transform(original, fingerprint)
    expected_diff = "".join(unified_diff(original.splitlines(keepends=True), expected.splitlines(keepends=True),
                                       fromfile=f"a/{proposal.file_path}", tofile=f"b/{proposal.file_path}"))
    if not expected_diff or proposal.diff != expected_diff:
        raise ValueError("Patch policy only accepts the exact reviewed compiler repair and preserves kernel/API behavior.")
    return proposal


async def _repair(context: RealJobContext, analysis: AnalysisLogData, diagnostic: str,
                  fingerprint: str, used_lines: int) -> PatchProposal:
    relative = _repair_path(context, analysis, diagnostic)
    original = _read_source(context.workdir / relative)
    if fingerprint == "FP_WARP_SIZE":
        source_lines = original.splitlines(keepends=True)
        match = re.search(re.escape(Path(relative).name) + r":(\d+)", diagnostic)
        center = int(match.group(1)) - 1 if match else 0
        start = max(0, min(center - 60, len(source_lines) - 150))
        window = tuple(source_lines[start:start + 150])
        error = LogEvent(job_id=context.job_id, state=PipelineState.COMPILING, level="ERROR", message=diagnostic)
        raw = await engine._propose_patch(error, fingerprint, window, file_path=relative, source_start_line=start + 1)
    else:
        expected = _known_transform(original, fingerprint)
        diff = "".join(unified_diff(original.splitlines(keepends=True), expected.splitlines(keepends=True),
                                    fromfile=f"a/{relative}", tofile=f"b/{relative}"))
        raw = PatchProposal(patch_id=f"{context.job_id}-deterministic-repair", file_path=relative,
                            diff=diff, fingerprint_id=fingerprint,
                            lines_added=sum(line.startswith("+") for line in diff.splitlines()[2:]),
                            lines_deleted=sum(line.startswith("-") for line in diff.splitlines()[2:]),
                            explanation="Deterministic HIP API repair for the observed compiler diagnostic.").model_dump_json()
    proposal = await asyncio.to_thread(validate_patch, context, raw, fingerprint, analysis, used_lines)
    await asyncio.to_thread(_git, context, "apply", "--whitespace=error-all", "-", data=proposal.diff.encode())
    await _event(context.job_id, PipelineState.REPAIR, "Validated patch applied to isolated source export.", data=proposal)
    return proposal


async def rollback_job(job_id: str, reason: str) -> JobStatusResponse:
    current = engine._job_statuses[job_id]
    if current.current_state == PipelineState.ROLLED_BACK:
        return current
    context = _contexts.get(job_id)
    await _event(job_id, current.current_state, reason, error=True)
    if context is not None:
        context.verified = False
        if context.baseline_commit:
            restored = await asyncio.to_thread(context.rollback.restore_isolated_files, str(context.git_dir), context.input_files)
            if not restored:
                await _event(job_id, current.current_state, "Rollback restoration failed; operator action is required.", error=True)
                raise RuntimeError("Isolated rollback could not be confirmed.")
            context.changed_files = ()
            await _event(job_id, current.current_state, "Isolated source files restored to their recorded baseline commit.")
    report = current.verification_report or VerificationReport(
        job_id=job_id, overall_status="ROLLED_BACK", cpu_reference_verified=False,
        determinism_passed=False, summary=f"{reason} No successful GPU verification was recorded.")
    return await engine._transition(current, PipelineState.ROLLED_BACK, report=report)


async def run_real_pipeline(job_id: str, request: JobCreateRequest) -> JobStatusResponse:
    request = JobCreateRequest.model_validate(request)
    if not _JOB_ID.fullmatch(job_id) or job_id in engine._job_statuses:
        raise ValueError("Malformed or already registered job identifier.")
    current = JobStatusResponse(job_id=job_id, current_state=PipelineState.CREATED)
    engine._job_statuses[job_id] = current
    context = None
    try:
        await _event(job_id, PipelineState.CREATED, "Real AMD runner pipeline created; no simulation fallback is enabled.")
        from agent_orchestrator.runner_client import RunnerClient
        client = RunnerClient.from_environment()
        current = await engine._transition(current, PipelineState.CLONING)
        context = await asyncio.to_thread(prepare_export, job_id, request)
        current = JobStatusResponse(**{**current.model_dump(), "best_known_commit": context.baseline_commit})
        engine._job_statuses[job_id] = current
        await _event(job_id, current.current_state, f"Copied {len(context.input_files)} source files into a bounded isolated export; original repository unchanged.")
        current = await engine._transition(current, PipelineState.SECURITY_SCAN)
        await _event(job_id, current.current_state, await asyncio.to_thread(security_scan, context))
        current = await engine._transition(current, PipelineState.ANALYSIS)
        analysis = await asyncio.to_thread(analyze, context)
        await _event(job_id, current.current_state, f"Analyzed {len(analysis.cu_files)} CUDA sources and {analysis.total_loc} CUDA lines.", data=analysis)
        current = await engine._transition(current, PipelineState.BASELINE)
        result = await _runner_step(client, context, "baseline", current.current_state)
        if result.returncode:
            raise RuntimeError("Trusted CPU baseline did not execute successfully.")
        current = await engine._transition(current, PipelineState.HIPIFICATION)
        hipify_lines = 0
        for relative in analysis.cu_files:
            original = _read_source(context.workdir / relative)
            result = await _runner_step(client, context, "hipify", current.current_state, relative)
            if result.returncode or result.event is None or result.event.level != "INFO":
                raise RuntimeError("Real HIPIFY failed.")
            converted = result.event.message
            if not converted.strip() or len(converted.encode()) > MAX_EXPORT_BYTES:
                raise ValueError("HIPIFY returned invalid source content.")
            diff = "".join(unified_diff(original.splitlines(keepends=True), converted.splitlines(keepends=True),
                                       fromfile=f"a/{relative}", tofile=f"b/{relative}"))
            if diff:
                added = sum(line.startswith("+") for line in diff.splitlines()[2:])
                deleted = sum(line.startswith("-") for line in diff.splitlines()[2:])
                hipify_lines += added + deleted
                if hipify_lines > min(300, analysis.total_loc * 15 // 100):
                    raise ValueError("HIPIFY exceeds the cumulative source-change budget.")
                proposal = PatchProposal(patch_id=f"{job_id}-hipify-{len(context.changed_files)}",
                    file_path=relative, diff=diff, fingerprint_id=None, lines_added=added, lines_deleted=deleted,
                    explanation="Actual deterministic hipify-perl output; no LLM repair was requested.")
                await asyncio.to_thread(_git, context, "apply", "--check", "--whitespace=error-all", "-", data=diff.encode())
                await _event(job_id, current.current_state, "HIPIFY source changes captured for review.", data=proposal)
            (context.workdir / relative).write_text(converted, encoding="utf-8", newline="\n")
        current = await engine._transition(current, PipelineState.COMPILING)
        fingerprints = FingerprintDB()
        used_lines, stalls = hipify_lines, 0
        previous_errors = None
        while True:
            result = await _runner_step(client, context, "compile", current.current_state)
            if result.returncode == 0:
                break
            diagnostics = result.event.message if result.event else result.stdout + "\n" + result.stderr
            errors = frozenset(line.strip() for line in diagnostics.splitlines() if "error:" in line.lower())
            if previous_errors is not None:
                stalls = 0 if errors and errors < previous_errors else stalls + 1
            previous_errors = errors
            if stalls >= 2 or current.repair_rounds_used >= request.max_repair_rounds:
                raise RuntimeError("Bounded repair stopped after exhausted rounds or two rounds without progress.")
            matches = fingerprints.classify("\n".join(errors))
            if not matches or any(not fingerprints.record_occurrence(fp.id) for fp in matches):
                raise RuntimeError("Compiler error is unknown or its fingerprint exceeded two repair attempts.")
            fingerprint = matches[0]
            bounded = "\n".join(line for line in diagnostics.splitlines() if re.search(fingerprint.pattern, line, re.I))
            bounded = "\n".join(bounded.splitlines()[:3])
            if not bounded or len(bounded) > 4000:
                raise ValueError("Compiler context cannot be safely bounded.")
            current = await engine._transition(current, PipelineState.REPAIR, repairs=current.repair_rounds_used + 1)
            proposal = await _repair(context, analysis, bounded, fingerprint.id, used_lines)
            used_lines += proposal.lines_added + proposal.lines_deleted
            current = await engine._transition(current, PipelineState.COMPILING)
        current = await engine._transition(current, PipelineState.VERIFYING)
        result = await _runner_step(client, context, "verify", current.current_state)
        if result.report is None:
            raise RuntimeError("Runner did not produce a trusted GPU verification report.")
        report = VerificationReport.model_validate(result.report)
        if report.job_id != job_id:
            raise ValueError("Verification report belongs to another job.")
        if report.overall_status == "VERIFIED" and (
            len({case.seed for case in report.results}) < 2 or len({case.shape for case in report.results}) < 2
            or len({case.dtype for case in report.results}) < 2
        ):
            raise ValueError("Verification coverage is insufficient.")
        current = JobStatusResponse(job_id=job_id, current_state=current.current_state,
                                    repair_rounds_used=current.repair_rounds_used,
                                    best_known_commit=context.baseline_commit, verification_report=report)
        engine._job_statuses[job_id] = current
        await _event(job_id, current.current_state, report.summary, error=report.overall_status != "VERIFIED")
        if result.returncode or report.overall_status != "VERIFIED":
            raise RuntimeError("GPU numerical verification failed; user approval is unavailable.")
        context.verification_report = report
        context.verification_sha256 = {name: hashlib.sha256((context.workdir / name).read_bytes()).hexdigest() for name in context.input_files}
        current = await engine._transition(current, PipelineState.BENCHMARKING)
        result = await _runner_step(client, context, "benchmark", current.current_state)
        if result.returncode or result.event is None or not isinstance(result.event.data, BenchmarkLogData):
            raise RuntimeError("Runner did not provide validated GPU benchmark measurements.")
        context.changed_files = tuple((await asyncio.to_thread(_git, context, "diff", "--name-only", context.baseline_commit, "--")).splitlines())
        context.verified = True
        current = await engine._transition(current, PipelineState.REPORT)
        await _event(job_id, current.current_state, "Actual GPU verification and benchmark evidence retained; reviewed source hashes recorded.")
        current = await engine._transition(current, PipelineState.USER_APPROVAL)
        await _event(job_id, current.current_state, "Awaiting explicit user approval. No GitHub branch or pull request has been created.")
        return current
    except asyncio.CancelledError:
        await rollback_job(job_id, "Real migration was cancelled.")
        raise
    except Exception as exc:
        return await rollback_job(job_id, f"Real migration stopped: {type(exc).__name__}: {exc}")
