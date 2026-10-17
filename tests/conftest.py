import pytest

from friday.router import model as router_model


@pytest.fixture(autouse=True)
def _router_model_off(monkeypatch):
    """No test loads torch or the router model by accident; tests that want it turn it on."""
    monkeypatch.setenv(router_model.ENV_FLAG, "0")
    monkeypatch.setattr(router_model, "_shared", {})
