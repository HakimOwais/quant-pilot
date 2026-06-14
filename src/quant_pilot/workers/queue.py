"""Job queue: the JobQueue port adapters (RQ for real, in-memory for dev/tests) + helpers."""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any
from uuid import uuid4

import redis
from rq import Queue

from quant_pilot.config.settings import get_settings
from quant_pilot.domain.models import JobStatus

_TERMINAL = {"finished", "failed", "unknown"}


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


@lru_cache
def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis())


def _import_string(path: str) -> Any:
    module, _, attr = path.rpartition(".")
    return getattr(importlib.import_module(module), attr)


class RqJobQueue:
    """Production JobQueue backed by RQ + Redis."""

    def __init__(self, queue_name: str = "default") -> None:
        self._queue = get_queue(queue_name)

    def enqueue(self, func: str, *args: Any, **kwargs: Any) -> str:
        return str(self._queue.enqueue(func, *args, **kwargs).id)

    def status(self, job_id: str) -> JobStatus:
        from rq.job import Job

        try:
            job = Job.fetch(job_id, connection=get_redis())
            return JobStatus(
                id=job_id,
                status=str(job.get_status()),
                result=job.result,
                error=str(job.exc_info) if job.exc_info else None,
            )
        except Exception:
            return JobStatus(id=job_id, status="unknown")


class InMemoryJobQueue:
    """Dev/test JobQueue. With eager=True it runs the job synchronously; otherwise it records a
    stub job marked 'finished' (no worker needed). NOT for production."""

    def __init__(self, eager: bool = False) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self.eager = eager

    def enqueue(self, func: str, *args: Any, **kwargs: Any) -> str:
        job_id = uuid4().hex
        if self.eager:
            try:
                result = _import_string(func)(*args, **kwargs)
                self._jobs[job_id] = JobStatus(id=job_id, status="finished", result=result)
            except Exception as exc:
                self._jobs[job_id] = JobStatus(id=job_id, status="failed", error=str(exc))
        else:
            self._jobs[job_id] = JobStatus(id=job_id, status="finished")
        return job_id

    def status(self, job_id: str) -> JobStatus:
        return self._jobs.get(job_id, JobStatus(id=job_id, status="unknown"))
