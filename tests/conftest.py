"""
Utilidades compartidas para los tests: ajustes de ruta, dobles de red (sin tocar
Internet) y fixtures. Toda la batería es OFFLINE: comprueba la lógica, no las APIs.
"""

import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from osintlib.modules.base import Context  # noqa: E402
from osintlib.utils import get_logger       # noqa: E402

_UNSET = object()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Anula time.sleep para que los tests no esperen de verdad."""
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)


class FakeResponse:
    """Respuesta HTTP simulada."""

    def __init__(self, status_code=200, json_data=_UNSET, content=b"", text=""):
        self.status_code = status_code
        self._json = json_data
        self.content = content or (text.encode("utf-8") if text else b"")
        self._text = text

    def json(self):
        if self._json is _UNSET:
            raise ValueError("sin JSON")
        return self._json

    @property
    def text(self):
        return self._text or (self.content.decode("utf-8", "replace") if self.content else "")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Sesión HTTP simulada: delega en un handler(url, **kw) -> FakeResponse."""

    def __init__(self, handler=None):
        self.handler = handler or (lambda url, **kw: FakeResponse(404))
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return self.handler(url, **kw)


@pytest.fixture
def fake_response():
    return FakeResponse


@pytest.fixture
def fake_session():
    return FakeSession


@pytest.fixture
def ctx_factory():
    """Crea un Context con sesión simulada y settings a medida."""
    def _make(session=None, settings=None):
        return Context(config={"settings": settings or {}, "api_keys": {}},
                       session=session or FakeSession(), logger=get_logger("test"))
    return _make
