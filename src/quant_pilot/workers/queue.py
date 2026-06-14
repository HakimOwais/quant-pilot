"""Job queue helpers (RQ + Redis). Cached connection + queue accessors."""

from __future__ import annotations

from functools import lru_cache

import redis
from rq import Queue

from quant_pilot.config.settings import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


@lru_cache
def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis())
