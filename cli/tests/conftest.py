import pytest

from be.config import SETTINGS


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point be at a scratch config file and clear setting env vars."""
    path = tmp_path / "be" / "config"
    monkeypatch.setenv("BE_CONFIG", str(path))
    for s in SETTINGS.values():
        monkeypatch.delenv(s.env, raising=False)
    return path
