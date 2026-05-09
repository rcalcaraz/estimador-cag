"""Pytest: variables de entorno antes de importar la app (Settings valida API keys al importar)."""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-pytest")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key-pytest")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
