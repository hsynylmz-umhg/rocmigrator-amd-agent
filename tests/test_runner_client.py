"""Protocol and transport guardrails; these tests do not claim GPU execution."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_orchestrator.runner_client import RunnerClient, RunnerError, parse_result
from contracts.api_schemas import LogEvent
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import VerificationReport


class RunnerProtocolTests(unittest.TestCase):
    def event(self, **changes):
        values = dict(job_id="job-1", state=PipelineState.COMPILING, level="INFO", message="compiler exited 0")
        values.update(changes)
        return LogEvent(**values).model_dump_json()

    def parse(self, output, code=0, operation="compile"):
        return parse_result("job-1", operation, code, output, "", 0.5)

    def test_compiler_failure_preserves_diagnostics(self):
        result = self.parse(self.event(level="ERROR", message="hipcc error: unknown type"), code=1)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown type", result.event.message)

    def test_rejects_wrong_job_state_and_exit_status(self):
        for output, code in ((self.event(job_id="job-2"), 0),
                             (self.event(state=PipelineState.HIPIFICATION), 0),
                             (self.event(), 1), (self.event(level="ERROR"), 0)):
            with self.subTest(output=output, code=code), self.assertRaises(RunnerError):
                self.parse(output, code)

    def test_rejects_malformed_extra_and_duplicate_json(self):
        for output in ("", "[]", "{}", self.event() + self.event(),
                       self.event().replace('"job_id":', '"job_id":"forged","job_id":')):
            with self.subTest(output=output), self.assertRaises(RunnerError):
                self.parse(output)

    def test_verification_requires_a_report_and_benchmark_requires_measurements(self):
        for operation, state in (("verify", PipelineState.VERIFYING), ("benchmark", PipelineState.BENCHMARKING)):
            with self.subTest(operation=operation), self.assertRaises(RunnerError):
                self.parse(self.event(state=state), operation=operation)

    def test_failed_numerical_report_is_preserved(self):
        report = VerificationReport(job_id="job-1", overall_status="FAILED", cpu_reference_verified=False,
                                    determinism_passed=False, summary="GPU unavailable in protocol test")
        result = self.parse(report.model_dump_json(), code=1, operation="verify")
        self.assertEqual(result.report.overall_status, "FAILED")
        with self.assertRaises(RunnerError):
            self.parse(report.model_dump_json(), code=0, operation="verify")


class RunnerInvocationTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_argv_clean_environment_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compose = root / "docker-compose.yml"
            compose.touch()
            harness, source = root / "harness", root / "input"
            harness.mkdir()
            source.mkdir()
            client = RunnerClient(docker="/usr/bin/docker", render_device="/dev/dri/renderD128",
                                  render_gid=992, kfd_gid=992, architecture="gfx942", image="runner:reviewed",
                                  compose_file=compose, harness_dir=harness)
            stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
            stdout.feed_data(LogEvent(job_id="job-1", state=PipelineState.COMPILING,
                                     message="real invocation replaced by test transport").model_dump_json().encode())
            stdout.feed_eof()
            stderr.feed_eof()
            class Process:
                returncode = 0
                wait = AsyncMock(return_value=0)
            process = Process()
            process.stdout, process.stderr = stdout, stderr
            with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as launch:
                result = await client.run("job-1", "compile", source)
            self.assertEqual(result.returncode, 0)
            command, options = launch.call_args_list[0]
            self.assertEqual(command[-3:], ("runner", "compile", "job-1"))
            self.assertNotIn("shell", options)
            self.assertNotIn("OPENAI_API_KEY", options["env"])
            self.assertNotIn("HOME", options["env"])
            self.assertEqual(options["env"]["AMD_RENDER_GID"], "992")
            self.assertEqual(launch.call_args_list[-1].args[1:3], ("rm", "-f"))
            with self.assertRaises(RunnerError):
                await client.run("job-1", "hipify", source, "../escape.cu")
            with self.assertRaises(RunnerError):
                await client.run("job-1;command", "compile", source)


if __name__ == "__main__":
    unittest.main()
