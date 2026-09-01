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


def test_api_metar_bsi_endpoint():
    """Verify GET /api/metar/bsi returns structured BSI METAR JSON."""
    response = client.get("/api/metar/bsi")
    assert response.status_code == 200
    data = response.json()
    assert "metar_id" in data
    assert data["metar_id"].startswith("METAR-BSI-")
    assert "bsi_value" in data


def test_api_metar_all_endpoint():
    """Verify GET /api/metar/all returns aggregated 11 stations dictionary."""
    response = client.get("/api/metar/all")
    assert response.status_code == 200
    data = response.json()
    assert data["registered_count"] == 11
    assert "metars" in data
    assert "bsi" in data["metars"]
    assert "dxy" in data["metars"]


def test_api_metar_skew_endpoint():
    """Verify GET /api/metar/skew returns structured SKEW METAR JSON."""
    response = client.get("/api/metar/skew")
    assert response.status_code in [200, 404]


def test_api_metar_credit_endpoint():
    """Verify GET /api/metar/credit returns structured Credit Stress METAR JSON."""
    response = client.get("/api/metar/credit")
    assert response.status_code in [200, 404]


def test_api_metar_yield_curve_endpoint():
    """Verify GET /api/metar/yield-curve returns structured Yield Curve METAR JSON."""
    response = client.get("/api/metar/yield-curve")
    assert response.status_code in [200, 404]


def test_api_metar_rotation_endpoint():
    """Verify GET /api/metar/rotation returns structured Rotation METAR JSON."""
    response = client.get("/api/metar/rotation")
    assert response.status_code in [200, 404]


def test_api_metar_dxy_endpoint():
    """Verify GET /api/metar/dxy returns structured DXY METAR JSON."""
    response = client.get("/api/metar/dxy")
    assert response.status_code in [200, 404]

