"""Exercise the embedded runner supervisor without executing repository code or GPU jobs."""

import contextlib
import io
import json
import os
import signal
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from contracts.api_schemas import LogEvent
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import NumericalResult, VerificationReport


def load_supervisor():
    script = Path(__file__).resolve().parents[1] / "runner" / "entrypoint.sh"
    source = script.read_text(encoding="utf-8").split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    module = types.ModuleType("runner_supervisor_under_test")
    # The deployed script adds its immutable contract directory. Restore the
    # host path immediately after loading its definitions; never run main here.
    with patch.object(sys, "path", list(sys.path)):
        exec(compile(source, str(script), "exec"), module.__dict__)
    return module


runner = load_supervisor()


def report_for(job_id="runner-test", *, verified=False, diverse=True):
    cases = ((42, (8,), "float32"), (43, (16,), "float64")) if diverse else ((42, (8,), "float32"),)
    results = tuple(
        NumericalResult(
            seed=seed, shape=shape, dtype=dtype, atol=1e-5, rtol=1e-5,
            max_abs_err=0.0, max_rel_err=0.0, mismatch_ratio=0.0,
            nan_inf_detected=False, passed=True,
        ) for seed, shape, dtype in cases
    ) if verified else ()
    return VerificationReport(
        job_id=job_id, overall_status="VERIFIED" if verified else "FAILED",
        cpu_reference_verified=verified, determinism_passed=verified,
        results=results, total_tests=len(results), passed_tests=len(results),
        failed_tests=0, summary="Synthetic supervisor test evidence; no GPU execution.",
    )


class RunnerGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.work = self.directory / "workspace"
        self.input = self.directory / "input"
        self.work.mkdir()
        self.input.mkdir()
        self.stack.enter_context(patch.object(runner, "WORK", self.work))
        self.stack.enter_context(patch.object(runner, "INPUT", self.input))
        # These timers exist only on Linux. Tests inspect supervisor behavior
        # with an explicit deadline and never arm a signal on the test process.
        for name, value in (("alarm", MagicMock()), ("setitimer", MagicMock()),
                            ("SIGALRM", 14), ("SIGKILL", 9), ("ITIMER_REAL", 0)):
            self.stack.enter_context(patch.object(signal, name, value, create=True))

    @contextlib.contextmanager
    def isolated_linux(self, *, uid=1000, interfaces=("lo",), status_changes=None, limits=None, mount_changes=None):
        status = {"NoNewPrivs": "1", "CapEff": "0", "CapPrm": "0", "CapBnd": "0", "Seccomp": "2"}
        status.update(status_changes or {})
        files = {
            "/proc/self/status": "\n".join(f"{name}:\t{value}" for name, value in status.items()),
            "/proc/self/cgroup": "0::/\n",
            "/sys/fs/cgroup/memory.max": str(16 * 1024**3),
            "/sys/fs/cgroup/pids.max": "256",
            "/sys/fs/cgroup/memory.swap.max": "0",
            "/sys/fs/cgroup/cpu.max": "400000 100000",
            "/proc/self/mountinfo": "\n".join(
                f"1 0 0:1 / {path} {(mount_changes or {}).get(path, flags)} - {filesystem} none rw"
                for path, flags, filesystem in (
                    ("/workspace", "rw,nosuid,nodev", "tmpfs"),
                    ("/tmp", "rw,nosuid,nodev,noexec", "tmpfs"),
                    ("/dev/shm", "rw,nosuid,nodev", "tmpfs"),
                    ("/input", "ro", "ext4"),
                )
            ),
        }
        files.update(limits or {})
        resource = types.SimpleNamespace(RLIMIT_CORE=4, RLIMIT_NOFILE=7, RLIMIT_FSIZE=1, setrlimit=MagicMock())
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, "platform", "linux"))
            stack.enter_context(patch.object(os, "getuid", return_value=uid, create=True))
            stack.enter_context(patch.object(os, "geteuid", return_value=uid, create=True))
            stack.enter_context(patch.object(os, "getpid", return_value=1))
            stack.enter_context(patch.object(os, "listdir", return_value=list(interfaces)))
            stack.enter_context(patch.object(os, "ST_RDONLY", 1, create=True))
            stack.enter_context(patch.object(os, "statvfs", return_value=types.SimpleNamespace(
                f_flag=1, f_blocks=1024, f_frsize=4096), create=True))
            stack.enter_context(patch.object(Path, "read_text", lambda path, *args, **kwargs: files[path.as_posix()]))
            stack.enter_context(patch.object(Path, "is_file", return_value=True))
            stack.enter_context(patch.dict(os.environ, {"PYTORCH_ROCM_ARCH": "gfx90a"}, clear=True))
            stack.enter_context(patch.dict(sys.modules, {"resource": resource}))
            if hasattr(runner, "protect_supervisor"):
                stack.enter_context(patch.object(runner, "protect_supervisor"))
            yield resource

    def invoke(self, arguments, *, isolation_error=None, result=(0, "built", "")):
        (self.work / "setup.py").write_text("# Never executed by these tests.\n")
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, "isolation_checks", side_effect=isolation_error))
            stack.enter_context(patch.object(runner, "stage_input"))
            stack.enter_context(patch.object(runner, "child_environment", return_value={"PIP_NO_INDEX": "1"}))
            command = stack.enter_context(patch.object(runner, "run_command", return_value=result))
            stack.enter_context(contextlib.redirect_stdout(output))
            code = runner.main(arguments)
        event = LogEvent.model_validate_json(output.getvalue().strip())
        return code, event, command

    def test_root_is_rejected_before_execution(self):
        with self.isolated_linux(uid=0), self.assertRaisesRegex(runner.GuardError, "UID"):
            runner.isolation_checks()

    def test_external_network_interface_is_rejected(self):
        with self.isolated_linux(interfaces=("lo", "eth0")), self.assertRaisesRegex(runner.GuardError, "network"):
            runner.isolation_checks()

    def test_privilege_escalation_and_capabilities_are_rejected(self):
        for changes in ({"NoNewPrivs": "0"}, {"CapEff": "1"}, {"CapPrm": "1"}, {"CapBnd": "1"}, {"Seccomp": "0"}):
            with self.subTest(changes=changes), self.isolated_linux(status_changes=changes):
                with self.assertRaises(runner.GuardError):
                    runner.isolation_checks()

    def test_unbounded_or_excessive_resources_are_rejected(self):
        for path, value in (("memory.max", "max"), ("memory.max", str(17 * 1024**3)),
                            ("pids.max", "max"), ("pids.max", "257"),
                            ("memory.swap.max", "1"), ("cpu.max", "max 100000"),
                            ("cpu.max", "500000 100000")):
            with self.subTest(path=path, value=value), self.isolated_linux(limits={f"/sys/fs/cgroup/{path}": value}):
                with self.assertRaises(runner.GuardError):
                    runner.isolation_checks()

    def test_valid_isolation_applies_process_limits(self):
        with self.isolated_linux() as resource:
            runner.isolation_checks()
        self.assertEqual(resource.setrlimit.call_count, 3)

    def test_missing_cgroup_is_rejected(self):
        with self.isolated_linux(), patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(runner.GuardError, "cgroup"):
                runner.isolation_checks()

    def test_shared_cgroup_namespace_is_rejected(self):
        with self.isolated_linux(limits={"/proc/self/cgroup": "0::/docker/host-job"}):
            with self.assertRaisesRegex(runner.GuardError, "namespace root"):
                runner.isolation_checks()

    def test_mount_policy_rejects_writable_input_and_executable_temp(self):
        for changes in ({"/input": "rw"}, {"/tmp": "rw,nosuid,nodev"}, {"/workspace": "rw,nosuid,nodev,noexec"}):
            with self.subTest(changes=changes), self.isolated_linux(mount_changes=changes):
                with self.assertRaises(runner.GuardError):
                    runner.isolation_checks()

    def test_writable_root_is_rejected(self):
        with self.isolated_linux(), patch.object(os, "statvfs", return_value=types.SimpleNamespace(f_flag=0)):
            with self.assertRaisesRegex(runner.GuardError, "read-only"):
                runner.isolation_checks()

    def test_credentials_cannot_enter_runner_environment(self):
        with self.isolated_linux(), patch.dict(os.environ, {"GITHUB_TOKEN": "sentinel"}):
            with self.assertRaisesRegex(runner.GuardError, "Credential"):
                runner.isolation_checks()

    def test_supervisor_protection_failure_is_fatal(self):
        import ctypes

        libc = MagicMock()
        libc.prctl.return_value = -1
        with patch.object(ctypes, "CDLL", return_value=libc):
            with self.assertRaisesRegex(runner.GuardError, "protect"):
                runner.protect_supervisor()
        libc.prctl.assert_called_once_with(4, 0, 0, 0, 0)

    def test_unknown_command_cannot_start_a_child(self):
        code, event, command = self.invoke(["bash", "runner-test"])
        self.assertEqual(code, 1)
        self.assertEqual(event.level, "ERROR")
        self.assertEqual(event.state, PipelineState.CREATED)
        command.assert_not_called()

    def test_invalid_hipify_paths_cannot_start_a_child(self):
        for value in ("../escape.cu", "/absolute.cu", "csrc/../escape.cu", "-o.cu", "csrc/-help.cu", "csrc\\kernel.cu", "C:/kernel.cu", "kernel.py", "./kernel.cu", "csrc/line\nbreak.cu"):
            with self.subTest(path=value):
                code, event, command = self.invoke(["hipify", "runner-test", value])
                self.assertEqual(code, 1)
                self.assertEqual(event.level, "ERROR")
                command.assert_not_called()

    def test_security_failure_returns_contract_json_without_child(self):
        code, event, command = self.invoke(["compile", "runner-test"], isolation_error=runner.GuardError("Network isolation is required."))
        self.assertEqual(code, 1)
        self.assertEqual(event.job_id, "runner-test")
        self.assertEqual(event.state, PipelineState.COMPILING)
        self.assertIn("Network isolation", event.message)
        command.assert_not_called()

    def test_compile_runs_only_fixed_argv_and_preserves_diagnostics(self):
        code, event, command = self.invoke(["compile", "runner-test"], result=(2, "build output", 'compiler: "bad token"\nsecond line'))
        self.assertEqual(code, 1)
        self.assertEqual(event.level, "ERROR")
        self.assertIn('compiler: "bad token"\nsecond line', event.message)
        self.assertEqual(command.call_args.args[0], [runner.PYTHON, "setup.py", "build_ext", "--inplace"])
        self.assertEqual(command.call_count, 1)

    def test_compile_success_does_not_claim_verification(self):
        code, event, _ = self.invoke(["compile", "runner-test"])
        self.assertEqual(code, 0)
        self.assertEqual(event.level, "INFO")
        self.assertEqual(event.state, PipelineState.COMPILING)
        self.assertIsNone(event.data)

    def test_staging_rejects_secret_paths_before_copy(self):
        for name in (".env", ".env.local", "private.pem", "private.key", ".git"):
            path = self.input / name
            path.write_text("must remain unread")
            with self.subTest(path=name), self.assertRaises(runner.GuardError):
                runner.stage_input(float("inf"))
            self.assertEqual(list(self.work.iterdir()), [])
            path.unlink()

    def test_staging_rejects_linked_files(self):
        source = self.input / "kernel.cu"
        source.write_text("kernel")
        for mode, links in ((stat.S_IFLNK | 0o777, 1), (stat.S_IFREG | 0o600, 2)):
            with self.subTest(mode=mode, links=links), patch.object(Path, "lstat", return_value=types.SimpleNamespace(st_mode=mode, st_nlink=links, st_size=6)):
                with self.assertRaisesRegex(runner.GuardError, "nonlinked"):
                    runner.stage_input(float("inf"))
            self.assertEqual(list(self.work.iterdir()), [])

    def test_staging_copies_bounded_export_without_modifying_input(self):
        (self.input / "csrc").mkdir()
        source = self.input / "csrc" / "kernel.cu"
        source.write_text("original source")
        runner.stage_input(float("inf"))
        self.assertEqual((self.work / "csrc" / "kernel.cu").read_text(), "original source")
        self.assertEqual(source.read_text(), "original source")
        self.assertTrue((self.work / "home").is_dir())

    def test_staging_deadline_prevents_copy(self):
        (self.input / "kernel.cu").write_text("source")
        with self.assertRaisesRegex(runner.GuardError, "deadline"):
            runner.stage_input(0.0)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_oversized_export_is_rejected_before_copy(self):
        (self.input / "kernel.cu").write_text("oversized input")
        with patch.object(runner, "MAX_INPUT", 2), self.assertRaisesRegex(runner.GuardError, "staging budget"):
            runner.stage_input(float("inf"))
        self.assertEqual(list(self.work.iterdir()), [])

    def test_directory_flood_counts_against_export_budget(self):
        directories = [f"directory-{number}" for number in range(2049)]
        with patch.object(os, "walk", return_value=[(str(self.input), directories, [])]):
            with patch.object(Path, "lstat", return_value=types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o700)):
                with self.assertRaisesRegex(runner.GuardError, "staging budget"):
                    runner.stage_input(float("inf"))
        self.assertEqual(list(self.work.iterdir()), [])

    def test_child_environment_drops_host_injection_and_credentials(self):
        with patch.dict(os.environ, {"PYTORCH_ROCM_ARCH": "gfx90a", "LD_PRELOAD": "evil.so", "PYTHONPATH": "untrusted", "PATH": "untrusted", "GITHUB_TOKEN": "sentinel"}, clear=True):
            environment = runner.child_environment()
        self.assertNotIn("LD_PRELOAD", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("untrusted", environment["PATH"])
        self.assertEqual(environment["PIP_NO_INDEX"], "1")
        self.assertEqual(environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")

    def test_architecture_must_be_one_reviewed_target(self):
        for value in ("", "gfx90a;curl attacker", "gfx90a gfx1100", "native"):
            with self.subTest(value=value), patch.dict(os.environ, {"PYTORCH_ROCM_ARCH": value}, clear=True):
                with self.assertRaises(runner.GuardError):
                    runner.child_environment()

    @contextlib.contextmanager
    def fake_child(self, stdout, stderr, *, clock=None):
        process = MagicMock(pid=1234)
        process.wait.return_value = 0
        selector = MagicMock()
        selector.__enter__.return_value = selector
        keys = {}
        chunks = {10: iter([stdout, b""]), 11: iter([stderr, b""])}

        def register(fileobj, events, data):
            fd = 10 if fileobj is process.stdout else 11
            keys[fd] = types.SimpleNamespace(fd=fd, fileobj=fileobj, data=data)

        def unregister(fileobj):
            keys.pop(10 if fileobj is process.stdout else 11)

        selector.register.side_effect = register
        selector.unregister.side_effect = unregister
        selector.get_map.side_effect = lambda: keys
        selector.select.side_effect = lambda **kwargs: [(key, 1) for key in list(keys.values())]
        with contextlib.ExitStack() as stack:
            popen = stack.enter_context(patch.object(runner.subprocess, "Popen", return_value=process))
            stack.enter_context(patch.object(runner.selectors, "DefaultSelector", return_value=selector))
            stack.enter_context(patch.object(os, "read", side_effect=lambda fd, size: next(chunks[fd])))
            stack.enter_context(patch.object(os, "getpid", return_value=1))
            cleanup = stack.enter_context(patch.object(runner, "terminate_children"))
            if clock is not None:
                stack.enter_context(patch.object(runner.time, "monotonic", side_effect=clock))
            yield process, popen, cleanup

    def test_child_output_is_captured_and_descendants_are_cleaned_up(self):
        with self.fake_child(b"output\n", b"invalid utf8: \xff") as (process, popen, cleanup):
            result = runner.run_command(["reviewed-tool", "literal;argument"], {"PIP_NO_INDEX": "1"}, float("inf"))
        self.assertEqual(result, (0, "output\n", "invalid utf8: \ufffd"))
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.args[0], ["reviewed-tool", "literal;argument"])
        cleanup.assert_called_once_with(process)
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_output_flood_terminates_child_group(self):
        with self.fake_child(b"x" * (runner.MAX_OUTPUT + 1), b"") as (process, _, cleanup):
            with self.assertRaisesRegex(runner.GuardError, "output exceeded"):
                runner.run_command(["reviewed-tool"], {}, float("inf"))
        cleanup.assert_called_once_with(process)
        process.stdout.close.assert_called_once()

    def test_deadline_terminates_child_group(self):
        with self.fake_child(b"", b"", clock=[0.0, 2.0]) as (process, _, cleanup):
            with self.assertRaisesRegex(runner.GuardError, "timed out"):
                runner.run_command(["reviewed-tool"], {}, 1.0)
        cleanup.assert_called_once_with(process)
        process.stderr.close.assert_called_once()

    def test_cleanup_kills_detached_descendants_and_reaps_children(self):
        process = MagicMock()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(os, "getpid", return_value=1))
            stack.enter_context(patch.object(os, "WNOHANG", 1, create=True))
            kill = stack.enter_context(patch.object(os, "kill"))
            waitpid = stack.enter_context(patch.object(os, "waitpid", side_effect=[(1234, 0), (0, 0), (0, 0)]))
            stack.enter_context(patch.object(os, "listdir", side_effect=[["1", "1234"], ["1", "self"]]))
            stack.enter_context(patch.object(runner.time, "sleep"))
            runner.terminate_children(process)
        kill.assert_called_once_with(-1, signal.SIGKILL)
        process.wait.assert_called_once_with(timeout=2)
        self.assertEqual(waitpid.call_count, 3)

    def test_cleanup_refuses_to_signal_outside_container_pid_one(self):
        with patch.object(os, "getpid", return_value=1234), patch.object(os, "kill") as kill:
            with self.assertRaisesRegex(runner.GuardError, "PID 1"):
                runner.terminate_children(MagicMock())
        kill.assert_not_called()

    def test_build_cannot_supply_a_stale_successful_report(self):
        report_path = self.work / "verification_report.json"
        harness = self.directory / "verify.py"
        harness.write_text("# Trusted harness is intercepted by the test.\n")
        (self.work / "setup.py").write_text("# Untrusted build is intercepted by the test.\n")
        calls = []

        def simulated_command(argv, environment, deadline):
            calls.append(argv)
            if "setup.py" in argv:
                report_path.write_text(report_for(verified=True).model_dump_json())
            elif str(harness) in argv:
                self.assertFalse(report_path.exists(), "A stale build-produced report reached verification.")
                # A successful exit without fresh evidence must never verify.
            return 0, "", ""

        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(runner, "HARNESS", harness))
            stack.enter_context(patch.object(runner, "isolation_checks"))
            stack.enter_context(patch.object(runner, "stage_input"))
            stack.enter_context(patch.object(runner, "child_environment", return_value={}))
            stack.enter_context(patch.object(runner, "run_command", side_effect=simulated_command))
            stack.enter_context(patch.object(os, "ST_RDONLY", 1, create=True))
            stack.enter_context(patch.object(os, "statvfs", return_value=types.SimpleNamespace(f_flag=1), create=True))
            stack.enter_context(patch.object(os, "O_NOFOLLOW", 0, create=True))
            stack.enter_context(patch.object(os, "O_NONBLOCK", 0, create=True))
            stack.enter_context(contextlib.redirect_stdout(output))
            code = runner.main(["verify", "runner-test"])
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 3)
        event = LogEvent.model_validate_json(output.getvalue().strip())
        self.assertEqual(event.level, "ERROR")
        self.assertIn("FileNotFoundError", event.message)

    def read_report(self, contents, job_id="runner-test"):
        (self.work / "verification_report.json").write_text(contents, encoding="utf-8")
        with patch.object(os, "O_NOFOLLOW", 0, create=True), patch.object(os, "O_NONBLOCK", 0, create=True):
            return runner.read_report(job_id)

    def test_report_requires_matching_job_and_existing_strict_schema(self):
        with self.assertRaisesRegex(runner.GuardError, "different job"):
            self.read_report(report_for("another-job").model_dump_json())
        invalid = json.loads(report_for().model_dump_json())
        invalid["cpu_reference_verified"] = "false"
        with self.assertRaises(ValueError):
            self.read_report(json.dumps(invalid))

    def test_verified_report_requires_diverse_evidence(self):
        with self.assertRaisesRegex(runner.GuardError, "multiple seeds"):
            self.read_report(report_for(verified=True, diverse=False).model_dump_json())
        expected = report_for(verified=True)
        self.assertEqual(self.read_report(expected.model_dump_json()), expected)

    def test_failed_report_is_returned_without_upgrading_status(self):
        expected = report_for()
        self.assertEqual(self.read_report(expected.model_dump_json()), expected)

    @unittest.skipUnless(sys.platform == "linux", "Linux O_NOFOLLOW behavior is enforced by the deployed runner.")
    def test_report_symlink_is_rejected_by_kernel(self):
        external = self.directory / "external.json"
        external.write_text(report_for().model_dump_json())
        (self.work / "verification_report.json").symlink_to(external)
        with self.assertRaises(OSError):
            runner.read_report("runner-test")


if __name__ == "__main__":
    unittest.main()
