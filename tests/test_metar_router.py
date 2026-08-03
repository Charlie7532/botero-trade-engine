"""
Unit and integration tests for Market METAR REST API Router (/api/metar)
"""
import pytest
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_api_metar_vix_endpoint():
    """Verify GET /api/metar/vix returns structured VIX METAR JSON."""
    response = client.get("/api/metar/vix")
    assert response.status_code == 200
    data = response.json()
    assert "metar_id" in data
    assert data["metar_id"].startswith("METAR-VIX-")
    assert "timestamp_utc" in data
    assert "as_of_date" in data
    assert "vix_index_value" in data


def test_api_metar_vvix_endpoint():
    """Verify GET /api/metar/vvix returns structured VVIX METAR JSON."""
    response = client.get("/api/metar/vvix")
    assert response.status_code == 200
    data = response.json()
    assert "metar_id" in data
    assert data["metar_id"].startswith("METAR-VVIX-")


def test_api_metar_pcr_endpoint():
    """Verify GET /api/metar/pcr returns structured PCR METAR JSON."""
    response = client.get("/api/metar/pcr")
    assert response.status_code == 200
    data = response.json()
    assert "metar_id" in data
    assert data["metar_id"].startswith("METAR-PCR-")


def test_api_metar_fg_endpoint():
    """Verify GET /api/metar/fg returns structured FG METAR JSON."""
    response = client.get("/api/metar/fg")
    assert response.status_code == 200
    data = response.json()
    assert "metar_id" in data
    assert data["metar_id"].startswith("METAR-FG-")


def test_api_metar_sv5_turbulence_endpoint():
    """Verify GET /api/metar/sv5-turbulence returns structured SV5_TURBULENCE METAR JSON."""
    response = client.get("/api/metar/sv5-turbulence")
    assert response.status_code == 200
    data = response.json()
    assert "metar_id" in data
    assert data["metar_id"].startswith("METAR-SV5TURB-")


def test_api_metar_all_endpoint():
    """Verify GET /api/metar/all returns aggregated 9 stations dictionary."""
    response = client.get("/api/metar/all")
    assert response.status_code == 200
    data = response.json()
    assert data["registered_count"] == 9
    assert "metars" in data
