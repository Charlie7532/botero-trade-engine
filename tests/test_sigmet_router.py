"""
Unit and integration tests for Market SIGMET REST API Router (/api/sigmet)
"""
import pytest
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_api_sigmet_vix_endpoint():
    """Verify GET /api/sigmet/vix returns structured VIX SIGMET JSON."""
    response = client.get("/api/sigmet/vix")
    assert response.status_code == 200
    data = response.json()
    assert "sigmet_id" in data
    assert data["sigmet_id"].startswith("SIGMET-VIX-")
    assert "timestamp_utc" in data
    assert "as_of_date" in data
    assert "vix_index_value" in data


def test_api_sigmet_vvix_endpoint():
    """Verify GET /api/sigmet/vvix returns structured VVIX SIGMET JSON."""
    response = client.get("/api/sigmet/vvix")
    assert response.status_code == 200
    data = response.json()
    assert "sigmet_id" in data
    assert data["sigmet_id"].startswith("SIGMET-VVIX-")


def test_api_sigmet_pcr_endpoint():
    """Verify GET /api/sigmet/pcr returns structured PCR SIGMET JSON."""
    response = client.get("/api/sigmet/pcr")
    assert response.status_code == 200
    data = response.json()
    assert "sigmet_id" in data
    assert data["sigmet_id"].startswith("SIGMET-PCR-")


def test_api_sigmet_fg_endpoint():
    """Verify GET /api/sigmet/fg returns structured FG SIGMET JSON."""
    response = client.get("/api/sigmet/fg")
    assert response.status_code == 200
    data = response.json()
    assert "sigmet_id" in data
    assert data["sigmet_id"].startswith("SIGMET-FG-")


def test_api_sigmet_sv5_turbulence_endpoint():
    """Verify GET /api/sigmet/sv5-turbulence returns structured SV5_TURBULENCE SIGMET JSON."""
    response = client.get("/api/sigmet/sv5-turbulence")
    assert response.status_code == 200
    data = response.json()
    assert "sigmet_id" in data
    assert data["sigmet_id"].startswith("SIGMET-TURB-")
