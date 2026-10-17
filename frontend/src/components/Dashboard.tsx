"use client";

import { useCallback, useRef, useState, type FormEvent } from "react";
import { motion } from "motion/react";
import { useMigration } from "../hooks/useMigration";
import { LogTerminal } from "./LogTerminal";
import { Navbar } from "./Navbar";
import { StateStepper } from "./StateStepper";
import { VerificationSummary } from "./VerificationSummary";
import { BlurReveal } from "./ui/blur-reveal";

const inputClass =
  "w-full rounded-lg border border-[#3d191e] bg-[#120608] px-3.5 py-2.5 text-sm text-foreground placeholder:text-brand-khaki/50 shadow-inner transition-all duration-200 outline-none focus:outline-none focus-visible:outline-none focus:border-rose-500/60 focus:ring-2 focus:ring-rose-500/20 focus:bg-[#1a0a0d] disabled:opacity-50";

export function Dashboard() {
  const migration = useMigration();

  const [repoPath, setRepoPath] = useState("fixtures/golden-repo-01");
  const [branch, setBranch] = useState("hip-port");
  const [repairLimit, setRepairLimit] = useState(3);
  const [formError, setFormError] = useState<string | null>(null);

  const folderInputRef = useRef<HTMLInputElement>(null);

  const isDisconnected = migration.connection !== "connected";
  const locked = migration.submitting || migration.busy;

  const isMigrationActiveOrFinished = Boolean(
    migration.job ||
    migration.currentState ||
    migration.submitting ||
    migration.busy
  );

  const handleReset = useCallback(() => {
    migration.resetWorkspace();
  }, [migration]);

  const handleApprove = useCallback(() => {
    void migration.approveMigration();
  }, [migration]);

  const handleRepoPathChange = (val: string) => {
    setRepoPath(val);
    if (!migration.busy && isMigrationActiveOrFinished) {
      handleReset();
    }
  };

  const handleBranchChange = (val: string) => {
    setBranch(val);
    if (!migration.busy && isMigrationActiveOrFinished) {
      handleReset();
    }
  };

  const handleRepairLimitChange = (val: number) => {
    setRepairLimit(val);
    if (!migration.busy && isMigrationActiveOrFinished) {
      handleReset();
    }
  };

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!repoPath.trim() || !branch.trim()) {
      setFormError("Enter a repository path and target branch. Both must contain text.");
      return;
    }
    setFormError(null);
    void migration.start({ repo_path: repoPath, target_branch: branch, max_repair_rounds: repairLimit });
  }

  const handleBrowseFolder = async () => {
    if (typeof window !== "undefined" && "showDirectoryPicker" in window) {
      try {
        // @ts-expect-error Standard modern File System Access API
        const dirHandle = await window.showDirectoryPicker();
        if (dirHandle?.name) {
          handleRepoPathChange(dirHandle.name);
          return;
        }
      } catch {
        // Fallback to hidden file input on cancel or browser restriction
      }
    }
    folderInputRef.current?.click();
  };

  return (
    <div className="relative min-h-screen bg-[#110708] text-foreground antialiased selection:bg-rose-950 selection:text-rose-200">
      {/* Slow-moving ambient background gradient layer */}
      <div aria-hidden="true" className="fixed inset-0 -z-10 pointer-events-none overflow-hidden bg-[#110708]">
        <div className="absolute -top-[15%] left-[10%] h-[550px] w-[550px] rounded-full bg-rose-600/12 blur-[130px] anim-orb-1" />
        <div className="absolute top-[35%] -right-[10%] h-[600px] w-[600px] rounded-full bg-rose-500/8 blur-[140px] anim-orb-2" />
        <div className="absolute -bottom-[15%] left-[25%] h-[500px] w-[500px] rounded-full bg-[#881337]/14 blur-[130px] anim-orb-3" />
        <div className="absolute inset-0 ambient-grid-pattern opacity-[0.035]" />
      </div>

      <a
        href="#workspace"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-rose-900 focus:p-3 focus:text-foreground focus:shadow-lg"
      >
        Skip to migration workspace
      </a>

      {/* Hidden native directory picker for cross-browser fallback */}
      <input
        ref={folderInputRef}
        type="file"
        // @ts-expect-error webkitdirectory is standard for folder picking
        webkitdirectory=""
        directory=""
        className="hidden"
        onChange={(e) => {
          const files = e.target.files;
          if (files && files.length > 0) {
            const rel = files[0].webkitRelativePath;
            const folderName = rel.split("/")[0] || rel.split("\\")[0];
            handleRepoPathChange(folderName || files[0].name);
          }
        }}
      />

      {/* Clean full-width top header */}
      <motion.div
        initial={{ opacity: 0, y: -10, filter: "blur(6px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <Navbar
          currentState={migration.currentState}
          isBusy={migration.busy}
          connection={migration.connection}
        />
      </motion.div>

      <main id="workspace" className="mx-auto w-full max-w-[1480px] px-5 pb-12 pt-8 sm:px-8 lg:px-10">
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.6, delay: 0.05, ease: [0.16, 1, 0.3, 1] }}
          className="mb-8 flex flex-wrap items-end justify-between gap-4"
        >
          <div>
            <BlurReveal
              as="h1"
              className="text-3xl font-bold tracking-tight text-foreground sm:text-[34px]"
              delay={0.05}
            >
              Bring your kernels to ROCm.
            </BlurReveal>
            <BlurReveal
              as="p"
              className="mt-2.5 max-w-2xl text-sm leading-6 text-brand-khaki"
              delay={0.15}
            >
              Start a bounded CUDA-to-HIP migration. Follow the repairs and inspect the evidence.
            </BlurReveal>
          </div>
          <p className="flex items-center gap-2 rounded-full border border-[#3d191e] bg-[#16080a] px-3.5 py-1.5 text-xs text-brand-khaki shadow-sm">
            <span aria-hidden="true" className="h-2 w-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(225,29,72,0.8)]" />
            Explicit approval before a pull request
          </p>
        </motion.div>

        <div className="grid items-start gap-6 lg:grid-cols-[310px_minmax(0,1fr)] xl:grid-cols-[330px_minmax(0,1fr)]">
          {/* Left Column: Form & Scope Reference */}
          <motion.aside
            initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.6, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-6"
            aria-label="Migration configuration"
          >
            <section
              className="card-gradient overflow-hidden rounded-xl border border-[#3d191e] shadow-xl transition-all duration-200 hover:border-rose-500/40"
              aria-labelledby="new-migration-heading"
            >
              <div className="border-b border-[#3d191e] bg-[#16080a] px-5 py-4">
                <div className="flex items-center justify-between">
                  <BlurReveal
                    as="h2"
                    id="new-migration-heading"
                    className="text-base font-semibold tracking-tight text-foreground"
                    delay={0.1}
                  >
                    New migration
                  </BlurReveal>
                </div>
                <p className="mt-1 text-xs leading-5 text-brand-khaki">
                  Configure the repository and repair budget.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5 p-5">
                {/* Repository Path with Browse Button */}
                <div>
                  <div className="flex items-center justify-between">
                    <label htmlFor="repo-path" className="text-sm font-medium text-foreground">
                      Repository path
                    </label>
                  </div>

                  <div className="mt-2 flex items-center gap-1.5">
                    <input
                      id="repo-path"
                      name="repo_path"
                      value={repoPath}
                      onChange={(event) => handleRepoPathChange(event.target.value)}
                      required
                      disabled={locked}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="fixtures/golden-repo-01"
                      aria-describedby="repo-help"
                      className="w-full min-w-0 rounded-lg border border-[#3d191e] bg-[#120608] px-3 py-2 text-xs font-mono text-foreground placeholder:text-brand-khaki/50 shadow-inner transition-all duration-200 outline-none focus:outline-none focus-visible:outline-none focus:border-rose-500/60 focus:ring-2 focus:ring-rose-500/20 focus:bg-[#1a0a0d] disabled:opacity-50 sm:text-[13px]"
                    />
                    <button
                      type="button"
                      onClick={handleBrowseFolder}
                      disabled={locked}
                      title="Browse local directory"
                      className="shrink-0 flex items-center gap-1 rounded-lg border border-[#3d191e] bg-[#1f0c10] px-2.5 py-2 text-xs font-semibold text-rose-300 transition-all hover:border-rose-500 hover:bg-[#2c1218] hover:text-rose-100 disabled:opacity-50 outline-none focus:outline-none focus-visible:outline-none focus:ring-2 focus:ring-rose-500/30"
                    >
                      <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                      </svg>
                      <span>Browse</span>
                    </button>
                  </div>

                  <p id="repo-help" className="mt-2 text-xs leading-5 text-brand-khaki">
                    Use a repository path accessible to the backend.
                  </p>
                </div>

                <div>
                  <label htmlFor="target-branch" className="text-sm font-medium text-foreground">
                    Target branch
                  </label>
                  <input
                    id="target-branch"
                    name="target_branch"
                    value={branch}
                    onChange={(event) => handleBranchChange(event.target.value)}
                    required
                    disabled={locked}
                    autoComplete="off"
                    spellCheck={false}
                    className={`mt-2 ${inputClass} font-mono`}
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between">
                    <label htmlFor="repair-limit" className="text-sm font-medium text-foreground">
                      Maximum repair rounds
                    </label>
                    <span className="font-mono text-xs font-semibold text-rose-300">
                      {repairLimit} {repairLimit === 1 ? "round" : "rounds"}
                      <span className="ml-1 text-[11px] text-brand-khaki font-normal">
                        (Max {repairLimit} repair {repairLimit === 1 ? "loop" : "loops"})
                      </span>
                    </span>
                  </div>

                  {/* Hidden input to strictly preserve form contract if checked by name/id */}
                  <input type="hidden" id="repair-limit" name="max_repair_rounds" value={repairLimit} />

                  {/* Top Row: Stepper Controls & Label Card */}
                  <div className="mt-2 flex items-center justify-between rounded-lg border border-[#3d191e] bg-[#120608] px-3.5 py-2 shadow-inner">
                    <span className="font-mono text-xs text-brand-khaki">Budget</span>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleRepairLimitChange(Math.max(1, repairLimit - 1))}
                        disabled={locked || repairLimit <= 1}
                        title="Decrease repair budget"
                        aria-label="Decrease repair budget"
                        className="flex h-7 w-7 items-center justify-center rounded-md border border-[#3d191e] bg-[#1e0c10] text-sm font-bold text-rose-300 transition-all hover:border-rose-500 hover:bg-[#2e1117] hover:text-rose-100 disabled:opacity-40 disabled:cursor-not-allowed outline-none focus:outline-none focus-visible:outline-none focus:ring-1 focus:ring-rose-500/30"
                      >
                        −
                      </button>
                      <span className="min-w-[28px] text-center font-mono text-sm font-bold text-foreground">
                        {repairLimit}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRepairLimitChange(Math.min(5, repairLimit + 1))}
                        disabled={locked || repairLimit >= 5}
                        title="Increase repair budget"
                        aria-label="Increase repair budget"
                        className="flex h-7 w-7 items-center justify-center rounded-md border border-[#3d191e] bg-[#1e0c10] text-sm font-bold text-rose-300 transition-all hover:border-rose-500 hover:bg-[#2e1117] hover:text-rose-100 disabled:opacity-40 disabled:cursor-not-allowed outline-none focus:outline-none focus-visible:outline-none focus:ring-1 focus:ring-rose-500/30"
                      >
                        +
                      </button>
                    </div>
                  </div>

                  {/* Bottom Row: 5 Interactive Horizontal Pill Segments */}
                  <div className="mt-2 grid grid-cols-5 gap-1.5" role="group" aria-label="Repair round selector segments">
                    {[1, 2, 3, 4, 5].map((level) => {
                      const isFilled = level <= repairLimit;
                      return (
                        <button
                          key={level}
                          type="button"
                          disabled={locked}
                          onClick={() => handleRepairLimitChange(level)}
                          title={`Set repair budget to ${level} ${level === 1 ? "round" : "rounds"}`}
                          className={`h-2.5 rounded-full transition-all duration-300 outline-none focus:outline-none focus-visible:outline-none ${
                            isFilled
                              ? "bg-gradient-to-r from-rose-600 via-pink-500 to-amber-400 shadow-[0_0_8px_rgba(225,29,72,0.6)]"
                              : "bg-[#251014] hover:bg-[#35161c]"
                          } disabled:cursor-not-allowed`}
                        />
                      );
                    })}
                  </div>

                  <p id="repair-help" className="mt-2 text-xs leading-5 text-brand-khaki">
                    The engine may enforce a lower limit.
                  </p>
                </div>

                {(formError || migration.submitError) && (
                  <p
                    role="alert"
                    className="rounded-lg border border-rose-500/40 bg-rose-950/40 p-3.5 text-xs leading-5 text-rose-200"
                  >
                    {formError ?? migration.submitError}
                  </p>
                )}

                {/* Primary Action Button: Passive/Disabled when active or completed; Glossy Shimmer when fresh */}
                <button
                  type="submit"
                  disabled={isMigrationActiveOrFinished || isDisconnected}
                  className={
                    isMigrationActiveOrFinished || isDisconnected
                      ? "flex w-full items-center justify-center gap-2.5 rounded-lg px-4 py-3 text-sm font-medium tracking-wide bg-zinc-900/80 text-zinc-500 border border-zinc-800 shadow-none cursor-not-allowed opacity-55 transition-all duration-200"
                      : "glossy-button glossy-shimmer flex w-full items-center justify-center gap-2.5 rounded-lg px-4 py-3 text-sm font-bold tracking-wide text-foreground shadow-lg transition-all duration-200"
                  }
                >
                  {isMigrationActiveOrFinished ? (
                    migration.submitting || migration.busy ? (
                      <span className="h-4 w-4 rounded-full border-2 border-zinc-600 border-t-zinc-400 animate-spin" />
                    ) : migration.currentState === "PR_CREATED" ? (
                      <svg className="h-4 w-4 text-zinc-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : migration.currentState === "USER_APPROVAL" ? (
                      <svg className="h-4 w-4 text-zinc-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="10" y1="15" x2="10" y2="9" />
                        <line x1="14" y1="15" x2="14" y2="9" />
                      </svg>
                    ) : (
                      <svg aria-hidden="true" viewBox="0 0 20 20" width="15" height="15" fill="currentColor">
                        <path d="m6 3 11 7-11 7V3Z" />
                      </svg>
                    )
                  ) : (
                    <svg aria-hidden="true" viewBox="0 0 20 20" width="15" height="15" fill="currentColor">
                      <path d="m6 3 11 7-11 7V3Z" />
                    </svg>
                  )}
                  {migration.currentState === "USER_APPROVAL"
                    ? "Awaiting user approval"
                    : migration.currentState === "PR_CREATED"
                    ? "Migration completed (PR ready)"
                    : migration.currentState === "ROLLED_BACK"
                    ? "Migration halted (Rolled back)"
                    : migration.submitting
                    ? "Starting migration…"
                    : migration.busy
                    ? "Migration in progress"
                    : "Start migration"}
                </button>

                {/* Secondary Action: Reset button when active/completed */}
                {isMigrationActiveOrFinished && (
                  <button
                    type="button"
                    onClick={handleReset}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#3d191e] bg-[#1a0a0d] px-4 py-2.5 text-xs font-semibold text-rose-300 transition-all hover:border-rose-500/50 hover:bg-[#280f14] hover:text-rose-100"
                  >
                    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                      <path d="M3 3v5h5" />
                    </svg>
                    <span>Reset migration workspace</span>
                  </button>
                )}

                {isDisconnected && !isMigrationActiveOrFinished && (
                  <p className="text-xs leading-5 text-amber-200">
                    Waiting for the live connection before starting.
                  </p>
                )}
              </form>
            </section>

            {/* Scope & Bounds Reference Card */}
            <section
              aria-labelledby="scope-heading"
              className="card-gradient rounded-xl border border-[#3d191e] p-5 shadow-sm transition-all duration-200 hover:border-rose-500/40"
            >
              <BlurReveal
                as="h2"
                id="scope-heading"
                className="text-sm font-semibold tracking-tight text-foreground"
                delay={0.15}
              >
                Designed for focused repairs
              </BlurReveal>
              <p className="mt-2 text-xs leading-6 text-brand-khaki">
                PyTorch CUDAExtension projects with 1–5 CUDA files and up to 2,000 CUDA lines.
              </p>
              <dl className="mt-4 divide-y divide-[#3d191e] text-xs">
                <div className="flex justify-between py-2.5">
                  <dt className="text-brand-khaki">Per patch</dt>
                  <dd className="font-mono font-medium text-foreground">≤ 120 lines</dd>
                </div>
                <div className="flex justify-between gap-2 py-2.5">
                  <dt className="text-brand-khaki">Total changes</dt>
                  <dd className="font-mono font-medium text-foreground">≤ min(300, 15% LOC)</dd>
                </div>
                <div className="flex justify-between py-2.5">
                  <dt className="text-brand-khaki">Verification</dt>
                  <dd className="font-medium text-foreground">CPU reference required</dd>
                </div>
              </dl>
            </section>
          </motion.aside>

          {/* Right Column: Pipeline, Live Output & Verification */}
          <div className="min-w-0 space-y-6">
            {migration.mode === "mock" && (
              <div
                role="status"
                className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm leading-6 text-amber-200 shadow-sm"
              >
                <strong className="font-semibold">Mock backend connected.</strong> This run simulates the API
                lifecycle. No repository changes, GPU execution, or numerical verification are performed.
              </div>
            )}

            {migration.job && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#3d191e] bg-[#16080a] px-4 py-2 text-xs text-brand-khaki shadow-sm">
                <span className="min-w-0 break-all">
                  Job <code className="ml-2 font-mono text-rose-300 font-semibold">{migration.job.job_id}</code>
                </span>
                <span>
                  Reported repair rounds:{" "}
                  <span className="font-mono font-bold text-foreground">{migration.job.repair_rounds_used}</span>
                </span>
              </div>
            )}

            {migration.statusError && (
              <div
                role="alert"
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3.5 text-xs leading-5 text-amber-200"
              >
                <span>{migration.statusError}</span>
                <button
                  type="button"
                  onClick={migration.refreshStatus}
                  className="rounded-lg border border-amber-400/40 bg-amber-400/20 px-2.5 py-1 font-medium hover:bg-amber-400/30"
                >
                  Retry status
                </button>
              </div>
            )}

            {migration.currentState === "USER_APPROVAL" && (
              <div
                role="status"
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-rose-500/60 bg-gradient-to-r from-rose-950/70 via-[#2a0e14] to-rose-950/70 p-4 shadow-[0_0_20px_rgba(225,29,72,0.3)]"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
                      <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose-500" />
                    </span>
                    <strong className="text-sm font-semibold text-foreground">
                      Stage 11: Awaiting Explicit Approval
                    </strong>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-rose-200">
                    This migration is awaiting explicit user approval. Review the verification report before approving
                    through the backend approval flow.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleApprove}
                  disabled={migration.approving}
                  className="shrink-0 flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-rose-600 to-rose-700 hover:from-rose-500 hover:to-rose-600 px-4 py-2.5 text-xs font-bold text-white shadow-[0_0_15px_rgba(225,29,72,0.4)] transition-all hover:shadow-[0_0_20px_rgba(225,29,72,0.6)] hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>{migration.approving ? "Approving…" : "Approve & Open Pull Request"}</span>
                </button>
              </div>
            )}

            {migration.approvalError && (
              <div
                role="alert"
                className="rounded-xl border border-rose-500/40 bg-rose-950/40 p-3.5 text-xs leading-5 text-rose-200"
              >
                {migration.approvalError}
              </div>
            )}

            {migration.currentState === "PR_CREATED" && (
              <div
                role="status"
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-emerald-500/50 bg-gradient-to-r from-emerald-950/50 via-[#102419] to-emerald-950/50 p-4 shadow-[0_0_20px_rgba(16,185,129,0.2)]"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 border border-emerald-400/40 text-emerald-300">
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                  <div>
                    <strong className="text-sm font-semibold text-emerald-200">
                      Migration Completed — 12/12 Stages Verified
                    </strong>
                    <p className="mt-0.5 text-xs text-brand-khaki">
                      Pull request ready on branch <code className="font-mono text-emerald-300 font-semibold">{branch}</code>. All numerical tests passed CPU reference.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleReset}
                  className="shrink-0 flex items-center justify-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-950/40 hover:bg-emerald-900/50 px-3 py-1.5 text-xs font-semibold text-emerald-200 transition-all"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                    <path d="M3 3v5h5" />
                  </svg>
                  <span>Reset workspace</span>
                </button>
              </div>
            )}

            {/* 12-Stage Visual Workflow Diagram */}
            <StateStepper
              currentState={migration.currentState}
              events={migration.events}
              onApprove={handleApprove}
              isCompleted={migration.currentState === "PR_CREATED"}
            />

            {/* Live Output Terminal Panel with Segmented Control & Unified Diff */}
            <LogTerminal
              events={migration.events}
              jobId={migration.job?.job_id ?? null}
              connection={migration.connection}
              error={migration.streamError}
              onReconnect={migration.reconnect}
            />

            {/* Numerical Verification Panel */}
            <VerificationSummary report={migration.job?.verification_report ?? null} events={migration.events} />
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-[#3d191e] pt-6 text-xs text-brand-khaki">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-600 shadow-[0_0_6px_rgba(225,29,72,0.8)]" />
            <span>ROCmigrator · CUDA-to-HIP migration workspace</span>
          </div>
          <span className="font-mono text-brand-khaki/80">GPU jobs run on the isolated AMD runner.</span>
        </footer>
      </main>
    </div>
  );
}
