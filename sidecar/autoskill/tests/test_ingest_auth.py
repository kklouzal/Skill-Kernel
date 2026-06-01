import pytest
from autoskill.api.app import _require_ingest_auth
from autoskill.core.config import get_settings
from fastapi import HTTPException


def test_ingest_auth_allows_unconfigured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTOSKILL_INGEST_TOKEN", raising=False)
    get_settings.cache_clear()

    _require_ingest_auth(None)

    get_settings.cache_clear()


def test_ingest_auth_rejects_invalid_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOSKILL_INGEST_TOKEN", "expected")
    get_settings.cache_clear()

    with pytest.raises(HTTPException):
        _require_ingest_auth("Bearer wrong")

    get_settings.cache_clear()


def test_ingest_auth_accepts_matching_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOSKILL_INGEST_TOKEN", "expected")
    get_settings.cache_clear()

    _require_ingest_auth("Bearer expected")

    get_settings.cache_clear()
