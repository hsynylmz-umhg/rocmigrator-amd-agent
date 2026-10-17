"""Bounded local Docker transport for the isolated AMD Linux runner.

The API runs on the AMD host. SSH authentication belongs to deployment, never
to a migration container. Compose is the single source of runtime isolation.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pydantic import ValidationError

from contracts.api_schemas import BenchmarkLogData, LogEvent
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import VerificationReport

ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT = 1024 * 1024
OPERATIONS = {
    "hipify": PipelineState.HIPIFICATION,
    "compile": PipelineState.COMPILING,
    "verify": PipelineState.VERIFYING,
    "benchmark": PipelineState.BENCHMARKING,
    "baseline": PipelineState.BASELINE,
}


class RunnerError(RuntimeError):
    """Operational or protocol failure; it must never trigger simulation."""


@dataclass(frozen=True)
class RunnerResult:
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    event: LogEvent | None = None
    report: VerificationReport | None = None


def validate_job_id(job_id: str) -> None:
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", job_id):
        raise RunnerError("Invalid runner job identifier.")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise RunnerError("Runner JSON contains duplicate keys.")
        result[key] = value
    return result


def parse_result(job_id: str, operation: str, code: int, output: str,
                 errors: str, duration: float) -> RunnerResult:
    """Accept exactly one schema-validated document for this invocation."""
    validate_job_id(job_id)
    if operation not in OPERATIONS or len(output.encode("utf-8")) > MAX_OUTPUT:
        raise RunnerError("Invalid operation or oversized runner output.")
    try:
        document = json.loads(output, object_pairs_hook=_unique_object)
        if not isinstance(document, dict):
            raise RunnerError("Runner output must be one JSON object.")
        if "overall_status" in document:
            if operation != "verify":
                raise RunnerError("Unexpected verification report outside verification.")
            report = VerificationReport.model_validate_json(output)
            if report.job_id != job_id or report.overall_status not in {"VERIFIED", "FAILED"}:
                raise RunnerError("Verification report has invalid ownership or status.")
            if (code == 0) != (report.overall_status == "VERIFIED"):
                raise RunnerError("Verification exit code contradicts its report.")
            if report.overall_status == "VERIFIED" and not (
                len({r.seed for r in report.results}) >= 2
                and len({r.shape for r in report.results}) >= 2
                and len({r.dtype for r in report.results}) >= 2
            ):
                raise RunnerError("Verification lacks required numerical coverage.")
            return RunnerResult(code, output, errors, duration, report=report)
        event = LogEvent.model_validate_json(output)
        if event.job_id != job_id or event.state != OPERATIONS[operation]:
            raise RunnerError("Runner event does not match its job and operation.")
        if event.level not in {"INFO", "ERROR"} or (code == 0) != (event.level == "INFO"):
            raise RunnerError("Runner exit code contradicts its event.")
        if operation == "verify" and code == 0:
            raise RunnerError("Verification succeeded without a numerical report.")
        if operation == "benchmark" and code == 0 and not isinstance(event.data, BenchmarkLogData):
            raise RunnerError("Benchmark succeeded without measured benchmark data.")
        return RunnerResult(code, output, errors, duration, event=event)
    except (ValueError, ValidationError, UnicodeError) as error:
        raise RunnerError("Runner returned malformed or schema-invalid JSON.") from error


class RunnerClient:
    def __init__(self, *, docker: str, render_device: str, render_gid: int,
                 kfd_gid: int, architecture: str, image: str,
                 compose_file: Path = ROOT / "runner/docker-compose.yml",
                 harness_dir: Path = ROOT / "runner/verification"):
        if not re.fullmatch(r"/dev/dri/renderD[0-9]+", render_device):
            raise RunnerError("Select exactly one /dev/dri/renderD device.")
        if not re.fullmatch(r"gfx[0-9a-f]{3,4}", architecture):
            raise RunnerError("Configure one reviewed AMD GPU architecture.")
        if any(type(gid) is not int or not 0 <= gid <= 2**32 - 1 for gid in (render_gid, kfd_gid)):
            raise RunnerError("GPU groups must be numeric device group IDs.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}", image):
            raise RunnerError("Invalid runner image identifier.")
        self.docker = docker
        self.compose_file = compose_file.resolve(strict=True)
        self.harness_dir = harness_dir.resolve(strict=True)
        self.settings = {
            "AMD_RENDER_DEVICE": render_device, "AMD_RENDER_GID": str(render_gid),
            "AMD_KFD_GID": str(kfd_gid), "PYTORCH_ROCM_ARCH": architecture,
            "RUNNER_IMAGE": image, "TRUSTED_VERIFICATION_DIR": str(self.harness_dir),
        }

    @classmethod
    def from_environment(cls) -> RunnerClient:
        if sys.platform != "linux":
            raise RunnerError("Real migration requires the backend on the AMD Linux host.")
        docker = shutil.which("docker")
        if not docker:
            raise RunnerError("Docker is unavailable on the AMD backend host.")
        device = os.environ.get("AMD_RENDER_DEVICE", "")
        if not re.fullmatch(r"/dev/dri/renderD[0-9]+", device):
            raise RunnerError("Set AMD_RENDER_DEVICE to the reviewed GPU render node.")
        try:
            render_info = os.stat(device)
            kfd_info = os.stat("/dev/kfd")
            if not all(stat.S_ISCHR(info.st_mode) for info in (render_info, kfd_info)):
                raise RunnerError("AMD device paths must be character devices.")
            for name, info in (("AMD_RENDER_GID", render_info), ("AMD_KFD_GID", kfd_info)):
                if name in os.environ and os.environ[name] != str(info.st_gid):
                    raise RunnerError(f"{name} does not match the actual device group.")
            return cls(docker=docker, render_device=device, render_gid=render_info.st_gid,
                       kfd_gid=kfd_info.st_gid, architecture=os.environ.get("PYTORCH_ROCM_ARCH", ""),
                       image=os.environ.get("RUNNER_IMAGE", "rocmigrator-runner:latest"))
        except OSError as error:
            raise RunnerError("AMD runner devices or trusted configuration are unavailable.") from error

    async def run(self, job_id: str, operation: str, input_dir: Path,
                  source: str | None = None) -> RunnerResult:
        validate_job_id(job_id)
        if operation not in OPERATIONS:
            raise RunnerError("Unsupported runner operation.")
        if operation == "hipify":
            path = PurePosixPath(source or "")
            if (not source or path.is_absolute() or str(path) != source or ".." in path.parts
                    or "\\" in source or ":" in source or path.suffix not in {".cu", ".cuh"}
                    or any(part.startswith("-") for part in path.parts)
                    or any(ord(character) < 32 for character in source)):
                raise RunnerError("Invalid relative HIPIFY source path.")
        elif source is not None:
            raise RunnerError("Only HIPIFY accepts a source argument.")
        directory = Path(input_dir).resolve(strict=True)
        if not directory.is_dir() or directory == self.harness_dir or directory in self.harness_dir.parents:
            raise RunnerError("Runner input must be isolated from the trusted harness.")
        container_name = f"rocmigrator-{uuid4().hex}"
        service = "verification" if operation in {"verify", "benchmark", "baseline"} else "runner"
        # Explicit environment prevents inherited Docker overrides and API secrets
        # from changing Compose interpolation or reaching container configuration.
        environment = {"PATH": os.defpath, "LANG": "C.UTF-8", **self.settings,
                       "JOB_ID": job_id, "RUNNER_INPUT_DIR": str(directory)}
        argv = [self.docker, "compose", "--env-file", "/dev/null", "-f", str(self.compose_file),
                ]
        if self.settings["AMD_RENDER_GID"] != self.settings["AMD_KFD_GID"]:
            argv.extend(["-f", str(self.compose_file.with_name("docker-compose.kfd-group.yml"))])
        argv.extend(["--project-name", container_name, "--profile", "verify", "run", "--rm", "-T",
                "--no-deps", "--name", container_name, service, operation, job_id]
        )
        if source is not None:
            argv.append(source)
        started = time.monotonic()
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=environment, cwd=self.compose_file.parent)
            captured = [0]

            async def read_bounded(stream: asyncio.StreamReader) -> bytes:
                chunks = []
                while chunk := await stream.read(65536):
                    captured[0] += len(chunk)
                    if captured[0] > MAX_OUTPUT:
                        raise RunnerError("Runner output exceeded the transport budget.")
                    chunks.append(chunk)
                return b"".join(chunks)

            output, errors, code = await asyncio.wait_for(asyncio.gather(
                read_bounded(process.stdout), read_bounded(process.stderr), process.wait()), timeout=295)
            try:
                return parse_result(job_id, operation, code, output.decode("utf-8"),
                                    errors.decode("utf-8"), time.monotonic() - started)
            except RunnerError as error:
                # Docker operational diagnostics are needed when the supervisor
                # never starts. Preserve them without accepting invalid JSON.
                detail = errors.decode("utf-8", errors="replace")[-4096:]
                raise RunnerError(f"{error} Docker exit={code}; stderr: {detail}") from error
            except UnicodeError as error:
                raise RunnerError("Runner output is not valid UTF-8.") from error
        except asyncio.TimeoutError as error:
            raise RunnerError("Runner exceeded its execution deadline; container terminated.") from error
        except OSError as error:
            raise RunnerError("Could not execute the configured Docker runner.") from error
        finally:
            # Killing Docker CLI alone does not kill its container. Removal uses a
            # controller-generated name, never an arbitrary user container name.
            try:
                cleanup = await asyncio.create_subprocess_exec(
                    self.docker, "rm", "-f", container_name, env=environment,
                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL)
                try:
                    await asyncio.wait_for(cleanup.wait(), 5)
                except asyncio.TimeoutError:
                    cleanup.kill()
                    await cleanup.wait()
                    raise RunnerError("Runner container cleanup timed out; operator action required.")
            finally:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
