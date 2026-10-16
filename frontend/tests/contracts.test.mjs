import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  PIPELINE_STATES,
  parseJobStatusResponse,
  parseLogEvent,
  parseVerificationReport,
} from "../src/lib/contracts.ts";

// Generate the wire fixtures from the actual backend contracts so changes to
// Python defaults, field names, enums, or payload variants break this boundary test.
const repository = fileURLToPath(new URL("../../", import.meta.url));
const fixtures = JSON.parse(execFileSync(process.env.PYTHON ?? "python", ["-c", `
import json
from datetime import datetime, timezone
from contracts.api_schemas import (
    AnalysisLogData, BenchmarkLogData, EmptyLogData, JobStatusResponse,
    LogEvent, PRLogData,
)
from contracts.patch_schemas import PatchProposal
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import NumericalResult, VerificationReport

stamp = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
patch = PatchProposal(
    patch_id="patch-1", file_path="csrc/elementwise.cu",
    diff="--- a/csrc/elementwise.cu\\n+++ b/csrc/elementwise.cu\\n@@ -1 +1 @@\\n-old\\n+new\\n",
    fingerprint_id="FP_WARP_SIZE", lines_added=1, lines_deleted=1,
    explanation="Replace the recorded architecture assumption.",
)
payloads = [
    EmptyLogData(), None,
    AnalysisLogData(cu_files=["csrc/elementwise.cu"], total_loc=80, setup_path="setup.py"),
    patch,
    BenchmarkLogData(avg_latency_ms=1.25, throughput_elements_per_sec=1024.0),
    PRLogData(title="HIP repair", body="Recorded verification results.", branch="hip-port"),
]
events = [LogEvent(job_id="job-1", timestamp=stamp, state=PipelineState.ANALYSIS,
                   message="Contract test event.", data=payload) for payload in payloads]
result = NumericalResult(seed=42, shape=[128, 64], dtype="float32",
    atol=1e-5, rtol=1e-5, max_abs_err=0.0, max_rel_err=0.0,
    mismatch_ratio=0.0, nan_inf_detected=False, passed=True)
verified = VerificationReport(job_id="job-1", overall_status="VERIFIED",
    cpu_reference_verified=True, determinism_passed=True, results=[result],
    total_tests=1, passed_tests=1, failed_tests=0,
    summary="Contract fixture with passing reference evidence.", timestamp=stamp)
failed = VerificationReport(job_id="job-1", overall_status="FAILED",
    cpu_reference_verified=False, determinism_passed=False,
    summary="Runner unavailable; no verification performed.", timestamp=stamp)
status = JobStatusResponse(job_id="job-1", current_state=PipelineState.USER_APPROVAL,
    repair_rounds_used=1, verification_report=verified)
created = JobStatusResponse(job_id="job-1", current_state=PipelineState.CREATED)
print(json.dumps({
    "states": [state.value for state in PipelineState],
    "events": [event.model_dump(mode="json") for event in events],
    "verified": verified.model_dump(mode="json"),
    "failed": failed.model_dump(mode="json"),
    "status": status.model_dump(mode="json"),
    "created": created.model_dump(mode="json"),
}))
`], { cwd: repository, encoding: "utf8", timeout: 30_000 }));

const copy = (value) => structuredClone(value);
const eventWith = (changes) => ({ ...copy(fixtures.events[0]), ...changes });
const reportWith = (changes) => ({ ...copy(fixtures.verified), ...changes });

test("the frontend state union exactly matches the Python enum", () => {
  assert.deepEqual(PIPELINE_STATES, fixtures.states);
  for (const state of fixtures.states) {
    assert.equal(parseLogEvent(eventWith({ state })).state, state);
  }
});

test("every Python LogEvent payload variant survives parsing without coercion", () => {
  for (const event of fixtures.events) assert.deepEqual(parseLogEvent(event), event);
});

test("Python status defaults and nested reports retain the complete wire shape", () => {
  assert.deepEqual(parseJobStatusResponse(fixtures.created), fixtures.created);
  assert.deepEqual(parseJobStatusResponse(fixtures.status), fixtures.status);
  assert.deepEqual(parseVerificationReport(fixtures.failed), fixtures.failed);
});

test("parsed payloads and nested numerical arrays are immutable copies", () => {
  const input = copy(fixtures.status);
  const parsed = parseJobStatusResponse(input);
  input.verification_report.results[0].shape[0] = 999;
  assert.equal(parsed.verification_report.results[0].shape[0], 128);
  for (const value of [parsed, parsed.verification_report,
    parsed.verification_report.results, parsed.verification_report.results[0],
    parsed.verification_report.results[0].shape]) {
    assert.ok(Object.isFrozen(value));
  }
  const analysis = parseLogEvent(fixtures.events[2]);
  assert.ok(Object.isFrozen(analysis.data));
  assert.ok(Object.isFrozen(analysis.data.cu_files));
});

test("a status cannot attach a different job's otherwise valid report", () => {
  const input = copy(fixtures.status);
  input.verification_report.job_id = "another-job";
  assert.throws(() => parseJobStatusResponse(input), /must match the status job_id/);
});

test("undeclared fields and mixed payload variants are rejected", () => {
  assert.throws(() => parseLogEvent(eventWith({ invented: true })), /not a declared field/);
  assert.throws(() => parseLogEvent(eventWith({ data: { unknown: "value" } })), /payload/);
  const mixed = { ...fixtures.events[2].data, ...fixtures.events[4].data };
  assert.throws(() => parseLogEvent(eventWith({ data: mixed })), /not a declared field/);
});

test("missing complete response fields are rejected instead of inferred", () => {
  const incomplete = copy(fixtures.events[0]);
  delete incomplete.data;
  assert.throws(() => parseLogEvent(incomplete), /data is required/);
  const status = copy(fixtures.created);
  delete status.repair_rounds_used;
  assert.throws(() => parseJobStatusResponse(status), /repair_rounds_used is required/);
});

test("invalid states, levels, nonobjects, and blank identifiers are rejected", () => {
  for (const invalid of [null, [], 123, "event"]) {
    assert.throws(() => parseLogEvent(invalid), /must be an object/);
  }
  assert.throws(() => parseLogEvent(eventWith({ state: "SUCCESS" })), /must be one of/);
  assert.throws(() => parseLogEvent(eventWith({ level: "DEBUG" })), /must be one of/);
  assert.throws(() => parseLogEvent(eventWith({ job_id: " \n" })), /nonblank/);
});

test("timestamps require an actual calendar date and explicit timezone", () => {
  for (const timestamp of ["2026-09-23T12:00:00", "2026-02-30T12:00:00Z",
    "2026-09-23T24:00:00Z", "0000-01-01T00:00:00Z", "not a timestamp"]) {
    assert.throws(() => parseLogEvent(eventWith({ timestamp })), /timestamp/);
  }
  assert.equal(parseLogEvent(eventWith({ timestamp: "2024-02-29T12:00:00+03:00" })).timestamp,
    "2024-02-29T12:00:00+03:00");
});

test("numeric strings, booleans, fractions, and out-of-bounds rounds are rejected", () => {
  for (const repair_rounds_used of ["1", true, 1.5, -1, 7]) {
    assert.throws(() => parseJobStatusResponse({ ...fixtures.created, repair_rounds_used }));
  }
  assert.throws(() => parseVerificationReport(reportWith({ total_tests: "1" })));
});

test("patch payloads enforce forbidden flags and the combined line budget", () => {
  for (const flag of ["modifies_dependencies", "modifies_public_api", "modifies_tests_or_tolerances"]) {
    const patch = { ...fixtures.events[3].data, [flag]: true };
    assert.throws(() => parseLogEvent(eventWith({ data: patch })), /must be false/);
  }
  const overBudget = { ...fixtures.events[3].data, lines_added: 61, lines_deleted: 60 };
  assert.throws(() => parseLogEvent(eventWith({ data: overBudget })), /120 changed lines/);
  // The schema preserves a negative allowlist assessment for the policy layer.
  const rejectedTarget = { ...fixtures.events[3].data, allowlisted: false };
  assert.equal(parseLogEvent(eventWith({ data: rejectedTarget })).data.allowlisted, false);
});

test("analysis payloads enforce scope without inventing missing files", () => {
  for (const cu_files of [[], Array(6).fill("csrc/kernel.cu"), [" "]]) {
    assert.throws(() => parseLogEvent(eventWith({ data: { ...fixtures.events[2].data, cu_files } })));
  }
  assert.throws(() => parseLogEvent(eventWith({ data: { ...fixtures.events[2].data, total_loc: 2001 } })));
});

test("VERIFIED requires CPU reference and determinism evidence", () => {
  for (const missingEvidence of ["cpu_reference_verified", "determinism_passed"]) {
    assert.throws(() => parseVerificationReport(reportWith({ [missingEvidence]: false })), /VERIFIED requires/);
  }
  assert.throws(() => parseVerificationReport({ ...fixtures.failed, overall_status: "VERIFIED" }), /VERIFIED requires/);
});

test("report counts must reflect every passing and failing result", () => {
  for (const field of ["total_tests", "passed_tests", "failed_tests"]) {
    assert.throws(() => parseVerificationReport(reportWith({ [field]: 99 })), /test counts/);
  }
  const report = copy(fixtures.verified);
  report.results[0].passed = false;
  report.passed_tests = 0;
  report.failed_tests = 1;
  assert.throws(() => parseVerificationReport(report), /VERIFIED requires/);
  report.overall_status = "FAILED";
  assert.deepEqual(parseVerificationReport(report), report);
});

test("passing results cannot conceal NaN/Inf or numerical mismatches", () => {
  for (const changes of [{ nan_inf_detected: true }, { mismatch_ratio: 0.01 }]) {
    const result = { ...fixtures.verified.results[0], ...changes };
    assert.throws(() => parseVerificationReport(reportWith({ results: [result] })), /cannot pass/);
  }
});

test("numerical evidence rejects nonfinite, negative, and imprecise numbers", () => {
  for (const changes of [{ max_abs_err: NaN }, { max_rel_err: Infinity },
    { atol: -0.1 }, { mismatch_ratio: 1.01 }, { shape: [1.5] },
    { shape: [-1] }, { seed: Number.MAX_SAFE_INTEGER + 1 }]) {
    const result = { ...fixtures.verified.results[0], ...changes };
    assert.throws(() => parseVerificationReport(reportWith({ results: [result] })));
  }
  for (const shape of [[], [0], [128, 64]]) {
    const result = { ...fixtures.verified.results[0], shape };
    assert.deepEqual(parseVerificationReport(reportWith({ results: [result] })).results[0].shape, shape);
  }
});
