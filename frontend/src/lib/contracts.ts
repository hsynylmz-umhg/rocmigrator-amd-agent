/** JSON wire contracts mirrored from the strict Pydantic models in contracts/. */
export const PIPELINE_STATES = [
  "CREATED",
  "CLONING",
  "SECURITY_SCAN",
  "ANALYSIS",
  "BASELINE",
  "HIPIFICATION",
  "COMPILING",
  "REPAIR",
  "VERIFYING",
  "BENCHMARKING",
  "REPORT",
  "USER_APPROVAL",
  "PR_CREATED",
  "ROLLED_BACK",
] as const;

export type PipelineState = (typeof PIPELINE_STATES)[number];
export type LogLevel = "INFO" | "WARNING" | "ERROR" | "STEP";
export type EmptyLogData = Readonly<Record<string, never>>;

export interface AnalysisLogData {
  readonly cu_files: readonly string[];
  readonly total_loc: number;
  readonly setup_path: string;
}

export interface PatchProposal {
  readonly patch_id: string;
  readonly file_path: string;
  readonly diff: string;
  readonly fingerprint_id: string | null;
  readonly lines_added: number;
  readonly lines_deleted: number;
  readonly explanation: string;
  readonly allowlisted: boolean;
  readonly modifies_dependencies: false;
  readonly modifies_public_api: false;
  readonly modifies_tests_or_tolerances: false;
}

export interface BenchmarkLogData {
  readonly avg_latency_ms: number;
  readonly throughput_elements_per_sec: number;
}

export interface PRLogData {
  readonly title: string;
  readonly body: string;
  readonly branch: string;
}

export type LogData =
  | EmptyLogData
  | AnalysisLogData
  | PatchProposal
  | BenchmarkLogData
  | PRLogData
  | null;

export interface LogEvent {
  readonly job_id: string;
  readonly timestamp: string;
  readonly level: LogLevel;
  readonly state: PipelineState;
  readonly message: string;
  readonly data: LogData;
}

export interface JobCreateRequest {
  readonly repo_path: string;
  readonly target_branch: string;
  readonly max_repair_rounds: number;
}

export interface NumericalResult {
  readonly seed: number;
  readonly shape: readonly number[];
  readonly dtype: string;
  readonly atol: number;
  readonly rtol: number;
  readonly max_abs_err: number;
  readonly max_rel_err: number;
  readonly mismatch_ratio: number;
  readonly nan_inf_detected: boolean;
  readonly passed: boolean;
}

export interface VerificationReport {
  readonly job_id: string;
  readonly overall_status: "VERIFIED" | "FAILED" | "ROLLED_BACK";
  readonly cpu_reference_verified: boolean;
  readonly determinism_passed: boolean;
  readonly results: readonly NumericalResult[];
  readonly total_tests: number;
  readonly passed_tests: number;
  readonly failed_tests: number;
  readonly summary: string;
  readonly timestamp: string;
}

export interface JobStatusResponse {
  readonly job_id: string;
  readonly current_state: PipelineState;
  readonly repair_rounds_used: number;
  readonly best_known_commit: string | null;
  readonly verification_report: VerificationReport | null;
}

type JsonObject = Readonly<Record<string, unknown>>;

function fail(path: string, expectation: string): never {
  throw new Error(`Invalid API data: ${path} ${expectation}.`);
}

function object(value: unknown, path: string): JsonObject {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return fail(path, "must be an object");
  }
  return value as JsonObject;
}

/** Backend responses use complete model_dump_json output, including defaults. */
function fields(value: JsonObject, keys: readonly string[], path: string): void {
  for (const key of Object.keys(value)) {
    if (!keys.includes(key)) fail(`${path}.${key}`, "is not a declared field");
  }
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      fail(`${path}.${key}`, "is required");
    }
  }
}

function text(value: unknown, path: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    return fail(path, "must be a nonblank string");
  }
  return value;
}

function nullableText(value: unknown, path: string): string | null {
  return value === null ? null : text(value, path);
}

function bool(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return fail(path, "must be a boolean");
  return value;
}

function forbiddenFlag(value: unknown, path: string): false {
  if (value !== false) return fail(path, "must be false");
  return false;
}

function number(value: unknown, path: string, minimum = 0, maximum = Infinity): number {
  if (
    typeof value !== "number" || !Number.isFinite(value) ||
    value < minimum || value > maximum
  ) {
    return fail(path, `must be a finite number between ${minimum} and ${maximum}`);
  }
  return value;
}

function integer(value: unknown, path: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number {
  const result = number(value, path, minimum, maximum);
  // JSON numbers outside this range cannot preserve exact Python integer values.
  if (!Number.isSafeInteger(result)) return fail(path, "must be a safe integer");
  return result;
}

function array(value: unknown, path: string): readonly unknown[] {
  if (!Array.isArray(value)) return fail(path, "must be an array");
  return value;
}

function choice<const T extends readonly string[]>(value: unknown, choices: T, path: string): T[number] {
  if (typeof value !== "string" || !choices.includes(value)) {
    return fail(path, `must be one of ${choices.join(", ")}`);
  }
  return value as T[number];
}

function timestamp(value: unknown, path: string): string {
  const result = text(value, path);
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(result);
  if (!match || !Number.isFinite(Date.parse(result))) {
    return fail(path, "must be an ISO 8601 timestamp with a timezone offset");
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthDays = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1 || month < 1 || month > 12 || day < 1 || day > monthDays[month - 1] ||
    Number(match[4]) > 23 || Number(match[5]) > 59 || Number(match[6]) > 59
  ) {
    return fail(path, "must contain a valid calendar date and time");
  }
  return result;
}

function parsePatch(value: JsonObject, path: string): PatchProposal {
  fields(value, [
    "patch_id", "file_path", "diff", "fingerprint_id", "lines_added", "lines_deleted",
    "explanation", "allowlisted", "modifies_dependencies", "modifies_public_api",
    "modifies_tests_or_tolerances",
  ], path);
  const patch: PatchProposal = {
    patch_id: text(value.patch_id, `${path}.patch_id`),
    file_path: text(value.file_path, `${path}.file_path`),
    diff: text(value.diff, `${path}.diff`),
    fingerprint_id: nullableText(value.fingerprint_id, `${path}.fingerprint_id`),
    lines_added: integer(value.lines_added, `${path}.lines_added`, 0, 120),
    lines_deleted: integer(value.lines_deleted, `${path}.lines_deleted`, 0, 120),
    explanation: text(value.explanation, `${path}.explanation`),
    allowlisted: bool(value.allowlisted, `${path}.allowlisted`),
    modifies_dependencies: forbiddenFlag(value.modifies_dependencies, `${path}.modifies_dependencies`),
    modifies_public_api: forbiddenFlag(value.modifies_public_api, `${path}.modifies_public_api`),
    modifies_tests_or_tolerances: forbiddenFlag(value.modifies_tests_or_tolerances, `${path}.modifies_tests_or_tolerances`),
  };
  if (patch.lines_added + patch.lines_deleted > 120) {
    fail(path, "must not exceed 120 changed lines");
  }
  return Object.freeze(patch);
}

function parseLogData(value: unknown, path: string): LogData {
  if (value === null) return null;
  const data = object(value, path);
  if (Object.keys(data).length === 0) return Object.freeze({});
  if ("cu_files" in data) {
    fields(data, ["cu_files", "total_loc", "setup_path"], path);
    const cuFiles = array(data.cu_files, `${path}.cu_files`).map((file, index) =>
      text(file, `${path}.cu_files[${index}]`),
    );
    if (cuFiles.length < 1 || cuFiles.length > 5) {
      fail(`${path}.cu_files`, "must contain between 1 and 5 paths");
    }
    return Object.freeze({
      cu_files: Object.freeze(cuFiles),
      total_loc: integer(data.total_loc, `${path}.total_loc`, 0, 2000),
      setup_path: text(data.setup_path, `${path}.setup_path`),
    });
  }
  if ("patch_id" in data) return parsePatch(data, path);
  if ("avg_latency_ms" in data) {
    fields(data, ["avg_latency_ms", "throughput_elements_per_sec"], path);
    return Object.freeze({
      avg_latency_ms: number(data.avg_latency_ms, `${path}.avg_latency_ms`),
      throughput_elements_per_sec: number(data.throughput_elements_per_sec, `${path}.throughput_elements_per_sec`),
    });
  }
  if ("title" in data) {
    fields(data, ["title", "body", "branch"], path);
    return Object.freeze({
      title: text(data.title, `${path}.title`),
      body: text(data.body, `${path}.body`),
      branch: text(data.branch, `${path}.branch`),
    });
  }
  return fail(path, "must be an empty, analysis, patch, benchmark, or pull request payload");
}

/** Validate every SSE event before it can change the dashboard's displayed state. */
export function parseLogEvent(value: unknown): LogEvent {
  const path = "LogEvent";
  const event = object(value, path);
  fields(event, ["job_id", "timestamp", "level", "state", "message", "data"], path);
  return Object.freeze({
    job_id: text(event.job_id, `${path}.job_id`),
    timestamp: timestamp(event.timestamp, `${path}.timestamp`),
    level: choice(event.level, ["INFO", "WARNING", "ERROR", "STEP"], `${path}.level`),
    state: choice(event.state, PIPELINE_STATES, `${path}.state`),
    message: text(event.message, `${path}.message`),
    data: parseLogData(event.data, `${path}.data`),
  });
}

function parseNumericalResult(value: unknown, path: string): NumericalResult {
  const result = object(value, path);
  fields(result, [
    "seed", "shape", "dtype", "atol", "rtol", "max_abs_err", "max_rel_err",
    "mismatch_ratio", "nan_inf_detected", "passed",
  ], path);
  const parsed: NumericalResult = {
    seed: integer(result.seed, `${path}.seed`, Number.MIN_SAFE_INTEGER),
    shape: Object.freeze(array(result.shape, `${path}.shape`).map((dimension, index) =>
      integer(dimension, `${path}.shape[${index}]`),
    )),
    dtype: text(result.dtype, `${path}.dtype`),
    atol: number(result.atol, `${path}.atol`),
    rtol: number(result.rtol, `${path}.rtol`),
    max_abs_err: number(result.max_abs_err, `${path}.max_abs_err`),
    max_rel_err: number(result.max_rel_err, `${path}.max_rel_err`),
    mismatch_ratio: number(result.mismatch_ratio, `${path}.mismatch_ratio`, 0, 1),
    nan_inf_detected: bool(result.nan_inf_detected, `${path}.nan_inf_detected`),
    passed: bool(result.passed, `${path}.passed`),
  };
  if (parsed.passed && (parsed.nan_inf_detected || parsed.mismatch_ratio !== 0)) {
    fail(path, "cannot pass with mismatches or NaN/Inf");
  }
  return Object.freeze(parsed);
}

export function parseVerificationReport(value: unknown): VerificationReport {
  const path = "VerificationReport";
  const report = object(value, path);
  fields(report, [
    "job_id", "overall_status", "cpu_reference_verified", "determinism_passed",
    "results", "total_tests", "passed_tests", "failed_tests", "summary", "timestamp",
  ], path);
  const parsed: VerificationReport = {
    job_id: text(report.job_id, `${path}.job_id`),
    overall_status: choice(report.overall_status, ["VERIFIED", "FAILED", "ROLLED_BACK"], `${path}.overall_status`),
    cpu_reference_verified: bool(report.cpu_reference_verified, `${path}.cpu_reference_verified`),
    determinism_passed: bool(report.determinism_passed, `${path}.determinism_passed`),
    results: Object.freeze(array(report.results, `${path}.results`).map((result, index) =>
      parseNumericalResult(result, `${path}.results[${index}]`),
    )),
    total_tests: integer(report.total_tests, `${path}.total_tests`),
    passed_tests: integer(report.passed_tests, `${path}.passed_tests`),
    failed_tests: integer(report.failed_tests, `${path}.failed_tests`),
    summary: text(report.summary, `${path}.summary`),
    timestamp: timestamp(report.timestamp, `${path}.timestamp`),
  };
  const passed = parsed.results.filter((result) => result.passed).length;
  if (
    parsed.total_tests !== parsed.results.length || parsed.passed_tests !== passed ||
    parsed.failed_tests !== parsed.results.length - passed
  ) {
    fail(path, "test counts must exactly match its numerical results");
  }
  if (parsed.overall_status === "VERIFIED" && (
    !parsed.cpu_reference_verified || !parsed.determinism_passed ||
    parsed.results.length === 0 || parsed.failed_tests !== 0
  )) {
    fail(path, "VERIFIED requires CPU reference, determinism, and nonempty passing results");
  }
  return Object.freeze(parsed);
}

export function parseJobStatusResponse(value: unknown): JobStatusResponse {
  const path = "JobStatusResponse";
  const status = object(value, path);
  fields(status, [
    "job_id", "current_state", "repair_rounds_used", "best_known_commit", "verification_report",
  ], path);
  const parsed: JobStatusResponse = {
    job_id: text(status.job_id, `${path}.job_id`),
    current_state: choice(status.current_state, PIPELINE_STATES, `${path}.current_state`),
    repair_rounds_used: integer(status.repair_rounds_used, `${path}.repair_rounds_used`, 0, 6),
    best_known_commit: nullableText(status.best_known_commit, `${path}.best_known_commit`),
    verification_report: status.verification_report === null
      ? null
      : parseVerificationReport(status.verification_report),
  };
  if (parsed.verification_report && parsed.verification_report.job_id !== parsed.job_id) {
    fail(`${path}.verification_report.job_id`, "must match the status job_id");
  }
  return Object.freeze(parsed);
}
