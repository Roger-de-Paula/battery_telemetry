"""Pytest fixtures. Client uses the real app; no DB override for health-only tests."""
import pytest
from starlette.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    """HTTP client for the FastAPI app (no dependency overrides)."""
    return TestClient(app)
