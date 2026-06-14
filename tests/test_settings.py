from __future__ import annotations

from quant_pilot.config.settings import Settings


def test_cors_origins_parses_csv_env(monkeypatch):
    # regression: pydantic-settings must NOT JSON-decode this env value (NoDecode);
    # a comma-separated string is parsed by the field validator.
    monkeypatch.setenv("QP_CORS_ORIGINS", "http://localhost:3000,http://example.com")
    s = Settings()
    assert s.cors_origins == ["http://localhost:3000", "http://example.com"]


def test_cors_origins_default_is_list():
    assert isinstance(Settings().cors_origins, list)


def test_prod_rejects_insecure_secret(monkeypatch):
    import pytest

    monkeypatch.setenv("QP_ENV", "prod")
    monkeypatch.delenv("QP_SESSION_SECRET", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]
