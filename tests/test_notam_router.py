"""
Unit and integration tests for Operational Market NOTAM REST API Router (/api/notam)
"""
import pytest
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_api_notam_incidents_endpoint():
    """Verify GET /api/notam/incidents returns a list of operational NOTAM bulletins."""
    response = client.get("/api/notam/incidents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_api_notam_circuit_breaker_endpoint():
    """Verify GET /api/notam/circuit-breaker returns circuit breaker status."""
    response = client.get("/api/notam/circuit-breaker")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data or "notam_id" in data
