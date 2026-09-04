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


def test_api_notam_report_endpoint():
    """Verify GET /api/notam/report returns full operational report with station telemetry."""
    response = client.get("/api/notam/report")
    assert response.status_code == 200
    data = response.json()
    assert "report_id" in data
    assert "overall_status" in data
    assert "station_telemetry" in data
    assert "outdated_stations" in data
    assert isinstance(data["station_telemetry"], list)
    # Check that BSI is among the evaluated stations
    stations = [s["station"] for s in data["station_telemetry"]]
    assert "BSI" in stations
    assert "SPY" in stations


def test_api_notam_outdated_stations_endpoint():
    """Verify GET /api/notam/outdated-stations returns outdated station audit."""
    response = client.get("/api/notam/outdated-stations")
    assert response.status_code == 200
    data = response.json()
    assert "benchmark_station" in data
    assert "outdated_stations" in data
    assert isinstance(data["outdated_stations"], list)
