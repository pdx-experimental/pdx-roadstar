from fastapi.testclient import TestClient

from apps.api import main


def test_public_demo_hides_source_record_and_legacy_control_endpoints(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_DEMO", True)
    client = TestClient(main.app)

    for path in (
        "/api/orders",
        "/api/fleet",
        "/api/dispatch/plans",
        "/api/detention/records",
        "/api/artifacts/list",
    ):
        assert client.get(path).status_code == 404

    assert client.get("/health").status_code == 200
    assert client.get("/api/simulator/dates").status_code == 200
    assert client.get("/api/simulator/dual/state").status_code == 200


def test_security_headers_are_set():
    response = TestClient(main.app).get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_public_demo_state_replaces_source_identifiers(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_DEMO", True)
    state = {
        "baseline": {"active_trucks": [{"id": "TRK-SOURCE", "driver": "Driver13"}]},
        "pdx": {"active_trucks": [{"id": "TRK-SOURCE", "driver": "Driver13"}]},
        "interventions": [{
            "type": "PDX_BACKHAUL_MATCH",
            "truck": "TRK-SOURCE",
            "bill_number": "SOURCE-BILL",
            "desc": "Engine completed bill SOURCE-BILL",
        }],
    }
    result = main.public_demo_state(state)
    public_id = result["baseline"]["active_trucks"][0]["id"]

    assert public_id.startswith("TRK-")
    assert public_id != "TRK-SOURCE"
    assert result["pdx"]["active_trucks"][0]["id"] == public_id
    assert result["baseline"]["active_trucks"][0]["driver"].startswith("DRV-")
    assert result["interventions"][0]["truck"] == public_id
    assert "bill_number" not in result["interventions"][0]
    assert "SOURCE-BILL" not in result["interventions"][0]["desc"]
