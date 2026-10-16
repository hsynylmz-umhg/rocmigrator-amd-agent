"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import type { LogEvent, LogLevel, PatchProposal } from "../lib/contracts";

interface LogTerminalProps {
  readonly events: readonly LogEvent[];
  readonly jobId: string | null;
  readonly connection: "connecting" | "connected" | "reconnecting" | "closed";
  readonly error: string | null;
  readonly onReconnect: () => void;
}

const levelColors: Readonly<Record<LogLevel, string>> = {
  INFO: "text-brand-khaki",
  STEP: "text-foreground",
  WARNING: "text-amber-300",
  ERROR: "text-rose-400 font-semibold",
};

const ASCII_BANNER = ` ____   ___   ____           _                 _             
|  _ \\ / _ \\ / ___|_ __ ___ (_) __ _ _ __ __ _| |_ ___  _ __ 
| |_) | | | | |   | '_ \` _ \\| |/ _\` | '__/ _\` | __/ _ \\| '__|
|  _ <| |_| | |___| | | | | | | (_| | | | (_| | || (_) | |   
|_| \\_\\\\___/ \\____|_| |_| |_|_|\\__, |_|  \\__,_|\\__\\___/|_|   
                               |___/                         `;

export function LogTerminal({ events, jobId, connection, error, onReconnect }: LogTerminalProps) {
  const viewport = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [following, setFollowing] = useState(true);
  const [activeTab, setActiveTab] = useState<"output" | "changes">("output");

  const patches: readonly PatchProposal[] = events
    .map((e) => e.data)
    .filter((d): d is PatchProposal => Boolean(d && typeof d === "object" && "diff" in d && "patch_id" in d));

  useEffect(() => {
    follow.current = true;
    setFollowing(true);
  }, [jobId]);

  useEffect(() => {
    const element = viewport.current;
    if (element && follow.current) {
      element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
    }
  }, [events, jobId, activeTab]);

  function scrollToLatest() {
    follow.current = true;
    setFollowing(true);
    if (viewport.current) {
      viewport.current.scrollTo({ top: viewport.current.scrollHeight, behavior: "smooth" });
    }
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.6, delay: 0.24, ease: [0.16, 1, 0.3, 1] }}
      className="card-gradient overflow-hidden rounded-xl border border-[#3d191e] shadow-xl transition-all duration-200"
      aria-labelledby="terminal-heading"
    >
      {/* Terminal Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#3d191e] bg-[#16080a] px-4 py-3 sm:px-5">
        <div className="flex items-center gap-4">
          <h2 id="terminal-heading" className="flex items-center gap-2.5 text-sm font-semibold tracking-tight text-foreground">
            <span aria-hidden="true" className="font-mono text-rose-500 font-bold">&gt;_</span>
            <span>Live output</span>
          </h2>

          {/* Unified Segmented Pill Control with Framer Motion layoutId Active Pill */}
          <div
            role="tablist"
            aria-label="Terminal views"
            className="relative inline-flex items-center rounded-lg border border-[#3d191e] bg-[#0c0406] p-1 shadow-inner"
          >
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "output"}
              onClick={() => setActiveTab("output")}
              className={`relative flex items-center justify-center px-3 py-1 text-xs font-semibold transition-colors duration-200 ${
                activeTab === "output" ? "text-foreground" : "text-brand-khaki hover:text-foreground"
              }`}
            >
              {activeTab === "output" && (
                <motion.span
                  layoutId="activeOutputTab"
                  className="absolute inset-0 rounded-md border border-rose-500/50 bg-gradient-to-r from-rose-950 via-[#38141b] to-rose-950 shadow-[0_0_12px_rgba(225,29,72,0.35)]"
                  transition={{ type: "spring", stiffness: 450, damping: 35 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="4 17 10 11 4 5" />
                  <line x1="12" y1="19" x2="20" y2="19" />
                </svg>
                Output
              </span>
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "changes"}
              onClick={() => setActiveTab("changes")}
              className={`relative flex items-center justify-center px-3 py-1 text-xs font-semibold transition-colors duration-200 ${
                activeTab === "changes" ? "text-foreground" : "text-brand-khaki hover:text-foreground"
              }`}
            >
              {activeTab === "changes" && (
                <motion.span
                  layoutId="activeOutputTab"
                  className="absolute inset-0 rounded-md border border-rose-500/50 bg-gradient-to-r from-rose-950 via-[#38141b] to-rose-950 shadow-[0_0_12px_rgba(225,29,72,0.35)]"
                  transition={{ type: "spring", stiffness: 450, damping: 35 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-1.5">
                <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="12" y1="18" x2="12" y2="12" />
                  <line x1="9" y1="15" x2="15" y2="15" />
                </svg>
                Changes
                {patches.length > 0 && (
                  <span className="flex h-4 min-w-[18px] items-center justify-center rounded-full border border-rose-500/40 bg-rose-600/40 px-1 text-[10px] font-mono font-bold text-rose-200 shadow-sm">
                    {patches.length}
                  </span>
                )}
              </span>
            </button>
          </div>
        </div>

        {/* Live stream badge and lines retained */}
        <div className="flex items-center gap-3 text-xs">
          <span className="text-brand-khaki">{events.length} lines retained</span>
          <span className="text-brand-khaki/50">•</span>
          <span
            className={`flex items-center gap-2 ${
              connection === "connected" ? "text-emerald-300" : "text-amber-200"
            }`}
          >
            <span className="relative flex h-2 w-2">
              <span
                className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  connection === "connected" ? "bg-emerald-400 animate-ping" : "bg-amber-400"
                }`}
              />
              <span
                aria-hidden="true"
                className={`relative inline-flex h-2 w-2 rounded-full ${
                  connection === "connected" ? "bg-emerald-500" : "bg-amber-400"
                }`}
              />
            </span>
            {connection === "connected"
              ? "Live stream"
              : connection === "reconnecting"
              ? "Reconnecting"
              : connection === "connecting"
              ? "Connecting"
              : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Connection Banner */}
      {(error || connection !== "connected") && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-400/20 bg-amber-400/10 px-5 py-3 text-xs leading-5 text-amber-200"
        >
          <span>{error ?? "Connecting to the migration service. Make sure the backend is running."}</span>
          {connection === "closed" && (
            <button
              type="button"
              onClick={onReconnect}
              className="rounded border border-amber-400/40 bg-amber-400/20 px-2.5 py-1 text-xs font-medium hover:bg-amber-400/30 transition-colors"
            >
              Reconnect
            </button>
          )}
        </div>
      )}

      {/* Smoothly Animated Viewport Container */}
      <div className="relative h-[380px] overflow-hidden sm:h-[430px]">
        {/* Output Tab View */}
        <div
          ref={viewport}
          role="log"
          aria-label={jobId ? `Migration log for ${jobId}` : "Migration log"}
          aria-live="polite"
          aria-relevant="additions"
          tabIndex={0}
          onScroll={() => {
            const element = viewport.current;
            if (!element) return;
            const atEnd = element.scrollHeight - element.scrollTop - element.clientHeight < 32;
            follow.current = atEnd;
            setFollowing(atEnd);
          }}
          className={`terminal h-full overflow-y-auto px-4 py-5 font-mono text-xs leading-6 sm:px-5 transition-all duration-300 ease-out ${
            activeTab === "output"
              ? "opacity-100 translate-x-0 pointer-events-auto"
              : "opacity-0 -translate-x-6 pointer-events-none absolute inset-0"
          }`}
        >
          {events.length === 0 ? (
            <div className="flex h-full flex-col justify-center px-2 text-brand-khaki sm:px-6">
              <div className="mb-4 flex flex-col items-start select-none">
                <pre className="font-mono text-[9px] sm:text-[11px] leading-tight font-extrabold bg-gradient-to-r from-rose-500 via-amber-400 to-pink-500 bg-clip-text text-transparent">
                  {ASCII_BANNER}
                </pre>
                <span className="mt-1.5 text-[10px] sm:text-xs font-mono text-rose-300/80 tracking-wider">
                  [ROCm™ AST Synthesizer • CUDA-to-HIP Bounded Repair Engine]
                </span>
              </div>
              <div className="mb-3 flex items-center gap-1 text-2xl font-bold text-rose-500">
                <span>&gt;</span>
                <span className="terminal-cursor inline-block h-5 w-2.5 bg-rose-500" />
              </div>
              <p className="text-foreground font-semibold">
                {jobId ? "Waiting for job output." : "Your migration output starts here."}
              </p>
              <p className="mt-1.5 max-w-md text-brand-khaki text-xs leading-5">
                {jobId
                  ? "Only events for this migration will appear. The current state is also recovered after a connection interruption."
                  : "Select a repository and start a migration. Follow each step, compiler message, and repair as it happens."}
              </p>
            </div>
          ) : (
            <>
              {events.map((event, index) => (
                <div
                  key={`${event.timestamp}-${index}`}
                  className="grid grid-cols-[auto_1fr] gap-x-3 border-l-2 border-transparent py-0.5 transition-colors hover:border-rose-500 hover:bg-[#231013]/70 sm:grid-cols-[auto_4rem_1fr]"
                >
                  <time
                    dateTime={event.timestamp}
                    title={event.timestamp}
                    className="select-none text-brand-khaki/80"
                  >
                    {new Date(event.timestamp).toISOString().slice(11, 19)}
                  </time>
                  <span className={`${levelColors[event.level]} hidden sm:block font-medium`}>
                    {event.level}
                  </span>
                  <span className="min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-foreground">
                    <span className={`mr-2 sm:hidden ${levelColors[event.level]}`}>{event.level}</span>
                    <span className="mr-2 text-rose-400 font-medium">[{event.state}]</span>
                    {event.message}
                  </span>
                </div>
              ))}
              {/* Blinking Terminal Cursor */}
              <div className="flex items-center gap-1.5 pt-2 text-rose-500 font-mono text-xs select-none">
                <span>&gt;</span>
                <span className="terminal-cursor inline-block h-3.5 w-2 bg-rose-500" />
              </div>
            </>
          )}
        </div>

        {/* Changes Tab View */}
        <div
          className={`terminal h-full overflow-y-auto px-4 py-5 font-mono text-xs leading-6 sm:px-5 transition-all duration-300 ease-out ${
            activeTab === "changes"
              ? "opacity-100 translate-x-0 pointer-events-auto"
              : "opacity-0 translate-x-6 pointer-events-none absolute inset-0"
          }`}
        >
          {patches.length === 0 ? (
            <div className="flex h-full flex-col justify-center px-4 text-brand-khaki sm:px-6">
              <svg className="mb-3 h-8 w-8 text-rose-500/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="15" y2="15" />
              </svg>
              <p className="text-foreground font-semibold">No code patches generated yet.</p>
              <p className="mt-1 max-w-md text-brand-khaki text-xs">
                Kernel diffs and HIPIFY modifications will appear here when the repair loop runs.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {patches.map((patch) => (
                <div key={patch.patch_id} className="rounded-lg border border-[#3d191e] bg-[#14080a] p-4 shadow-sm">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-[#3d191e] pb-2">
                    <span className="font-semibold text-foreground">{patch.file_path}</span>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-emerald-400 font-mono font-semibold">+{patch.lines_added}</span>
                      <span className="text-rose-400 font-mono font-semibold">-{patch.lines_deleted}</span>
                      <span className="rounded bg-[#231013] px-2 py-0.5 text-brand-khaki border border-[#3d191e]">
                        {patch.patch_id}
                      </span>
                    </div>
                  </div>
                  <p className="mb-3 text-xs text-brand-khaki">{patch.explanation}</p>
                  <pre className="overflow-x-auto rounded bg-[#0a0304] p-3 text-[11px] leading-5 text-foreground border border-[#3d191e]/50">
                    {patch.diff.split("\n").map((line, lIdx) => (
                      <div
                        key={lIdx}
                        className={
                          line.startsWith("+")
                            ? "bg-emerald-950/40 text-emerald-300 font-medium"
                            : line.startsWith("-")
                            ? "bg-rose-950/40 text-rose-300 font-medium"
                            : line.startsWith("@")
                            ? "text-cyan-400 font-bold"
                            : "text-brand-khaki/90"
                        }
                      >
                        {line}
                      </div>
                    ))}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Terminal Footer Bar */}
      <div className="flex items-center justify-between gap-3 border-t border-[#3d191e] bg-[#16080a] px-4 py-2.5 text-[11px] text-brand-khaki sm:px-5">
        <span className="font-mono">UTC timestamps · Latest 1,000 stream events retained</span>
        <button
          type="button"
          onClick={scrollToLatest}
          disabled={following}
          className="shrink-0 rounded px-2.5 py-1 text-foreground transition-all hover:bg-[#231013] hover:text-rose-300 disabled:text-brand-khaki/50"
        >
          {following ? "Following output" : "Jump to latest"}
        </button>
      </div>
    </motion.section>
  );
}
