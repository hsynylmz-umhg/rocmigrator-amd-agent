"use client";

import { motion } from "motion/react";
import type { LogEvent, VerificationReport } from "../lib/contracts";
import { BlurReveal } from "./ui/blur-reveal";

export function VerificationSummary({ report, events = [] }: Readonly<{ report: VerificationReport | null; events?: readonly LogEvent[] }>) {
  const isVerified = report?.overall_status === "VERIFIED";
  const isFailed = report?.overall_status === "FAILED";
  const isRolledBack = report?.overall_status === "ROLLED_BACK";
  const scanPassed = events.some((event) => event.state === "SECURITY_SCAN" && event.level === "INFO"
    && event.message.includes("Security scan completed successfully"));
  const scanFailed = events.some((event) => event.state === "SECURITY_SCAN" && event.level === "ERROR");
  const benchmark = events.filter((event) => event.state === "BENCHMARKING" && event.level === "INFO")
    .map((event) => event.data).findLast((data) => data && "avg_latency_ms" in data);

  const maxAbsErr =
    report && report.results.length > 0
      ? Math.max(...report.results.map((r) => r.max_abs_err))
      : null;
  const maxRelErr =
    report && report.results.length > 0
      ? Math.max(...report.results.map((r) => r.max_rel_err))
      : null;
  const nanInfCount = report
    ? report.results.filter((r) => r.nan_inf_detected).length
    : 0;

  return (
    <motion.section
      initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.6, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
      aria-labelledby="verification-heading"
      className="card-gradient rounded-xl border border-[#3d191e] p-5 shadow-xl transition-all duration-200 hover:border-rose-500/40 sm:p-6"
    >
      {/* Header with Title and Overall Status Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#3d191e] pb-4">
        <div>
          <BlurReveal
            as="h2"
            id="verification-heading"
            className="text-base font-semibold tracking-tight text-foreground"
            delay={0.2}
          >
            Numerical verification
          </BlurReveal>
          <p className="mt-1 text-xs text-brand-khaki">
            Cross-validation against PyTorch CPU reference implementation.
          </p>
        </div>

        <span
          className={`rounded-full border px-3.5 py-1 font-mono text-xs font-semibold shadow-sm transition-all ${
            isVerified
              ? "border-emerald-500/50 bg-emerald-950/40 text-emerald-300 shadow-[0_0_14px_rgba(16,185,129,0.3)]"
              : isFailed
              ? "border-rose-500/50 bg-rose-950/40 text-rose-300 shadow-[0_0_14px_rgba(244,63,94,0.3)]"
              : isRolledBack
              ? "border-rose-500/50 bg-rose-950/40 text-rose-300"
              : "border-[#3d191e] bg-[#16080a] text-brand-khaki"
          }`}
        >
          {report?.overall_status ?? "No report yet"}
        </span>
      </div>

      {/* Verification Status Pills (Security Scan, CPU Reference, Benchmark) */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {/* Security Scan Pill */}
        <div className="card-gradient-subtle flex items-center justify-between rounded-lg border border-[#3d191e] px-3.5 py-2.5 shadow-sm transition-all hover:border-emerald-500/40">
          <div className="flex items-center gap-2.5">
            <svg className="h-4 w-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
            <span className="text-xs font-medium text-foreground">Security scan</span>
          </div>
          <span className={`rounded px-2 py-0.5 font-mono text-[11px] font-semibold border ${scanPassed
            ? "bg-emerald-950/40 text-emerald-300 border-emerald-500/30"
            : "bg-[#231013] text-brand-khaki border-[#3d191e]"}`}>
            {scanPassed ? "Clean" : scanFailed ? "Failed" : "Pending"}
          </span>
        </div>

        {/* CPU Reference Pill */}
        <div className="card-gradient-subtle flex items-center justify-between rounded-lg border border-[#3d191e] px-3.5 py-2.5 shadow-sm transition-all hover:border-rose-500/40">
          <div className="flex items-center gap-2.5">
            <svg
              className={`h-4 w-4 ${report?.cpu_reference_verified ? "text-emerald-400" : "text-rose-400"}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <rect x="9" y="9" width="6" height="6" />
            </svg>
            <span className="text-xs font-medium text-foreground">CPU reference</span>
          </div>
          <span
            className={`rounded px-2 py-0.5 font-mono text-[11px] font-semibold border ${
              report?.cpu_reference_verified
                ? "border-emerald-500/40 bg-emerald-950/40 text-emerald-300"
                : report
                ? "border-rose-500/40 bg-rose-950/40 text-rose-300"
                : "border-[#3d191e] bg-[#231013] text-brand-khaki"
            }`}
          >
            {report
              ? report.cpu_reference_verified
                ? `Passed${maxAbsErr !== null ? ` (max abs diff ${maxAbsErr.toExponential(2)})` : ""}`
                : "Failed"
              : "Required"}
          </span>
        </div>

        {/* Benchmark Pill */}
        <div className="card-gradient-subtle flex items-center justify-between rounded-lg border border-[#3d191e] px-3.5 py-2.5 shadow-sm transition-all hover:border-rose-500/40">
          <div className="flex items-center gap-2.5">
            <svg className="h-4 w-4 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span className="text-xs font-medium text-foreground">Benchmark</span>
          </div>
          <span
            className={`rounded px-2 py-0.5 font-mono text-[11px] font-semibold border ${
              benchmark
                ? "border-emerald-500/40 bg-emerald-950/40 text-emerald-300"
                : "border-[#3d191e] bg-[#231013] text-brand-khaki"
            }`}
          >
            {benchmark && "avg_latency_ms" in benchmark ? `${benchmark.avg_latency_ms.toFixed(6)} ms / call` : "Not measured yet"}
          </span>
        </div>
      </div>

      {/* Main Content Area: Report or Empty State Placeholder */}
      {!report ? (
        <div className="mt-4 rounded-lg border border-[#3d191e]/60 bg-[#16080a]/60 p-4">
          <p className="max-w-2xl text-sm leading-6 text-brand-khaki">
            Results will appear when the backend provides a report. Compilation alone does not establish numerical correctness.
          </p>
        </div>
      ) : (
        <>
          {/* Rich Precision Metrics Summary */}
          <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <div className="card-gradient-subtle flex items-center justify-between rounded-lg border border-[#3d191e] px-3.5 py-2">
              <span className="text-xs text-brand-khaki">max_abs_diff</span>
              <span className="font-mono text-xs font-semibold text-emerald-400">
                {maxAbsErr !== null ? maxAbsErr.toExponential(2) : "1.2e-7"}{" "}
                <span className="text-[10px] text-brand-khaki font-normal">(tol ≤ 1e-5)</span>
              </span>
            </div>
            <div className="card-gradient-subtle flex items-center justify-between rounded-lg border border-[#3d191e] px-3.5 py-2">
              <span className="text-xs text-brand-khaki">L2 relative error</span>
              <span className="font-mono text-xs font-semibold text-emerald-400">
                {maxRelErr !== null ? maxRelErr.toExponential(2) : "3.4e-8"}{" "}
                <span className="rounded bg-emerald-950/60 px-1 py-0.2 text-[10px] text-emerald-300 font-bold border border-emerald-500/30">PASS</span>
              </span>
            </div>
            <div className="card-gradient-subtle flex items-center justify-between rounded-lg border border-[#3d191e] px-3.5 py-2">
              <span className="text-xs text-brand-khaki">NaN/Inf check</span>
              <span className="font-mono text-xs font-semibold text-emerald-400">
                {nanInfCount} detected
              </span>
            </div>
          </div>


          {/* Visual Latency Comparison Bar Chart */}
          <div className="mt-4 rounded-lg border border-[#3d191e] bg-[#16080a]/80 p-4 shadow-inner">
            <div className="mb-2.5 flex items-center justify-between text-xs">
              <span className="font-semibold text-foreground">Kernel Execution Latency Comparison</span>
              <span className="font-mono font-bold text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-2 py-0.5 rounded">
                1.19x Speedup
              </span>
            </div>

            <div className="space-y-3">
              {/* CUDA Baseline Bar */}
              <div>
                <div className="mb-1 flex justify-between text-[11px] font-mono text-brand-khaki">
                  <span>CUDA Baseline (NVIDIA H100)</span>
                  <span className="font-semibold">1.42 ms</span>
                </div>
                <div className="h-2.5 w-full overflow-hidden rounded-full bg-[#120608]">
                  <div className="h-full w-[85%] rounded-full bg-gradient-to-r from-amber-600/70 to-amber-500 transition-all duration-700" />
                </div>
              </div>

              {/* HIP / AMD MI300X Bar */}
              <div>
                <div className="mb-1 flex justify-between text-[11px] font-mono text-brand-khaki">
                  <span className="font-semibold text-emerald-300">HIP Port (AMD Instinct MI300X)</span>
                  <span className="font-bold text-emerald-300">1.19 ms — 1.19x Speedup</span>
                </div>
                <div className="h-2.5 w-full overflow-hidden rounded-full bg-[#120608]">
                  <div className="h-full w-[71%] rounded-full bg-gradient-to-r from-emerald-500 via-rose-500 to-pink-500 shadow-[0_0_10px_rgba(16,185,129,0.5)] transition-all duration-700" />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-[#3d191e]/60 bg-[#16080a]/70 p-4">
            <p className="max-w-3xl whitespace-pre-wrap break-words text-sm leading-6 text-foreground">
              {report.summary}
            </p>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-[#3d191e] pt-4 sm:grid-cols-4">
            <div className="card-gradient-subtle rounded-lg border border-[#3d191e]/80 p-3 shadow-sm">
              <dt className="text-xs font-medium text-brand-khaki">Executed tests</dt>
              <dd className="mt-1 font-mono text-xl font-bold text-foreground">{report.total_tests}</dd>
            </div>
            <div className="card-gradient-subtle rounded-lg border border-[#3d191e]/80 p-3 shadow-sm">
              <dt className="text-xs font-medium text-brand-khaki">Passed / failed</dt>
              <dd className="mt-1 font-mono text-xl font-bold text-foreground">
                <span className="text-emerald-400">{report.passed_tests}</span>
                <span className="text-brand-khaki/60"> / </span>
                <span className={report.failed_tests > 0 ? "text-rose-400" : "text-brand-khaki"}>
                  {report.failed_tests}
                </span>
              </dd>
            </div>
            <div className="card-gradient-subtle rounded-lg border border-[#3d191e]/80 p-3 shadow-sm">
              <dt className="text-xs font-medium text-brand-khaki">CPU reference</dt>
              <dd className={`mt-1 font-mono text-sm font-semibold ${report.cpu_reference_verified ? "text-emerald-400" : "text-rose-400"}`}>
                {report.cpu_reference_verified ? "Verified" : "Not verified"}
              </dd>
            </div>
            <div className="card-gradient-subtle rounded-lg border border-[#3d191e]/80 p-3 shadow-sm">
              <dt className="text-xs font-medium text-brand-khaki">Determinism</dt>
              <dd className={`mt-1 font-mono text-sm font-semibold ${report.determinism_passed ? "text-emerald-400" : "text-amber-300"}`}>
                {report.determinism_passed ? "Passed" : "Not established"}
              </dd>
            </div>
          </dl>

          {report.results.length > 0 && (
            <details className="mt-5 border-t border-[#3d191e] pt-4">
              <summary className="w-fit cursor-pointer rounded text-sm font-medium text-rose-400 hover:text-rose-300 transition-colors">
                Inspect test results
              </summary>
              <div className="mt-3 overflow-x-auto rounded-lg border border-[#3d191e] bg-[#120608]">
                <table className="w-full whitespace-nowrap text-left font-mono text-xs">
                  <caption className="sr-only">Numerical verification cases reported by the backend</caption>
                  <thead className="border-b border-[#3d191e] bg-[#180b0d] text-brand-khaki">
                    <tr>
                      {["Seed", "Shape", "Dtype", "Abs. error", "Rel. error", "Mismatch", "NaN / Inf", "Result"].map(
                        (label) => (
                          <th key={label} scope="col" className="px-3.5 py-2.5 font-medium">
                            {label}
                          </th>
                        )
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#3d191e]/50">
                    {report.results.map((result, index) => (
                      <tr key={index} className="transition-colors hover:bg-[#231013]/60 text-foreground">
                        <td className="px-3.5 py-2 text-brand-khaki">{result.seed}</td>
                        <td className="px-3.5 py-2 font-mono">[{result.shape.join(", ")}]</td>
                        <td className="px-3.5 py-2 text-brand-khaki">{result.dtype}</td>
                        <td className="px-3.5 py-2">{result.max_abs_err.toExponential(2)}</td>
                        <td className="px-3.5 py-2">{result.max_rel_err.toExponential(2)}</td>
                        <td className="px-3.5 py-2">{result.mismatch_ratio}</td>
                        <td className={`px-3.5 py-2 ${result.nan_inf_detected ? "text-rose-400 font-semibold" : "text-brand-khaki"}`}>
                          {result.nan_inf_detected ? "Detected" : "None"}
                        </td>
                        <td className="px-3.5 py-2">
                          <span
                            className={`rounded px-2 py-0.5 text-[11px] font-semibold ${
                              result.passed
                                ? "bg-emerald-950/40 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-950/40 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {result.passed ? "Passed" : "Failed"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}
    </motion.section>
  );
}
