import pytest
from autoskill.core.config import get_settings


@pytest.fixture(autouse=True)
def isolate_settings_env_file(monkeypatch):
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
