"""
Unit and integration tests for Market NOTAM REST API Router (/api/notam)
"""
import pytest
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_api_notam_vix_endpoint():
    """Verify GET /api/notam/vix returns structured VIX NOTAM JSON."""
    response = client.get("/api/notam/vix")
    assert response.status_code == 200
    data = response.json()
    assert "notam_id" in data
    assert data["notam_id"].startswith("NOTAM-VIX-")
    assert "timestamp_utc" in data
    assert "as_of_date" in data
    assert "vix_index_value" in data
    assert "primary_capital_velocity" in data


def test_api_notam_vix_strict_zero_fallback():
    """Verify GET /api/notam/vix with invalid date returns 404 under Strict Data Policy."""
    response = client.get("/api/notam/vix?as_of_date=1900-01-01")
    assert response.status_code == 404
    detail = response.json().get("detail", "")
    assert "NOTAM NOT AVAILABLE" in detail


def test_api_notam_vvix_endpoint():
    """Verify GET /api/notam/vvix returns structured VVIX NOTAM JSON."""
    response = client.get("/api/notam/vvix")
    assert response.status_code == 200
    data = response.json()
    assert "notam_id" in data
    assert data["notam_id"].startswith("NOTAM-VVIX-")
    assert "timestamp_utc" in data
    assert "as_of_date" in data
    assert "vvix_index_value" in data
    assert "primary_capital_velocity" in data


def test_api_notam_vvix_strict_zero_fallback():
    """Verify GET /api/notam/vvix with invalid date returns 404 under Strict Data Policy."""
    response = client.get("/api/notam/vvix?as_of_date=1900-01-01")
    assert response.status_code == 404
    detail = response.json().get("detail", "")
    assert "NOTAM NOT AVAILABLE" in detail

