from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_pilot.adapters.artifacts.local_store import LocalArtifactStore
from quant_pilot.adapters.clock import FixedClock, SystemClock
from quant_pilot.adapters.secrets.keyring_store import InMemorySecretStore, KeyringSecretStore
from quant_pilot.domain import ports

# --- artifact store ---------------------------------------------------------


def test_artifact_store_conforms(tmp_path):
    assert isinstance(LocalArtifactStore(tmp_path), ports.ArtifactStore)


def test_artifact_roundtrip(tmp_path):
    store = LocalArtifactStore(tmp_path)
    ref = store.save_bytes("runs/1/data.bin", b"hello")
    assert ref.size == 5
    assert store.exists("runs/1/data.bin")
    assert store.load_bytes("runs/1/data.bin") == b"hello"

    store.save_json("runs/1/m.json", {"sharpe": 1.4})
    assert store.load_json("runs/1/m.json") == {"sharpe": 1.4}


def test_artifact_path_traversal_rejected(tmp_path):
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.save_bytes("../escape.bin", b"x")
    assert store.exists("../escape.bin") is False


# --- secret store -----------------------------------------------------------


class _FakeKeyring:
    def __init__(self):
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service, name):
        return self.data.get((service, name))

    def set_password(self, service, name, value):
        self.data[(service, name)] = value

    def delete_password(self, service, name):
        del self.data[(service, name)]


def test_inmemory_secret_store_conforms_and_roundtrips():
    store = InMemorySecretStore()
    assert isinstance(store, ports.SecretStore)
    store.set_secret("kite_api_key", "abc")
    assert store.get_secret("kite_api_key") == "abc"
    store.delete_secret("kite_api_key")
    assert store.get_secret("kite_api_key") is None


def test_keyring_store_uses_backend():
    store = KeyringSecretStore(service="qp-test", backend=_FakeKeyring())
    assert isinstance(store, ports.SecretStore)
    store.set_secret("k", "v")
    assert store.get_secret("k") == "v"
    store.delete_secret("k")  # idempotent even though entry now gone
    store.delete_secret("k")
    assert store.get_secret("k") is None


# --- clock ------------------------------------------------------------------


def test_clocks_conform():
    assert isinstance(SystemClock(), ports.Clock)
    fixed = FixedClock(datetime(2026, 6, 14, 9, 15, tzinfo=UTC))
    assert isinstance(fixed, ports.Clock)
    assert fixed.now().year == 2026
    assert fixed.today().isoformat() == "2026-06-14"
