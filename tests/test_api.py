import pytest
from fastapi.testclient import TestClient
import sys

sys.path.insert(0, r"d:\ProDocuX\prodocux-labs\incubator\pdx-roadstar\apps\api")
from main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["prodocux"] == "0.3.0rc4"
    assert data["pdx_artifact_engine"] == "0.3.0a5"
    assert data["service"] == "pdx-roadstar"


def test_get_geofences():
    res = client.get("/api/geofences")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 8
    cities = [gf["city"] for gf in data]
    assert "Milton" in cities
    assert "London" in cities


def test_get_fleet_and_tick():
    res = client.get("/api/fleet")
    assert res.status_code == 200
    data = res.json()
    assert "trucks" in data
    assert len(data["trucks"]) >= 3

    # Tick simulation
    tick_res = client.post("/api/simulator/tick", json={"elapsed_minutes": 10.0})
    assert tick_res.status_code == 200
    tick_data = tick_res.json()
    assert "trucks" in tick_data


def test_dual_simulator_can_switch_operational_date():
    response = client.post("/api/simulator/dual/config", json={"target_date": "2026-08-27"})
    assert response.status_code == 200
    state = response.json()
    assert state["target_date"] == "2026-08-27"
    assert state["sim_minute"] == 0
    assert state["baseline"]["active_trucks"] == []
    assert state["backhaul_data_status"]["revenue_eligible"] is False


def test_dispatch_is_blocked_without_source_priced_orders():
    # Tlorder has no freight-rate field. The API must expose no fabricated
    # commercial candidates and must reject an unknown bill explicitly.
    orders_res = client.get("/api/orders?limit=20")
    assert orders_res.status_code == 200
    orders = orders_res.json()
    assert orders == []
    rec_res = client.post("/api/dispatch/recommend", json={"bill_number": "409028"})
    assert rec_res.status_code == 404


def test_generate_detention_dossier_and_download():
    # 1. Get detention records
    rec_res = client.get("/api/detention/records")
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert len(rec_data["all_records"]) > 0
    target_rec = rec_data["all_records"][0]
    rec_id = target_rec["record_id"]

    # 2. Generate PDF dossier
    gen_res = client.post("/api/detention/generate-dossier", json={"record_id": rec_id})
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["record_id"] == rec_id
    assert len(gen_data["sha256"]) == 64

    # 3. Download PDF
    dl_res = client.get(f"/api/detention/download/{rec_id}")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/pdf"
    assert len(dl_res.content) > 1000
