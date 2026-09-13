"""PDX-RoadStar FastAPI Application."""
from __future__ import annotations
import os
import sys
import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Add packages and simulator to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE_DIR, "packages"))
sys.path.insert(0, os.path.join(BASE_DIR, "simulator"))

from roadstar_domain.data_loader import load_dataset
from roadstar_domain.geofence_engine import SOUTHERN_ONTARIO_GEOFENCES
from roadstar_domain.matching_engine import match_backhaul_and_audit
from roadstar_adapter_pdx.dispatch_workflow import DispatchWorkflowEngine
from roadstar_adapter_prodocux.detention_dossier import DetentionDossierBuilder
from truck_simulator import TelematicsSimulator
from dual_track_simulator import DualTrackSimulator
from roadstar_application.scenario_comparison import ScenarioComparison
from roadstar_domain.fleet_scenario_indexer import get_available_dates

app = FastAPI(
    title="PDX-RoadStar Dispatch & Detention Evidence Cockpit",
    version="0.1.0",
    description="Autonomous Dispatch & Verifiable Detention Evidence Engine powered by ProDocuX and PDX Artifact Engine."
)

PUBLIC_DEMO = os.environ.get("ROADSTAR_PUBLIC_DEMO", "false").lower() in {"1", "true", "yes"}
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ROADSTAR_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


def require_private_api() -> None:
    """Hide source-record and legacy control endpoints on the public demo."""
    if PUBLIC_DEMO:
        raise HTTPException(status_code=404, detail="Not found")


def public_demo_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Remove source identifiers while preserving simulation/accounting values."""
    if not PUBLIC_DEMO:
        return state
    result = deepcopy(state)

    def alias(prefix: str, value: Any) -> str:
        digest = hashlib.sha256(f"roadstar-public:{value}".encode("utf-8")).hexdigest()[:8]
        return f"{prefix}-{digest.upper()}"

    truck_aliases: Dict[str, str] = {}
    for lane in ("baseline", "pdx"):
        for truck in result.get(lane, {}).get("active_trucks", []):
            source_truck = str(truck.get("id", "unknown"))
            public_truck = truck_aliases.setdefault(
                source_truck, alias("TRK", source_truck)
            )
            truck["id"] = public_truck
            if truck.get("driver"):
                truck["driver"] = alias("DRV", truck["driver"])

    for intervention in result.get("interventions", []):
        source_truck = str(intervention.get("truck", "unknown"))
        intervention["truck"] = truck_aliases.get(
            source_truck, alias("TRK", source_truck)
        )
        intervention.pop("bill_number", None)
        if intervention.get("type") == "PDX_BACKHAUL_MATCH":
            intervention["desc"] = "Engine completed eligible source backhaul"
    return result

# Shared State
DATA_DIR = os.path.join(BASE_DIR, "data")
DOSSIER_DIR = os.path.join(BASE_DIR, "artifacts", "dossiers")
os.makedirs(DOSSIER_DIR, exist_ok=True)

print("Loading dataset from Excel...")
all_drivers, all_orders = load_dataset()
print(f"Loaded {len(all_drivers)} drivers and {len(all_orders)} orders.")

simulator = TelematicsSimulator(all_drivers[:10])
pdx_workflow = DispatchWorkflowEngine()
dual_simulator = ScenarioComparison('2026-08-14')


class TickRequest(BaseModel):
    elapsed_minutes: float = 5.0


class DelayToggleRequest(BaseModel):
    delayed: bool = True


class PlanRequest(BaseModel):
    bill_number: str


class ApproveRequest(BaseModel):
    run_id: str
    approver_email: str = "dispatcher@roadstar.ca"


class GenerateDossierRequest(BaseModel):
    record_id: str


@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "pdx-roadstar",
        "prodocux": "0.3.0rc4",
        "pdx_artifact_engine": "0.3.0a5",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/geofences")
def get_geofences():
    return [gf.model_dump() for gf in SOUTHERN_ONTARIO_GEOFENCES]


@app.get("/api/fleet")
def get_fleet():
    require_private_api()
    sim_state = simulator.get_state()
    return {
        "sim_time": sim_state["sim_time"],
        "trucks": sim_state["trucks"],
        "total_drivers": len(all_drivers),
        "available_drivers_count": len([d for d in all_drivers if d.status == "AVAIL"])
    }


@app.get("/api/orders")
def get_orders(limit: int = 50):
    require_private_api()
    return [o.model_dump() for o in all_orders[:limit]]


@app.post("/api/dispatch/recommend")
def recommend_backhaul(req: PlanRequest):
    require_private_api()
    outbound = next((o for o in all_orders if o.bill_number == req.bill_number), None)
    if not outbound:
        raise HTTPException(status_code=404, detail="Order not found")

    match_result = match_backhaul_and_audit(
        outbound_order=outbound,
        candidate_orders=all_orders,
        available_drivers=[d for d in all_drivers if d.status == "AVAIL"]
    )
    return match_result.model_dump()


@app.post("/api/dispatch/create-plan")
def create_dispatch_plan(req: PlanRequest):
    require_private_api()
    outbound = next((o for o in all_orders if o.bill_number == req.bill_number), None)
    if not outbound:
        raise HTTPException(status_code=404, detail="Order not found")

    match_result = match_backhaul_and_audit(
        outbound_order=outbound,
        candidate_orders=all_orders,
        available_drivers=[d for d in all_drivers if d.status == "AVAIL"]
    )

    plan_entry = pdx_workflow.create_dispatch_plan(match_result)
    return plan_entry


@app.post("/api/dispatch/approve")
def approve_dispatch_plan(req: ApproveRequest):
    require_private_api()
    try:
        res = pdx_workflow.approve_plan(req.run_id, req.approver_email)
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/dispatch/plans")
def list_dispatch_plans():
    require_private_api()
    return list(pdx_workflow.active_plans.values())


@app.get("/api/detention/records")
def get_detention_records():
    require_private_api()
    # Sync with simulator's active records
    sim_state = simulator.get_state()
    return {
        "active_detentions": sim_state["active_detentions"],
        "all_records": [r.model_dump() for r in simulator.detention_history]
    }


@app.post("/api/detention/generate-dossier")
def generate_detention_dossier(req: GenerateDossierRequest):
    require_private_api()
    record = next((r for r in simulator.detention_history if r.record_id == req.record_id), None)
    if not record:
        raise HTTPException(status_code=404, detail=f"Detention record {req.record_id} not found.")

    pdf_path = DetentionDossierBuilder.generate_dossier_pdf(record, DOSSIER_DIR)
    record.status = "DISPUTE_SECURED"

    return {
        "record_id": record.record_id,
        "filename": record.dossier_filename,
        "sha256": record.dossier_sha256,
        "download_url": f"/api/detention/download/{record.record_id}",
        "total_fee_cad": record.total_detention_fee_cad,
        "billable_hours": record.billable_hours
    }


@app.get("/api/detention/download/{record_id}")
def download_dossier(record_id: str):
    require_private_api()
    record = next((r for r in simulator.detention_history if r.record_id == record_id), None)
    if not record or not record.dossier_filename:
        raise HTTPException(status_code=404, detail="Dossier PDF not generated yet.")

    pdf_path = os.path.join(DOSSIER_DIR, record.dossier_filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found on disk.")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=record.dossier_filename
    )


@app.post("/api/simulator/tick")
def simulator_tick(req: TickRequest):
    require_private_api()
    try:
        state = simulator.tick(req.elapsed_minutes)
        return state
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/simulator/delay-401")
def toggle_hwy401_delay(req: DelayToggleRequest):
    require_private_api()
    simulator.trigger_hwy401_incident(req.delayed)
    return {"is_delayed_hwy401": req.delayed, "state": simulator.get_state()}


@app.post("/api/simulator/release-dock/{truck_id}")
def release_dock(truck_id: str):
    require_private_api()
    simulator.release_dock_dwell(truck_id)
    return simulator.get_state()


@app.get("/api/analysis/benchmark")
def get_benchmark_analysis():
    state = dual_simulator.get_state()
    base, pdx, deltas = state["baseline"], state["pdx"], state["deltas"]
    return {
        "region": "Scenario comparison",
        "target_date": state["target_date"],
        "provisional": not state["is_finished"],
        "dataset_scope": {"total_orders_on_day": state["legs_count"], "total_freight_miles": base["total_miles"], "corridor_coverage": "Dataset locations"},
        "baseline_manual": {"deadhead_ratio_pct": base["deadhead_pct"], "wasted_empty_miles": base["empty_miles"], "modeled_empty_mile_cost_cad": round(base["empty_miles"] * 1.85, 2), "unbilled_detention_hours": base["unbilled_detention_hours"], "modeled_freight_value_cad": base["freight_revenue"], "modeled_operating_cost_cad": base["running_cost"], "contribution_margin_cad": base["net_profit"]},
        "with_pdx_optimization": {"deadhead_ratio_pct": pdx["deadhead_pct"], "empty_miles": pdx["empty_miles"], "empty_miles_saved": deltas["empty_miles_saved"], "modeled_fuel_cost_savings_cad": 0.0, "documented_detention_claim_cad": deltas["detention_gain_cad"], "source_backhaul_revenue_cad": deltas["new_backhaul_revenue_cad"], "added_operating_cost_cad": deltas["added_operating_cost_cad"], "modeled_freight_value_cad": pdx["freight_revenue"], "modeled_operating_cost_cad": pdx["running_cost"], "projected_contribution_margin_cad": pdx["net_profit"], "projected_contribution_delta_cad": deltas["net_profit_delta_cad"]},
        "backhaul_data_status": state["backhaul_data_status"],
        "notes": ["Loaded-mile value and operating cost are simulation assumptions, not source invoices.", "Detention is a documented claim with collection pending.", "Only completed Engine and passed Kernel outcomes are credited."]}


class DualTickRequest(BaseModel):
    elapsed_minutes: float = 5.0


class DualConfigRequest(BaseModel):
    enable_stochastic: Optional[bool] = None
    target_date: Optional[str] = None


@app.get("/api/simulator/dual/state")
def get_dual_state():
    return public_demo_state(dual_simulator.get_state())


@app.post("/api/simulator/dual/tick")
def tick_dual_simulator(req: DualTickRequest):
    try:
        return public_demo_state(dual_simulator.tick(req.elapsed_minutes))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/simulator/dual/reset")
def reset_dual_simulator():
    dual_simulator.reset()
    return public_demo_state(dual_simulator.get_state())


@app.get("/api/simulator/dates")
def list_simulator_dates():
    return get_available_dates()


@app.post("/api/simulator/dual/config")
def config_dual_simulator(req: DualConfigRequest):
    global dual_simulator
    if req.target_date is not None and req.target_date != dual_simulator.target_date_str:
        dual_simulator = ScenarioComparison(req.target_date)
    elif req.enable_stochastic is not None:
        dual_simulator.simulator.enable_stochastic = req.enable_stochastic
    return public_demo_state(dual_simulator.get_state())


@app.get("/api/scenario/artifacts/{filename}")
def download_scenario_artifact(filename: str):
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = dual_simulator.root / "dossiers" / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, media_type="application/pdf", filename=safe_name)


RECEIPT_DIR = os.path.join(BASE_DIR, "artifacts", "receipts")
os.makedirs(RECEIPT_DIR, exist_ok=True)


@app.get("/api/artifacts/download/{filename}")
def download_artifact(filename: str):
    require_private_api()
    # Check dossiers directory
    pdf_path = os.path.join(DOSSIER_DIR, filename)
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf", filename=filename)

    # Check receipts directory
    json_path = os.path.join(RECEIPT_DIR, filename)
    if os.path.exists(json_path):
        return FileResponse(json_path, media_type="application/json", filename=filename)

    raise HTTPException(status_code=404, detail=f"Artifact {filename} not found.")


@app.get("/api/artifacts/list")
def list_artifacts():
    require_private_api()
    import glob
    dossiers = [os.path.basename(f) for f in glob.glob(os.path.join(DOSSIER_DIR, "*.pdf"))]
    receipts = [os.path.basename(f) for f in glob.glob(os.path.join(RECEIPT_DIR, "*.json"))]
    return {
        "dossiers": dossiers,
        "receipts": receipts,
        "total_artifacts": len(dossiers) + len(receipts)
    }

from fastapi.staticfiles import StaticFiles

WEB_DIST_DIR = os.path.join(BASE_DIR, "apps", "web", "dist")
if os.path.exists(WEB_DIST_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIST_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
