"""SecretStore adapters.

KeyringSecretStore wraps the OS keychain (macOS Keychain, Secret Service, etc.) so broker
credentials never live in the repo, config, or database (SYSTEM_DESIGN §8.3). The backend
is injectable for testing. InMemorySecretStore is a non-persistent dev/test implementation.
"""

from __future__ import annotations

import contextlib
from typing import Protocol


class _KeyringBackend(Protocol):
    def get_password(self, service: str, name: str) -> str | None: ...
    def set_password(self, service: str, name: str, value: str) -> None: ...
    def delete_password(self, service: str, name: str) -> None: ...


class KeyringSecretStore:
    def __init__(
        self, service: str = "quant-pilot", backend: _KeyringBackend | None = None
    ) -> None:
        if backend is None:
            import keyring  # imported lazily so tests can inject a fake backend

            backend = keyring
        self._backend = backend
        self.service = service

    def get_secret(self, name: str) -> str | None:
        return self._backend.get_password(self.service, name)

    def set_secret(self, name: str, value: str) -> None:
        self._backend.set_password(self.service, name, value)

    def delete_secret(self, name: str) -> None:
        # keyring raises if the entry is absent; deletion is idempotent here.
        with contextlib.suppress(Exception):
            self._backend.delete_password(self.service, name)


class InMemorySecretStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get_secret(self, name: str) -> str | None:
        return self._store.get(name)

    def set_secret(self, name: str, value: str) -> None:
        self._store[name] = value

    def delete_secret(self, name: str) -> None:
        self._store.pop(name, None)
