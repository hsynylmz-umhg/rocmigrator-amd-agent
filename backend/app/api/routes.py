"""Strict lifecycle endpoints backed by the asynchronous migration engine.

The engine owns job snapshots, rejection, transitions, and lifecycle SSE events.
Its current store and background tasks are process-local: use one API worker
until durable storage and job dispatch are connected.
"""

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from agent_orchestrator.engine import (
    get_migration_status as get_engine_migration_status,
    run_migration_pipeline,
)
from backend.app.services.stream import log_streamer
from backend.app.services.approval import ApprovalError, approve_migration
from contracts.api_schemas import (
    ApprovalRequest,
    JobCreateRequest,
    JobStatusResponse,
    VerificationReport,
)
from contracts.state_schemas import PipelineState

router = APIRouter(prefix="/api", tags=["migration"])


_NO_CACHE_HEADERS: dict[str, str] = {"Cache-Control": "no-store"}


def _require_status(task_id: str) -> JobStatusResponse:
    """Read the engine's immutable snapshot without maintaining a second store."""
    snapshot = get_engine_migration_status(task_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Migration task not found.",
            headers=_NO_CACHE_HEADERS,
        )
    return snapshot


@router.post(
    "/jobs",
    response_model=JobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    deprecated=True,
    name="create_job",
)
@router.post(
    "/migrate",
    response_model=JobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    name="start_migration",
)
async def start_migration(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
) -> JobStatusResponse:
    """Acknowledge dispatch; the engine registers and runs the job after the response."""
    snapshot = JobStatusResponse(
        job_id=f"job-{uuid4().hex}",
        current_state=PipelineState.CREATED,
        repair_rounds_used=0,
    )
    background_tasks.add_task(run_migration_pipeline, snapshot.job_id, payload)
    response.headers.update(_NO_CACHE_HEADERS)
    response.headers["Location"] = str(
        request.url_for("get_migration_status", task_id=snapshot.job_id)
    )
    return snapshot


@router.get(
    "/jobs/{task_id}",
    response_model=JobStatusResponse,
    deprecated=True,
    name="get_job_status",
)
@router.get(
    "/status/{task_id}",
    response_model=JobStatusResponse,
    name="get_migration_status",
)
async def get_migration_status(task_id: str, response: Response) -> JobStatusResponse:
    """Read the current snapshot without advancing the task; logs use SSE."""
    response.headers.update(_NO_CACHE_HEADERS)
    return _require_status(task_id)


@router.get("/report/{task_id}", response_model=VerificationReport)
async def get_migration_report(task_id: str, response: Response) -> VerificationReport:
    """Return the engine's report, or 409 until one is available."""
    response.headers.update(_NO_CACHE_HEADERS)
    snapshot = _require_status(task_id)
    if snapshot.verification_report is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The verification report is not available yet.",
            headers={**_NO_CACHE_HEADERS, "Retry-After": "1"},
        )
    return snapshot.verification_report


@router.post(
    "/jobs/{task_id}/approve",
    response_model=ApprovalRequest,
    deprecated=True,
)
async def approve_job(task_id: str, payload: ApprovalRequest, response: Response) -> ApprovalRequest:
    """Publish only this explicitly approved job's verified isolated source."""
    _require_status(task_id)
    if payload.job_id != task_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval job_id must match the requested task_id.",
            headers=_NO_CACHE_HEADERS,
        )
    try:
        await approve_migration(task_id, payload)
    except ApprovalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc), headers=_NO_CACHE_HEADERS) from None
    response.headers.update(_NO_CACHE_HEADERS)
    return payload


@router.get("/logs/stream", response_class=StreamingResponse)
async def sse_logs() -> StreamingResponse:
    """Stream SSE frames containing serialized, strictly validated LogEvent models."""
    return StreamingResponse(
        log_streamer.stream_logs(),
        media_type="text/event-stream",
        headers={
            # Prevent proxy compression from buffering small SSE frames.
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
