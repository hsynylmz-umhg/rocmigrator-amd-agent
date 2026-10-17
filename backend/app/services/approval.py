"""Explicit approval and GitHub publication, outside the untrusted GPU runner."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts.api_schemas import ApprovalRequest, JobStatusResponse, LogEvent, PRLogData
from contracts.state_schemas import PipelineState
from contracts.verification_schemas import VerificationReport


class ApprovalError(RuntimeError):
    """An operational error safe to return without credentials or response bodies."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


class _GitObject(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class _Commit(_GitObject):
    tree: _GitObject
    parents: list[_GitObject] = Field(default_factory=list)
    message: str


class _Ref(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    object: _GitObject


class _Repository(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    full_name: str
    default_branch: str


class _PRBranch(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    ref: str
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    repo: _Repository


class ConfirmedPullRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)
    number: int = Field(gt=0)
    html_url: str
    state: str
    title: str
    body: str
    head: _PRBranch
    base: _PRBranch


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ApprovalError("GitHub redirected the request; publication stopped.")


class GitHubClient:
    """Bounded fixed-origin REST client. Authentication is never sent to a container."""

    def __init__(self):
        self._token = os.environ.get("ROCMIGRATOR_GITHUB_TOKEN", "").strip()
        if not self._token:
            raise ApprovalError("Approval requires a configured ROCMIGRATOR_GITHUB_TOKEN with repository contents and pull-request write permission.")
        self._opener = urllib.request.build_opener(_NoRedirect())

    def request(self, method: str, path: str, payload=None, *, allow_missing: bool = False):
        if method not in {"GET", "POST"} or not path.startswith("/repos/") or "\n" in path:
            raise ApprovalError("Invalid internal GitHub operation.")
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        request = urllib.request.Request(
            "https://api.github.com" + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "ROCmigrator",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self._opener.open(request, timeout=15) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_missing:
                return None
            descriptions = {
                401: "GitHub authentication failed.",
                403: "GitHub denied publication; check repository permissions or rate limits.",
                404: "GitHub repository or branch is unavailable to the configured identity.",
                409: "GitHub reported a branch or repository conflict.",
                422: "GitHub rejected publication; the branch or pull request may already exist.",
            }
            raise ApprovalError(descriptions.get(exc.code, f"GitHub request failed with HTTP {exc.code}.")) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ApprovalError("GitHub could not be reached; approval remains pending. Retry to reconcile any completed remote operations.") from None
        if len(raw) > 2 * 1024 * 1024:
            raise ApprovalError("GitHub returned an oversized response.")
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise ApprovalError("GitHub returned malformed JSON; publication was not confirmed.") from None


def _repository_name(remote: str | None) -> str:
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", remote or "")
    if not match:
        raise ApprovalError("Approval requires an inspected GitHub origin without embedded credentials.")
    return match.group(1)


def _branch_name(target: str, job_id: str) -> str:
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}", target)
        or any(part in {"", ".", ".."} or part.endswith(".lock") for part in target.split("/"))
        or ".." in target or target.endswith(".")
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", job_id)
    ):
        raise ApprovalError("The requested migration branch or job identifier is invalid.", 409)
    return f"codex/{target}-{job_id}"


def _verified_files(context) -> list[tuple[str, bytes]]:
    """Publish exactly bounded, non-secret source files from the verified workspace."""
    hashes = getattr(context, "verification_sha256", None)
    if not hashes or not context.changed_files or len(context.changed_files) > 16:
        raise ApprovalError("No bounded, immutable verified source changes are available for publication.", 409)
    root = context.workdir.resolve(strict=True)
    prefix = PurePosixPath(context.source_subdir)
    if prefix.is_absolute() or ".." in prefix.parts:
        raise ApprovalError("The repository export prefix is invalid.", 409)
    result = []
    for relative, expected in hashes.items():
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            raise ApprovalError("A verified source path escapes its workspace.", 409)
        source = root.joinpath(*path.parts)
        if source.is_symlink() or root not in source.resolve(strict=True).parents:
            raise ApprovalError("A verified source is no longer a regular isolated file.", 409)
        if not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
            raise ApprovalError("A verified source file exceeds the publication limits.", 409)
        contents = source.read_bytes()
        if hashlib.sha256(contents).hexdigest() != expected:
            raise ApprovalError("Source changed after GPU verification; rerun the migration before approval.", 409)
        if relative in context.changed_files:
            if path.suffix.lower() not in {".cu", ".cuh", ".cpp", ".hip", ".h", ".hpp"}:
                raise ApprovalError("Publication contains a source file outside the migration allowlist.", 409)
            result.append(((prefix / path).as_posix(), contents))
    if len(result) != len(context.changed_files):
        raise ApprovalError("Some changes were not included in GPU verification.", 409)
    return result


def publish_pull_request(context, report: VerificationReport, client: GitHubClient | None = None) -> ConfirmedPullRequest:
    """Publish a dedicated branch, then confirm a real open pull request via GitHub."""
    repository = _repository_name(context.source_remote)
    branch = _branch_name(context.request.target_branch, report.job_id)
    files = _verified_files(context)
    if not re.fullmatch(r"[0-9a-f]{40}", context.source_commit or ""):
        raise ApprovalError("The original repository commit was not recorded.", 409)
    client = client or GitHubClient()
    prefix = f"/repos/{repository}"
    try:
        repo = _Repository.model_validate(client.request("GET", prefix))
        if repo.full_name.casefold() != repository.casefold():
            raise ApprovalError("GitHub returned a different repository.")
        base = _Ref.model_validate(client.request("GET", prefix + "/git/ref/heads/" + urllib.parse.quote(repo.default_branch, safe="")))
        if base.object.sha != context.source_commit:
            raise ApprovalError("The repository default branch changed or differs from the verified source. Rerun migration before publication.", 409)
        original = _Commit.model_validate(client.request("GET", prefix + "/git/commits/" + context.source_commit))
        tree_items = []
        for path, contents in files:
            blob = _GitObject.model_validate(client.request("POST", prefix + "/git/blobs", {
                "content": base64.b64encode(contents).decode("ascii"), "encoding": "base64",
            }))
            tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob.sha})
        tree = _GitObject.model_validate(client.request("POST", prefix + "/git/trees", {"base_tree": original.tree.sha, "tree": tree_items}))
        if tree.sha == original.tree.sha:
            raise ApprovalError("Verified migration has no source changes to publish.", 409)
        ref_path = prefix + "/git/ref/heads/" + urllib.parse.quote(branch, safe="")
        existing = client.request("GET", ref_path, allow_missing=True)
        message = f"Port verified extension to ROCm for {report.job_id}"
        if existing is not None:
            commit_sha = _Ref.model_validate(existing).object.sha
            commit = _Commit.model_validate(client.request("GET", prefix + "/git/commits/" + commit_sha))
            if commit.tree.sha != tree.sha or [parent.sha for parent in commit.parents] != [context.source_commit] or commit.message != message:
                raise ApprovalError("The dedicated migration branch already contains unrelated changes.", 409)
        else:
            commit = _GitObject.model_validate(client.request("POST", prefix + "/git/commits", {
                "message": message, "tree": tree.sha, "parents": [context.source_commit],
            }))
            commit_sha = commit.sha
            created_ref = _Ref.model_validate(client.request("POST", prefix + "/git/refs", {"ref": "refs/heads/" + branch, "sha": commit_sha}))
            if created_ref.object.sha != commit_sha:
                raise ApprovalError("GitHub did not confirm the migration branch commit.")
        title = "Port verified extension to ROCm/HIP"
        body = (
            f"Migration job `{report.job_id}` was explicitly approved by the user.\n\n"
            f"The compiled GPU extension passed {report.passed_tests}/{report.total_tests} numerical cases "
            "against the independent CPU reference, including repeated-execution determinism checks.\n\n"
            f"Verification: {report.summary}\n\nOnly the verified migration source changes are included."
        )
        query = urllib.parse.urlencode({"state": "open", "head": repository.split("/")[0] + ":" + branch, "base": repo.default_branch})
        existing_prs = client.request("GET", prefix + "/pulls?" + query)
        if not isinstance(existing_prs, list) or len(existing_prs) > 1:
            raise ApprovalError("GitHub did not return a unique migration pull request.")
        candidate = existing_prs[0] if existing_prs else client.request("POST", prefix + "/pulls", {
            "title": title, "body": body, "head": branch, "base": repo.default_branch,
        })
        candidate = ConfirmedPullRequest.model_validate(candidate)
        confirmed = ConfirmedPullRequest.model_validate(client.request("GET", prefix + f"/pulls/{candidate.number}"))
        if (
            confirmed.state != "open" or confirmed.head.ref != branch or confirmed.head.sha != commit_sha
            or confirmed.base.ref != repo.default_branch
            or confirmed.head.repo.full_name.casefold() != repository.casefold()
            or confirmed.base.repo.full_name.casefold() != repository.casefold()
            or confirmed.html_url != f"https://github.com/{repository}/pull/{confirmed.number}"
        ):
            raise ApprovalError("GitHub did not confirm the expected open migration pull request.")
        return confirmed
    except ValidationError:
        raise ApprovalError("GitHub returned an invalid publication response; PR creation is not confirmed.") from None


_approval_locks: dict[str, asyncio.Lock] = {}


async def approve_migration(job_id: str, decision: ApprovalRequest) -> JobStatusResponse:
    """Require real job evidence and explicit same-job consent before any writes."""
    from agent_orchestrator import engine
    from agent_orchestrator.real_engine import get_job_context, rollback_job

    if decision.job_id != job_id:
        raise ApprovalError("Approval job_id must match the requested task_id.", 409)
    context = get_job_context(job_id)
    if context is None:
        raise ApprovalError("Approval is unavailable: this job is not connected to the real GPU runner.")
    lock = _approval_locks.setdefault(job_id, asyncio.Lock())
    if lock.locked():
        raise ApprovalError("Approval is already being processed for this job.", 409)
    async with lock:
        current = engine.get_migration_status(job_id)
        if current is None:
            raise ApprovalError("Migration task not found.", 404)
        report = current.verification_report
        if current.current_state != PipelineState.USER_APPROVAL:
            raise ApprovalError("Approval requires the USER_APPROVAL state.", 409)
        if not decision.approved:
            return await rollback_job(job_id, "User explicitly rejected the migration.")
        if (
            not context.verified or getattr(context, "job_id", None) != job_id
            or report is None or report.job_id != job_id or report.overall_status != "VERIFIED"
            or getattr(context, "verification_report", None) != report
            or len({case.seed for case in report.results}) < 2
            or len({case.shape for case in report.results}) < 2
            or len({case.dtype for case in report.results}) < 2
        ):
            raise ApprovalError("Approval requires this job's genuine GPU verification and complete numerical coverage.", 409)
        try:
            confirmed = await asyncio.to_thread(publish_pull_request, context, report)
        except Exception as exc:
            safe_error = exc if isinstance(exc, ApprovalError) else ApprovalError("Publication failed; the verified job remains awaiting approval.")
            await engine._publish(LogEvent(job_id=job_id, state=current.current_state, level="ERROR", message=str(safe_error)))
            raise safe_error from None
        current = await engine._transition(current, PipelineState.PR_CREATED)
        await engine._publish(LogEvent(
            job_id=job_id, state=current.current_state, level="INFO",
            message=f"GitHub confirmed pull request: {confirmed.html_url}",
            data=PRLogData(title=confirmed.title, body=confirmed.body, branch=confirmed.head.ref),
        ))
        return current
