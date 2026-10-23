import pytest

from be import cmux
from be.config import SETTINGS


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point be at a scratch config file and clear setting env vars."""
    path = tmp_path / "be" / "config"
    monkeypatch.setenv("BE_CONFIG", str(path))
    for s in SETTINGS.values():
        monkeypatch.delenv(s.env, raising=False)
    return path


@pytest.fixture(autouse=True)
def nothing_open_in_cmux(monkeypatch):
    """Treat every workspace as not yet open, so tests needn't stub cmux's listings."""
    monkeypatch.setattr(cmux, "focus_existing", lambda binary, title: False)
