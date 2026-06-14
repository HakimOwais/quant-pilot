"""Job endpoints: status and an SSE progress stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from quant_pilot.api.deps import get_job_queue
from quant_pilot.domain import ports
from quant_pilot.domain.models import JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TERMINAL = {"finished", "failed", "unknown"}
_MAX_EVENTS = 600  # ~10 min at 1s; the stream ends earlier on a terminal status


@router.get("/{job_id}", response_model=JobStatus)
def get_job(job_id: str, queue: ports.JobQueue = Depends(get_job_queue)) -> JobStatus:
    return queue.status(job_id)


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: str, queue: ports.JobQueue = Depends(get_job_queue)
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        for _ in range(_MAX_EVENTS):
            status = queue.status(job_id)
            yield f"data: {status.model_dump_json()}\n\n"
            if status.status in _TERMINAL:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(events(), media_type="text/event-stream")
