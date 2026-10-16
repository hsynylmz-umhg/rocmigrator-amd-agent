#!/bin/bash
# Fixed argv: hipify JOB_ID relative/file.cu | compile JOB_ID | verify JOB_ID.
# Python owns JSON escaping, bounded output, process groups, and the deadline.
set -euo pipefail
exec /opt/runner/bin/python -I - "$@" <<'PY'
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

sys.path.insert(0, "/opt/rocmigrator")
from contracts.api_schemas import LogEvent
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import VerificationReport

INPUT = Path("/input")
WORK = Path("/workspace")
HARNESS = Path("/verification/verify.py")
PYTHON = "/opt/runner/bin/python"
MAX_OUTPUT = 256 * 1024
MAX_INPUT = 32 * 1024 * 1024
STATES = {"hipify": PipelineState.HIPIFICATION, "compile": PipelineState.COMPILING,
          "verify": PipelineState.VERIFYING}


class GuardError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardError(message)


def bounded_integer(path: Path, maximum: int) -> None:
    value = path.read_text().strip()
    require(value.isdecimal() and 0 < int(value) <= maximum,
            f"Missing or excessive cgroup limit: {path.name}.")


def protect_supervisor() -> None:
    # Child build code shares UID 1000. Deny access to /proc/1/fd and ptrace so it
    # cannot bypass captured pipes and forge the supervisor's JSON channel.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(4, 0, 0, 0, 0) == 0, "Could not protect the runner supervisor.")


def isolation_checks() -> None:
    require(sys.platform == "linux", "This runner requires Linux on the isolated AMD host.")
    require(os.getuid() == os.geteuid() == 1000, "Runner UID must be 1000.")
    require(os.getpid() == 1, "Runner supervisor must be container PID 1; do not use --init.")
    require(set(os.listdir("/sys/class/net")) == {"lo"}, "Docker network must be none.")
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    require(status["NoNewPrivs"].strip() == "1", "no-new-privileges is required.")
    require(all(int(status[key].strip(), 16) == 0 for key in ("CapEff", "CapPrm", "CapBnd")),
            "All Linux capabilities must be dropped.")
    require(status["Seccomp"].strip() == "2", "Docker's seccomp filter is required.")
    require(bool(os.statvfs("/").f_flag & os.ST_RDONLY), "Root filesystem must be read-only.")
    group = Path("/sys/fs/cgroup")
    require((group / "cgroup.controllers").is_file(), "A private cgroup v2 namespace is required.")
    require(Path("/proc/self/cgroup").read_text().strip() == "0::/",
            "The container must have its own cgroup v2 namespace root.")
    bounded_integer(group / "memory.max", 16 * 1024**3)
    bounded_integer(group / "pids.max", 256)
    require((group / "memory.swap.max").read_text().strip() == "0", "Container swap must be disabled.")
    quota, period = (group / "cpu.max").read_text().split()
    require(quota.isdecimal() and period.isdecimal() and 0 < int(quota) <= 4 * int(period),
            "CPU quota must be finite and at most four cores.")
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        fields = before.split()
        mounts[fields[4]] = (set(fields[5].split(",")), after.split()[0])
    for path, limit in (("/workspace", 8 * 1024**3), ("/tmp", 1024**3), ("/dev/shm", 1024**3)):
        flags, filesystem = mounts.get(path, (set(), ""))
        require(filesystem == "tmpfs" and {"nosuid", "nodev"} <= flags,
                f"{path} must be a bounded nosuid,nodev tmpfs mount.")
        if path == "/tmp":
            require("noexec" in flags, "/tmp must prohibit executable mappings.")
        if path == "/workspace":
            require("noexec" not in flags, "/workspace must allow compiled extension mappings.")
        info = os.statvfs(path)
        require(info.f_blocks * info.f_frsize <= limit, f"{path} exceeds its disk budget.")
    require("ro" in mounts.get("/input", (set(), ""))[0], "/input must be a read-only repository export.")
    require(not any(re.search(r"TOKEN|SECRET|PASSWORD|PRIVATE_KEY|CREDENTIAL|SSH_AUTH_SOCK|AWS_ACCESS_KEY", name, re.I)
                    for name in os.environ), "Credential-like environment variables are forbidden.")
    # These process limits supplement Docker cgroups; they do not replace them.
    import resource
    for kind, limit in ((resource.RLIMIT_CORE, 0), (resource.RLIMIT_NOFILE, 1024),
                        (resource.RLIMIT_FSIZE, 64 * 1024**2)):
        resource.setrlimit(kind, (limit, limit))
    protect_supervisor()


def relative_source(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    require(bool(value) and not path.is_absolute() and str(path) == value
            and ".." not in path.parts and "\\" not in value and ":" not in value
            and not any(ord(character) < 32 for character in value)
            and all(not part.startswith("-") for part in path.parts)
            and path.suffix in (".cu", ".cuh"), "HIPIFY requires a canonical relative .cu/.cuh path.")
    return path


def stage_input(deadline: float) -> None:
    require(INPUT.is_dir() and not any(WORK.iterdir()), "Use a fresh workspace and a repository export at /input.")
    files = []
    total = 0
    entries = 0
    # Stage only regular files, never devices, sockets, symlinks, or hardlinks.
    # The read-only export must remain immutable on the host for this container.
    for directory, directories, names in os.walk(INPUT, followlinks=False):
        require(time.monotonic() < deadline, "Repository staging exceeded the task deadline.")
        for name in directories + names:
            entries += 1
            path = Path(directory) / name
            relative = path.relative_to(INPUT)
            require(name not in {".git", ".ssh", ".aws", ".azure", ".config", ".docker"}
                    and not name.startswith(".env") and path.suffix not in {".pem", ".key"},
                    "Repository export contains forbidden credential or configuration paths.")
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1),
                    "Repository export must contain only directories and ordinary nonlinked files.")
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
                files.append(relative)
            require(entries <= 2048 and total <= MAX_INPUT, "Repository export exceeds the staging budget.")
    for relative in files:
        require(time.monotonic() < deadline, "Repository staging exceeded the task deadline.")
        destination = WORK / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(INPUT / relative, destination, follow_symlinks=False)
        destination.chmod(0o600)
    (WORK / "home").mkdir(exist_ok=True)


def child_environment() -> dict[str, str]:
    python_bin = str(Path(PYTHON).resolve().parent)
    arch = os.environ.get("PYTORCH_ROCM_ARCH", "")
    require(bool(re.fullmatch(r"gfx[0-9a-f]{3,4}", arch)), "Set one reviewed PYTORCH_ROCM_ARCH, for example gfx90a.")
    return {
        "PATH": f"/opt/runner/bin:{python_bin}:/opt/rocm/bin:/opt/rocm/hip/bin:/usr/bin:/bin",
        "HOME": "/workspace/home", "TMPDIR": "/tmp", "LANG": "C.UTF-8",
        "LD_LIBRARY_PATH": f"/opt/rocm/lib:/opt/rocm/lib64:{sys.base_prefix}/lib",
        "ROCM_PATH": "/opt/rocm", "ROCM_HOME": "/opt/rocm", "HIP_PLATFORM": "amd",
        "PYTORCH_ROCM_ARCH": arch, "MAX_JOBS": "2", "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2", "PIP_NO_INDEX": "1", "PIP_CONFIG_FILE": "/dev/null",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "HIP_VISIBLE_DEVICES": "0", "ROCR_VISIBLE_DEVICES": "0",
    }


def terminate_children(process: subprocess.Popen) -> None:
    # PID 1 owns a private container namespace. Kill all children, including
    # double-forked/setsid descendants, before trusting a later phase's output.
    require(os.getpid() == 1, "Child cleanup requires container PID 1.")
    try:
        os.kill(-1, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)
    cleanup_deadline = time.monotonic() + 2
    while True:
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            pass
        if not any(name.isdecimal() and name != "1" for name in os.listdir("/proc")):
            return
        require(time.monotonic() < cleanup_deadline, "A child process could not be terminated.")
        time.sleep(0.01)


def run_command(argv: list[str], environment: dict[str, str], deadline: float) -> tuple[int, str, str]:
    require(os.getpid() == 1, "Task execution requires container PID 1.")
    require(time.monotonic() < deadline, "Task exceeded its execution deadline.")
    output = bytearray()
    errors = bytearray()
    process = subprocess.Popen(argv, cwd=WORK, env=environment, shell=False,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, output)
            selector.register(process.stderr, selectors.EVENT_READ, errors)
            while selector.get_map():
                require(time.monotonic() < deadline, "Task timed out; process group was terminated.")
                for key, _ in selector.select(timeout=0.1):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    require(len(output) + len(errors) + len(chunk) <= MAX_OUTPUT,
                            "Tool output exceeded 256 KiB; process group was terminated.")
                    key.data.extend(chunk)
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        return code, output.decode("utf-8", errors="replace"), errors.decode("utf-8", errors="replace")
    finally:
        try:
            terminate_children(process)
        finally:
            process.stdout.close()
            process.stderr.close()


def event(job_id: str, command: str, message: str, success: bool) -> None:
    print(LogEvent(job_id=job_id, state=STATES.get(command, PipelineState.CREATED),
                   level="INFO" if success else "ERROR", message=message, data=None).model_dump_json(), flush=True)


def diagnostics(code: int, output: str, errors: str) -> str:
    return f"Process exit code: {code}\nstdout:\n{output}\nstderr:\n{errors}"


def read_report(job_id: str) -> VerificationReport:
    descriptor = os.open(WORK / "verification_report.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as report_file:
        info = os.fstat(report_file.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_OUTPUT,
                "Verification report must be a bounded regular file.")
        report = VerificationReport.model_validate_json(report_file.read(MAX_OUTPUT + 1))
    require(report.job_id == job_id, "Verification report belongs to a different job.")
    require(report.overall_status in {"VERIFIED", "FAILED"}, "Verification cannot assert a rollback.")
    if report.overall_status == "VERIFIED":
        require(len({result.seed for result in report.results}) >= 2
                and len({result.shape for result in report.results}) >= 2
                and len({result.dtype for result in report.results}) >= 2,
                "VERIFIED requires multiple seeds, shapes, and dtypes.")
    return report


def main(arguments: list[str]) -> int:
    # Reserve five seconds of the 300-second maximum for termination and JSON.
    deadline = time.monotonic() + 295
    command = arguments[0] if arguments else ""
    job_id = arguments[1] if len(arguments) > 1 and arguments[1].strip() else "runner-rejected"
    try:
        require(command in STATES and len(arguments) == (3 if command == "hipify" else 2)
                and job_id != "runner-rejected", "Usage: hipify JOB_ID relative.cu | compile JOB_ID | verify JOB_ID.")
        source = relative_source(arguments[2]) if command == "hipify" else None
        isolation_checks()
        environment = child_environment()
        stage_input(deadline)
        if source is not None:
            target = WORK / source
            require(target.is_file(), "Requested HIPIFY source does not exist.")
            code, output, errors = run_command(["/opt/runner/bin/hipify-perl", str(target)], environment, deadline)
            if code == 0:
                require(bool(output.strip()) and "\ufffd" not in output, "HIPIFY returned empty or invalid UTF-8 source.")
                # Return translated source; disposable workspace mutations do not
                # persist between commands. The engine must stage this result.
                if errors:
                    print(errors, file=sys.stderr, end="")
                event(job_id, command, output, True)
                return 0
            event(job_id, command, diagnostics(code, output, errors), False)
            return 1
        require((WORK / "setup.py").is_file(), "Repository export must include setup.py.")
        if command == "verify":
            require(HARNESS.is_file() and not HARNESS.is_symlink()
                    and bool(os.statvfs(HARNESS).f_flag & os.ST_RDONLY),
                    "Mount a trusted, read-only numerical harness at /verification/verify.py.")
            gpu_check = ("import torch; assert torch.version.hip, 'ROCm PyTorch required'; "
                         "assert torch.cuda.is_available(), 'AMD GPU unavailable'; "
                         "assert torch.cuda.device_count() == 1, 'Exactly one GPU required'; "
                         "x=torch.ones(1, device='cuda'); torch.cuda.synchronize(); assert x.is_cuda")
            code, output, errors = run_command([PYTHON, "-I", "-c", gpu_check], environment, deadline)
            require(code == 0, "GPU preflight failed. " + diagnostics(code, output, errors))
        code, output, errors = run_command([PYTHON, "setup.py", "build_ext", "--inplace"], environment, deadline)
        if code != 0 or command == "compile":
            event(job_id, command, diagnostics(code, output, errors), code == 0)
            return 0 if code == 0 else 1
        # A verification invocation rebuilds its own ephemeral workspace. The
        # trusted harness calls the compiled extension against CPU references,
        # uses assert_close and existing tolerances, and writes the strict report.
        (WORK / "verification_report.json").unlink(missing_ok=True)
        code, output, errors = run_command([PYTHON, "-I", str(HARNESS), job_id,
                                           str(WORK / "verification_report.json")], environment, deadline)
        require(code == 0, "Numerical harness failed. " + diagnostics(code, output, errors))
        report = read_report(job_id)
        print(report.model_dump_json(), flush=True)
        return 0 if report.overall_status == "VERIFIED" else 1
    except (Exception, KeyboardInterrupt) as error:
        # Validation errors may contain untrusted input; do not echo full reprs.
        message = str(error) if isinstance(error, GuardError) else f"Runner failed: {type(error).__name__}."
        event(job_id, command, message, False)
        return 1


def cancelled(signum, frame) -> None:
    raise GuardError("Runner cancelled; execution was interrupted.")


def expired(signum, frame) -> None:
    raise GuardError("Runner exceeded its 295-second execution deadline.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(295)
    try:
        result = main(sys.argv[1:])
    finally:
        signal.alarm(0)
    sys.exit(result)
PY
