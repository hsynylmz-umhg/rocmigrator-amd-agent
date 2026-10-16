"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { approveMigration, readMigration, startMigration, type JobResponse } from "../lib/api";
import type { JobCreateRequest, JobStatusResponse, LogEvent, PatchProposal, PipelineState } from "../lib/contracts";
import { useLogStream } from "./useLogStream";

const restingStates: ReadonlySet<PipelineState> = new Set(["ROLLED_BACK", "PR_CREATED", "USER_APPROVAL"]);

export function useMigration() {
  const stream = useLogStream();
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [currentState, setCurrentState] = useState<PipelineState | null>(null);
  const [mode, setMode] = useState<JobResponse["mode"]>("unspecified");
  const [submitting, setSubmitting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const submission = useRef<AbortController | null>(null);
  const approvalAbort = useRef<AbortController | null>(null);
  const activeJobId = useRef<string | null>(null);
  const latestEvent = useRef<LogEvent | undefined>(undefined);
  const events = useMemo(() => stream.events.filter(event => event.job_id === job?.job_id), [stream.events, job?.job_id]);
  const lastEvent = events.at(-1);
  latestEvent.current = lastEvent;

  const patches = useMemo<readonly PatchProposal[]>(() => {
    return events
      .map((e) => e.data)
      .filter((d): d is PatchProposal => Boolean(d && typeof d === "object" && "diff" in d && "patch_id" in d));
  }, [events]);

  useEffect(() => () => {
    submission.current?.abort();
    approvalAbort.current?.abort();
  }, []);

  useEffect(() => {
    if (lastEvent) setCurrentState(lastEvent.state);
  }, [lastEvent]);

  // Read snapshots once after acceptance, reconnection, or a terminal SSE state.
  // There are no interval timers or status-polling loops. SSE remains authoritative
  // if another event arrives while a snapshot request is in flight.
  const settledEvent = lastEvent && restingStates.has(lastEvent.state) ? lastEvent.state : null;
  useEffect(() => {
    if (!job?.job_id) return;
    const jobId = job.job_id;
    const controller = new AbortController();
    const eventAtRequest = latestEvent.current;
    void readMigration(jobId, controller.signal).then(result => {
      if (controller.signal.aborted || activeJobId.current !== jobId) return;
      if (result.status.job_id !== jobId) throw new Error("The backend returned a different migration. Its status was rejected.");
      setJob(result.status);
      setMode(result.mode);
      setStatusError(null);
      if (latestEvent.current === eventAtRequest) setCurrentState(result.status.current_state);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setStatusError(error instanceof Error ? error.message : "Unable to read the migration status.");
    });
    return () => controller.abort();
  }, [job?.job_id, stream.connectionEpoch, settledEvent, refresh]);

  const busy = currentState !== null && !restingStates.has(currentState);

  const start = useCallback(async (request: JobCreateRequest) => {
    if (submission.current || busy || stream.connection !== "connected") return;
    const controller = new AbortController();
    submission.current = controller;
    activeJobId.current = null;
    setSubmitting(true);
    setSubmitError(null);
    setStatusError(null);
    setApprovalError(null);
    setJob(null);
    setCurrentState(null);
    setMode("unspecified");
    stream.resetForNewJob();
    try {
      const result = await startMigration(request, controller.signal);
      if (controller.signal.aborted) return;
      activeJobId.current = result.status.job_id;
      setJob(result.status);
      setCurrentState(result.status.current_state);
      setMode(result.mode);
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        const message = error instanceof Error ? error.message : "Unable to start the migration.";
        setSubmitError(`${message} If the response was lost, the job may already exist; check the backend before starting again.`);
      }
    } finally {
      submission.current = null;
      if (!controller.signal.aborted) setSubmitting(false);
    }
  }, [busy, stream.connection, stream.resetForNewJob]);

  const approve = useCallback(async () => {
    if (!job?.job_id || approving) return;
    const controller = new AbortController();
    approvalAbort.current = controller;
    setApproving(true);
    setApprovalError(null);
    try {
      await approveMigration(job.job_id, controller.signal);
      // Re-read migration status to sync with the backend
      setRefresh(v => v + 1);
    } catch (error: unknown) {
      if (!controller.signal.aborted) {
        setApprovalError(error instanceof Error ? error.message : "Unable to approve the migration.");
      }
    } finally {
      approvalAbort.current = null;
      if (!controller.signal.aborted) setApproving(false);
    }
  }, [job?.job_id, approving]);

  const resetWorkspace = useCallback(() => {
    submission.current?.abort();
    approvalAbort.current?.abort();
    activeJobId.current = null;
    setJob(null);
    setCurrentState(null);
    setMode("unspecified");
    setSubmitting(false);
    setApproving(false);
    setSubmitError(null);
    setStatusError(null);
    setApprovalError(null);
    stream.resetForNewJob();
  }, [stream.resetForNewJob]);

  return {
    job,
    currentState,
    mode,
    events,
    logs: events,
    patches,
    report: job?.verification_report ?? null,
    busy,
    submitting,
    approving,
    submitError,
    statusError,
    approvalError,
    error: submitError || statusError || approvalError || stream.error,
    start,
    startMigration: start,
    approveMigration: approve,
    resetWorkspace,
    connected: stream.connection === "connected",
    connection: stream.connection,
    streamError: stream.error,
    reconnect: stream.reconnect,
    refreshStatus: () => setRefresh(value => value + 1),
  };
}

