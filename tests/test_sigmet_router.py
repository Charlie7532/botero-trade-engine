"""
Unit and integration tests for Severe Weather Market SIGMET REST API Router (/api/sigmet)
"""
import pytest
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_api_sigmet_active_endpoint():
    """Verify GET /api/sigmet/active returns structured severe hazard payload."""
    response = client.get("/api/sigmet/active")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ("CLEAR", "HAZARD_WARNING")
    assert "active_sigmet_count" in data
    assert "sigmets" in data
