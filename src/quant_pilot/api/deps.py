"""FastAPI dependency providers — wire concrete adapters to port-typed dependencies.

Return types are the port Protocols, so mypy verifies each adapter conforms to its port
here (structural conformance check at the composition root).
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from quant_pilot.adapters.artifacts.local_store import LocalArtifactStore
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
