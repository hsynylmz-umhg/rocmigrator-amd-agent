# ROCmigrator dashboard

The Next.js App Router dashboard starts jobs at `POST /api/migrate` and consumes
strict `LogEvent` JSON from `/api/logs/stream`. The API's existing mock mode is
shown explicitly. A mock rollback never appears as successful verification.

Run FastAPI from the repository root with
`python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`.
In `frontend`, run `npm ci` and `npm run dev`, then open `http://localhost:3000`.
Use Node.js 24 LTS for development and the built-in test runner. Next.js itself
requires Node.js 20.9 or newer. Set `BACKEND_URL` in `.env.local` if FastAPI uses
a different origin; `.env.example` documents the default. Restart Next.js after
changing it. No browser-side backend URL or CORS configuration is required.

Validation: `npm run typecheck`, `npm test`, and `npm run build`.

## Streaming and consistency

- The connection opens before a migration can be submitted. The terminal shares
  the dashboard's single `useLogStream` subscription.
- Events arriving before the POST response are buffered and subsequently filtered
  by the exact returned job ID. The latest 1,000 stream events are retained.
- A snapshot is read once after acceptance, after reconnecting, and when a job
  reaches rollback, approval, or PR creation. There is no polling loop.
- The backend sends an initial SSE comment and 15-second heartbeat comments,
  with `Cache-Control: no-cache, no-transform` to prevent compression buffering.
  A production reverse proxy must disable buffering and allow long-lived SSE.
- The stream has no event IDs or replay history. Reconnecting restores current
  status, not missed log lines. Logs and selected job live in browser memory;
  refreshing the page clears them. The current backend store is also process-local.
- Failed POST responses are never retried automatically: the API does not expose
  an idempotency key and the job may already have been accepted.
- State labels use the contract's exact states, including the compile/repair loop.
  Seen steps are not presented as proof that verification passed. Approval is never
  inferred and this dashboard does not open pull requests.

`src/lib/contracts.ts` mirrors the serialized Pydantic contracts and validates
HTTP and SSE values at runtime. The Python schemas remain authoritative.
