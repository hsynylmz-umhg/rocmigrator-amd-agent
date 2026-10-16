"use client";

import { motion } from "motion/react";
import type { LogEvent, PipelineState } from "../lib/contracts";
import { BlurReveal } from "./ui/blur-reveal";

const stages = [
  ["CREATED", "Created"],
  ["CLONING", "Clone"],
  ["SECURITY_SCAN", "Security scan"],
  ["ANALYSIS", "Analysis"],
  ["BASELINE", "Baseline"],
  ["HIPIFICATION", "HIPIFY"],
  ["COMPILING", "Compile"],
  ["VERIFYING", "Verify"],
  ["BENCHMARKING", "Benchmark"],
  ["REPORT", "Report"],
  ["USER_APPROVAL", "User approval"],
  ["PR_CREATED", "Pull request"],
] as const satisfies readonly (readonly [PipelineState, string])[];

const stageIcons: Readonly<Record<PipelineState, (active: boolean, seen: boolean) => React.ReactNode>> = {
  CREATED: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-created" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
  CLONING: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-branch" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  ),
  SECURITY_SCAN: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-shield" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
  ANALYSIS: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-scan" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
  BASELINE: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="20" x2="6" y2="14" className={active ? "anim-bars-1" : ""} />
      <line x1="12" y1="20" x2="12" y2="4" className={active ? "anim-bars-2" : ""} />
      <line x1="18" y1="20" x2="18" y2="10" className={active ? "anim-bars-3" : ""} />
    </svg>
  ),
  HIPIFICATION: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" className={active ? "anim-chip fill-rose-500/30" : ""} />
      <line x1="9" y1="1" x2="9" y2="4" />
      <line x1="15" y1="1" x2="15" y2="4" />
      <line x1="9" y1="20" x2="9" y2="23" />
      <line x1="15" y1="20" x2="15" y2="23" />
      <line x1="20" y1="9" x2="23" y2="9" />
      <line x1="20" y1="14" x2="23" y2="14" />
      <line x1="1" y1="9" x2="4" y2="9" />
      <line x1="1" y1="14" x2="4" y2="14" />
    </svg>
  ),
  COMPILING: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-compile" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  ),
  REPAIR: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 animate-spin" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  ),
  VERIFYING: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-verify" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  ),
  BENCHMARKING: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="12" x2="16" y2="14" className={active ? "anim-gauge-hand" : ""} />
    </svg>
  ),
  REPORT: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-float" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  ),
  USER_APPROVAL: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-float" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="8.5" cy="7" r="4" />
      <polyline points="17 11 19 13 23 9" />
    </svg>
  ),
  PR_CREATED: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400 anim-branch" : seen ? "text-emerald-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="18" cy="18" r="3" />
      <circle cx="6" cy="6" r="3" />
      <path d="M13 6h3a2 2 0 0 1 2 2v7" />
      <line x1="6" y1="9" x2="6" y2="21" />
    </svg>
  ),
  ROLLED_BACK: (active, seen) => (
    <svg className={`h-4 w-4 ${active ? "text-rose-400" : seen ? "text-rose-400" : "text-brand-khaki"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1 4 1 10 7 10" />
      <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
    </svg>
  ),
};

interface StateStepperProps {
  readonly currentState: PipelineState | null;
  readonly events: readonly LogEvent[];
  readonly onApprove?: () => void;
  readonly isCompleted?: boolean;
}

export function StateStepper({ currentState, events, onApprove, isCompleted }: StateStepperProps) {
  const seen = new Set(events.map((event) => event.state));
  const repairing = currentState === "REPAIR";
  const rolledBack = currentState === "ROLLED_BACK";
  const isPrFinished =
    Boolean(isCompleted) ||
    currentState === "PR_CREATED" ||
    (seen.has("PR_CREATED") &&
      events.some((e) => e.message.toLowerCase().includes("pull request")));

  return (
    <motion.section
      initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.6, delay: 0.18, ease: [0.16, 1, 0.3, 1] }}
      aria-labelledby="pipeline-heading"
      className="card-gradient relative overflow-hidden rounded-xl border border-[#3d191e] p-5 shadow-xl sm:p-6"
    >
      {/* Header */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <BlurReveal
            as="h2"
            id="pipeline-heading"
            className="text-base font-semibold tracking-tight text-foreground"
            delay={0.15}
          >
            Migration pipeline
          </BlurReveal>
          <p className="mt-1 text-xs text-brand-khaki">
            Observed stages are marked Seen. Repair returns to compilation.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {currentState === "USER_APPROVAL" && onApprove && (
            <button
              type="button"
              onClick={onApprove}
              className="flex items-center gap-1.5 rounded-full border border-rose-500/70 bg-gradient-to-r from-rose-600 to-rose-700 px-3.5 py-1 text-xs font-bold text-white shadow-[0_0_14px_rgba(225,29,72,0.45)] transition-all hover:scale-105 hover:shadow-[0_0_20px_rgba(225,29,72,0.6)] active:scale-95"
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <span>Approve &amp; Open Pull Request</span>
            </button>
          )}
          <span
            role="status"
            className={`flex items-center gap-2 rounded-full border px-3.5 py-1 font-mono text-xs font-semibold shadow-sm transition-all duration-200 ${
              isPrFinished
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-200 shadow-[0_0_14px_rgba(16,185,129,0.35)]"
                : rolledBack
                ? "border-rose-500/50 bg-rose-500/15 text-rose-300 shadow-[0_0_12px_rgba(244,63,94,0.3)]"
                : repairing
                ? "border-amber-400/50 bg-amber-400/15 text-amber-200 shadow-[0_0_14px_rgba(251,191,36,0.35)] animate-pulse"
                : currentState
                ? "border-rose-500/50 bg-rose-500/15 text-rose-200 shadow-[0_0_14px_rgba(225,29,72,0.35)]"
                : "border-[#3d191e] bg-[#16080a] text-brand-khaki"
            }`}
          >
            {currentState && (
              <span className="relative flex h-2 w-2">
                <span
                  className={`absolute inline-flex h-full w-full animate-ping rounded-full ${
                    isPrFinished
                      ? "bg-emerald-400"
                      : repairing
                      ? "bg-amber-400"
                      : "bg-rose-500"
                  } opacity-75`}
                />
                <span
                  className={`relative inline-flex h-2 w-2 rounded-full ${
                    isPrFinished
                      ? "bg-emerald-400"
                      : repairing
                      ? "bg-amber-400"
                      : "bg-rose-500"
                  }`}
                />
              </span>
            )}
            {currentState ?? "Awaiting migration"}
          </span>
        </div>
      </div>

      {/* Visual Workflow Diagram */}
      <div className="relative">
        <ol
          aria-label="Migration stages"
          className="grid grid-cols-2 gap-2.5 min-[360px]:grid-cols-3 sm:grid-cols-4 xl:grid-cols-6"
        >
          {stages.map(([state, label], index) => {
            const isCompletedPrStage = state === "PR_CREATED" && isPrFinished;
            const active = !isCompletedPrStage && currentState === state;
            const observed = isCompletedPrStage || seen.has(state);
            const isLastInRow1 = index === 5;
            const isLastInRow2 = index === 11;

            return (
              <motion.li
                key={state}
                initial={{ opacity: 0, y: 10, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.35, delay: 0.2 + index * 0.03, ease: [0.16, 1, 0.3, 1] }}
                aria-current={active ? "step" : undefined}
                className={`group relative flex h-[88px] flex-col justify-between overflow-visible rounded-lg border p-3 transition-all duration-200 hover:-translate-y-0.5 ${
                  active
                    ? "border-rose-500 bg-[#351419] text-foreground shadow-[0_0_20px_rgba(225,29,72,0.35)] ring-1 ring-rose-500/60"
                    : observed
                    ? "border-emerald-500/35 bg-[#17201c]/50 text-foreground hover:border-emerald-500/60"
                    : "border-[#3d191e] bg-[#16080a]/60 text-brand-khaki/70 opacity-70 hover:border-rose-500/40 hover:opacity-100"
                }`}
              >
                {/* Repair loop indicator badge on 06 HIPIFY and 07 Compile */}
                {(state === "HIPIFICATION" || state === "COMPILING") && (repairing || seen.has("REPAIR")) && (
                  <span
                    aria-hidden="true"
                    className={`absolute -top-2.5 right-2 z-20 flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-mono font-bold shadow-md transition-all ${
                      repairing
                        ? "border-amber-400 bg-gradient-to-r from-amber-500/40 via-rose-600/40 to-amber-500/40 text-amber-200 animate-pulse shadow-[0_0_12px_rgba(251,191,36,0.6)]"
                        : "border-emerald-500/40 bg-emerald-950/50 text-emerald-300"
                    }`}
                  >
                    <span className="text-[10px]">↺</span>
                    <span>{repairing ? "Repair #1" : "Repaired"}</span>
                  </span>
                )}

                {/* Active or Completed top indicator */}
                <div className="mb-2 flex items-center justify-between gap-1 text-[11px]">
                  <div className="flex items-center gap-1.5 font-mono">
                    <span className="text-[10px] text-brand-khaki font-semibold">{String(index + 1).padStart(2, "0")}</span>
                    {stageIcons[state]?.(active, observed)}
                  </div>
                  <span
                    className={`flex items-center gap-1 text-[10px] font-medium ${
                      active
                        ? "text-rose-300 font-bold"
                        : observed
                        ? "text-emerald-400 font-semibold"
                        : "text-brand-khaki/70"
                    }`}
                  >
                    {active ? (
                      <>
                        <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-ping" />
                        Active
                      </>
                    ) : observed ? (
                      <>
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                        Seen
                      </>
                    ) : (
                      "Pending"
                    )}
                  </span>
                </div>

                <div className="mt-1">
                  <span className="block text-xs font-semibold tracking-tight text-foreground">{label}</span>
                </div>

                {/* Horizontal Directional Connector Arrow */}
                {!isLastInRow1 && !isLastInRow2 && (
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute -right-2 top-1/2 z-10 hidden -translate-y-1/2 translate-x-1/2 xl:block"
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 14 14"
                      fill="none"
                      className={`transition-colors ${
                        observed && seen.has(stages[index + 1][0])
                          ? "text-emerald-400"
                          : active
                          ? "text-rose-400 anim-flow"
                          : "text-[#3d191e]"
                      }`}
                    >
                      <path
                        d="M2 7h9m0 0L7.5 3.5M11 7l-3.5 3.5"
                        stroke="currentColor"
                        strokeWidth="1.75"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                )}
              </motion.li>
            );
          })}
        </ol>
      </div>

      {/* Explicit Flow & Loop Visualizer: Bounded Repair Loop & Rollback */}
      <div className="card-gradient-subtle mt-4 rounded-lg border border-[#3d191e] p-3.5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2">
            <svg
              className={`h-4 w-4 transition-colors ${
                repairing ? "text-rose-400 animate-spin" : "text-brand-khaki"
              }`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
            <span className="font-medium text-foreground">Bounded repair loop:</span>
            <span className="font-mono text-xs text-rose-300 font-semibold">07 Compile ➔ 06 HIPIFY</span>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono">
            <span
              className={`flex items-center gap-1.5 transition-colors ${
                repairing
                  ? "text-rose-400 font-bold"
                  : seen.has("REPAIR")
                  ? "text-emerald-400 font-semibold"
                  : "text-brand-khaki"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  repairing ? "bg-rose-500 animate-pulse" : seen.has("REPAIR") ? "bg-emerald-400" : "bg-[#3d191e]"
                }`}
              />
              {repairing ? "Repair Active" : seen.has("REPAIR") ? "Repairs Applied" : "Awaiting Trigger"}
            </span>

            <span className="text-brand-khaki/50">•</span>

            <span
              className={`flex items-center gap-1.5 transition-colors ${
                rolledBack ? "text-rose-400 font-bold" : "text-brand-khaki"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  rolledBack ? "bg-rose-500 animate-pulse" : "bg-[#3d191e]"
                }`}
              />
              {rolledBack ? "Rollback Executed" : "Rollback Armed (On failure)"}
            </span>
          </div>
        </div>

        {/* Dynamic SVG Animated Flow Line for the Repair Return */}
        <div aria-hidden="true" className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[#120608]">
          <div
            className={`h-full transition-all duration-500 ${
              repairing
                ? "w-full bg-gradient-to-r from-rose-600 via-pink-500 to-rose-600 anim-flow shadow-[0_0_8px_rgba(225,29,72,0.8)]"
                : seen.has("REPAIR")
                ? "w-full bg-emerald-500/50"
                : "w-0 bg-transparent"
            }`}
          />
        </div>
      </div>

      {/* Bottom Status Blocks (Strictly Preserving Required Test DOM & Tokens) */}
      <div className="mt-3 grid gap-2.5 text-xs sm:grid-cols-2">
        <div
          aria-current={repairing ? "step" : undefined}
          className={`card-gradient-subtle group flex items-center justify-between rounded-lg border px-3.5 py-2.5 transition-all duration-200 hover:border-rose-500/40 ${
            repairing
              ? "border-amber-400/60 bg-amber-400/15 text-amber-200 shadow-[0_0_12px_rgba(251,191,36,0.3)]"
              : seen.has("REPAIR")
              ? "border-emerald-500/35 text-emerald-300"
              : "border-[#3d191e] text-brand-khaki"
          }`}
        >
          <div className="flex items-center gap-2">
            <span aria-hidden="true" className="font-semibold text-rose-400">↔ </span>
            <span className="font-medium text-foreground">Repair loop</span>
          </div>
          <span className="font-mono text-[11px] font-semibold">
            {repairing ? "Active" : seen.has("REPAIR") ? "Seen" : "If required"}
          </span>
        </div>

        <div
          aria-current={rolledBack ? "step" : undefined}
          className={`card-gradient-subtle group flex items-center justify-between rounded-lg border px-3.5 py-2.5 transition-all duration-200 hover:border-rose-500/40 ${
            rolledBack
              ? "border-rose-500/60 bg-rose-500/15 text-rose-200 shadow-[0_0_12px_rgba(244,63,94,0.3)]"
              : "border-[#3d191e] text-brand-khaki"
          }`}
        >
          <div className="flex items-center gap-2">
            <svg className="h-3.5 w-3.5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
              <line x1="12" y1="2" x2="12" y2="12" />
            </svg>
            <span className="font-medium text-foreground">Rollback</span>
          </div>
          <span className="font-mono text-[11px] font-semibold">
            {rolledBack ? "Stopped" : "On failure"}
          </span>
        </div>
      </div>
    </motion.section>
  );
}
