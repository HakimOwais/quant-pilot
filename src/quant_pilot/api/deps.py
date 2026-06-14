"""FastAPI dependency providers — wire concrete adapters to port-typed dependencies.

Return types are the port Protocols, so mypy verifies each adapter conforms to its port
here (structural conformance check at the composition root).
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from quant_pilot.adapters.artifacts.local_store import LocalArtifactStore
from quant_pilot.adapters.data.parquet_cache import OHLCVCache
from quant_pilot.adapters.data.yfinance_provider import YFinanceMarketDataProvider
from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.adapters.secrets.keyring_store import KeyringSecretStore
from quant_pilot.config.settings import get_settings
from quant_pilot.db.session import get_db
from quant_pilot.domain import ports


def get_repository(session: Session = Depends(get_db)) -> ports.Repository:
    return SqlAlchemyRepository(session)


def get_artifact_store() -> ports.ArtifactStore:
    return LocalArtifactStore(get_settings().artifacts_dir)


def get_secret_store() -> ports.SecretStore:
    return KeyringSecretStore()


def get_market_data_provider(
    repository: ports.Repository = Depends(get_repository),
) -> ports.MarketDataProvider:
    return YFinanceMarketDataProvider(repository, OHLCVCache(get_settings().data_dir))


def get_job_queue() -> ports.JobQueue:
    from quant_pilot.workers.queue import RqJobQueue

    return RqJobQueue()
