import { parseJobStatusResponse, type JobCreateRequest, type JobStatusResponse } from "./contracts";

export interface JobResponse {
  readonly status: JobStatusResponse;
  readonly mode: "mock" | "unspecified";
}

async function jobRequest(path: string, init: RequestInit, signal: AbortSignal): Promise<JobResponse> {
  const response = await fetch(path, {
    ...init,
    cache: "no-store",
    signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
    headers: { "Accept": "application/json", ...init.headers },
  });
  if (!response.ok) {
    // Never render proxy HTML or arbitrary server error objects as application text.
    if (response.status === 404) throw new Error("This migration is no longer available. The backend may have restarted.");
    if (response.status === 422) throw new Error("The backend rejected the repository path, branch, or repair limit. Check the fields and try again.");
    throw new Error(`The migration service returned HTTP ${response.status}. Check the backend connection.`);
  }
  const value: unknown = await response.json();
  return {
    status: parseJobStatusResponse(value),
    mode: response.headers.get("X-ROCmigrator-Mode") === "mock" ? "mock" : "unspecified",
  };
}

export function startMigration(request: JobCreateRequest, signal: AbortSignal): Promise<JobResponse> {
  return jobRequest("/api/migrate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  }, signal);
}

export function readMigration(jobId: string, signal: AbortSignal): Promise<JobResponse> {
  return jobRequest(`/api/status/${encodeURIComponent(jobId)}`, { method: "GET" }, signal);
}

export async function approveMigration(jobId: string, signal: AbortSignal): Promise<void> {
  const init: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      approved: true,
      comments: "Approved via migration workspace.",
    }),
  };
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/approve`, {
    ...init,
    cache: "no-store",
    signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
    headers: { "Accept": "application/json", ...init.headers },
  });
  if (!response.ok) {
    if (response.status === 404) throw new Error("This migration is no longer available. The backend may have restarted.");
    if (response.status === 409) throw new Error("Approval conflict for the current job.");
    if (response.status === 503) {
      const errorData = await response.json().catch(() => null);
      throw new Error((errorData as { detail?: string } | null)?.detail ?? "Approval is unavailable until the engine approval handler is connected.");
    }
    throw new Error(`The migration service returned HTTP ${response.status}. Check the backend connection.`);
  }
}
