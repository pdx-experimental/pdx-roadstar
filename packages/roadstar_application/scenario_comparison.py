"""Connect scenario events to autonomous PDX operations without coupling them."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import uuid

from roadstar_adapter_pdx.dispatch_workflow import DispatchWorkflowEngine
from roadstar_adapter_prodocux.detention_dossier import DetentionDossierBuilder
from roadstar_domain.data_loader import load_dataset
from roadstar_domain.geo_routing import estimate_corridor_road_miles
from roadstar_domain.matching_engine import match_backhaul_and_audit
from roadstar_domain.models import BackhaulMatchResult, DetentionRecord, OrderModel
from roadstar_domain.resource_manager import FleetResourceManager
from dual_track_simulator import FleetSimulator


class ScenarioComparison:
    """Application coordinator: simulation events in, PDX outcomes out.

    FleetSimulator has no imports from this package, Kernel, or Engine. This
    service observes its clock and invokes the public packages automatically.
    """

    def __init__(self, target_date="2026-08-14", *, storage_dir: Path | None = None):
        root = Path(storage_dir or Path(__file__).resolve().parents[2] / "artifacts" / "scenario-runs")
        root.mkdir(parents=True, exist_ok=True)
        self.simulator = FleetSimulator(target_date, enable_stochastic=False)
        self.drivers, self.orders = load_dataset()
        self.base_root = root
        self._start_operation_session()
        self.reset_operations()

    @property
    def target_date_str(self) -> str:
        return self.simulator.target_date_str

    def _start_operation_session(self):
        self.root = self.base_root / f"session-{uuid.uuid4().hex}"
        self.resource_manager = FleetResourceManager(self.root / "fleet")
        self.workflow = DispatchWorkflowEngine(self.root / "engine", self.resource_manager)
        self.dossiers = DetentionDossierBuilder(self.root / "dossiers")

    def reset_operations(self):
        self.processed: set[str] = set()
        self.claimed_bills: set[str] = set()
        self.outcomes: dict[str, dict[str, Any]] = {}
        self.interventions: list[dict[str, Any]] = []

    def reset(self):
        # A replay creates a new comparison projection. Durable Engine resources
        # are intentionally not erased by a playback control.
        self.simulator.reset()
        self._start_operation_session()
        self.reset_operations()
        return self.get_state()

    def tick(self, elapsed_minutes: float):
        state = self.simulator.tick(elapsed_minutes)
        self._process_due_events(state["sim_minute"])
        return self.get_state()

    def _process_due_events(self, minute: float):
        due_events = []
        for index, leg in enumerate(self.simulator.legs):
            backhaul_key = f"backhaul:{leg['leg_id']}"
            if leg["is_empty"] and leg["start_min"] <= minute and backhaul_key not in self.processed:
                due_events.append((leg["start_min"], 0, index, backhaul_key, self._dispatch_backhaul, leg))
            dossier_key = f"dossier:{leg['leg_id']}"
            due = leg["end_min"] + leg["dwell"] * 60
            if leg["dwell"] > 2 and due <= minute and dossier_key not in self.processed:
                due_events.append((due, 1, index, dossier_key, self._create_dossier, leg))
        # Event order depends on scenario time, never on UI tick size.
        for _, _, index, key, handler, leg in sorted(due_events, key=lambda row: row[:3]):
            self.processed.add(key)
            handler(index, leg)

    def _event_time(self, minute):
        return (datetime.fromisoformat(self.simulator.target_date_str).replace(
            hour=6, tzinfo=timezone.utc) + timedelta(minutes=minute))

    def _dispatch_backhaul(self, index, leg):
        outbound = OrderModel(
            bill_number=leg["leg_id"], trip_number=leg["leg_id"], customer_name="Scenario outbound",
            origin_city=leg["orig"].split(",")[0], origin_prov="ON", origin_pc="",
            dest_city=leg["dest"].split(",")[0], dest_prov="ON", dest_pc="",
            distance_miles=leg["dist"], weight_lbs=32000, rate_cad=leg["dist"] * 2.85)
        arrival = self._event_time(leg["end_min"])
        match = match_backhaul_and_audit(outbound, self.orders,
            [d for d in self.drivers if d.status == "AVAIL"], self.claimed_bills, arrival)
        if not (match.return_order and match.hos_audit_passed and match.weight_audit_passed):
            return
        try:
            plan = self.workflow.create_dispatch_plan(match, truck_id=leg["id"],
                start_time=self._event_time(leg["start_min"]),
                duration_hours=(leg["end_min"] - leg["start_min"]) / 60)
            completed = self.workflow.approve_and_execute_plan(plan["run_id"], "scenario-policy@roadstar.local")
        except Exception as exc:
            self.interventions.insert(0, {"type": "PDX_BACKHAUL_ABORTED", "truck": leg["id"],
                "time": self.simulator.get_state()["sim_clock"], "desc": str(exc),
                "financial_delta": "$0.00 CAD", "filename": "", "download_url": ""})
            return
        if completed.get("status") != "completed":
            return
        returned = match.return_order
        self.claimed_bills.add(returned.bill_number)
        repo = estimate_corridor_road_miles(outbound.dest_city, returned.origin_city)
        post = estimate_corridor_road_miles(returned.dest_city, outbound.origin_city)
        self.outcomes[leg["leg_id"]] = {"kind": "backhaul", "saved_empty_miles": match.empty_miles_saved,
            "repo_miles": repo, "post_repo_miles": post, "return_miles": returned.distance_miles,
            "revenue": returned.rate_cad, "run_id": completed["run_id"],
            "bill_number": returned.bill_number}
        self.interventions.insert(0, {"type": "PDX_BACKHAUL_MATCH", "truck": leg["id"],
            "time": self.simulator.get_state()["sim_clock"],
            "desc": f"Engine completed bill {returned.bill_number}: {returned.origin_city} → {returned.dest_city}",
            "financial_delta": f"+${returned.rate_cad:,.2f} CAD freight", "run_id": completed["run_id"],
            "bill_number": returned.bill_number,
            "filename": "", "download_url": ""})

    def _create_dossier(self, index, leg):
        arrived = self._event_time(leg["end_min"])
        fee = round((leg["dwell"] - 2) * 95, 2)
        safe_leg_id = leg["leg_id"].replace(":", "-")
        record = DetentionRecord(record_id=f"DET-{safe_leg_id}", trip_number=safe_leg_id,
            bill_number=safe_leg_id, driver_id=index + 1, driver_name=leg["driver"],
            facility_id=f"FAC-{index}", facility_name=leg["dest"],
            geofence_arrival_time=arrived, geofence_departure_time=arrived + timedelta(hours=leg["dwell"]),
            total_wait_hours=leg["dwell"], billable_hours=leg["dwell"] - 2,
            hourly_rate_cad=95, total_detention_fee_cad=fee)
        try:
            pdf, audit = self.dossiers.generate_and_audit_dossier(record)
        except Exception as exc:
            self.interventions.insert(0, {"type": "PRODOCUX_DOSSIER_ABORTED", "truck": leg["id"],
                "time": self.simulator.get_state()["sim_clock"], "desc": str(exc),
                "financial_delta": "$0.00 CAD", "filename": "", "download_url": ""})
            return
        if audit.get("audit_status") != "pass":
            return
        amount = float(audit["invoiced_amount_cad"])
        self.outcomes[f"dossier:{leg['leg_id']}"] = {"kind": "dossier", "amount": amount,
            "hours": leg["dwell"] - 2, "filename": Path(pdf).name}
        self.interventions.insert(0, {"type": "PRODOCUX_DETENTION_DOSSIER", "truck": leg["id"],
            "time": self.simulator.get_state()["sim_clock"], "desc": "Kernel dossier audit passed",
            "financial_delta": f"+${amount:,.2f} CAD detention", "filename": Path(pdf).name,
            "download_url": f"/api/scenario/artifacts/{Path(pdf).name}"})

    def get_state(self):
        state = self.simulator.get_state()
        baseline = state["baseline"]
        pdx_trucks = deepcopy(baseline["active_trucks"])
        saved = backhaul = detention = added_miles = 0.0
        for truck in pdx_trucks:
            outcome = self.outcomes.get(truck["leg_id"])
            if outcome:
                truck["is_empty"] = False
                truck["leg_type"] = "PDX Backhaul Executed"
                saved += outcome["saved_empty_miles"]
                backhaul += outcome["revenue"]
                added_miles += outcome["repo_miles"] + outcome["return_miles"] + outcome["post_repo_miles"] - truck["dist"]
        for outcome in self.outcomes.values():
            if outcome["kind"] == "dossier":
                detention += outcome["amount"]
        pdx_total = max(0, baseline["total_miles"] + added_miles)
        pdx_empty = max(0, baseline["empty_miles"] - saved)
        added_cost = round(added_miles * 1.85, 2)
        pdx_cost = round(baseline["running_cost"] + added_cost, 2)
        pdx_revenue = round(baseline["freight_revenue"] + backhaul, 2)
        contribution_delta = round(backhaul + detention - added_cost, 2)
        pdx_profit = round(baseline["net_profit"] + contribution_delta, 2)
        state.update(mode="comparison", pdx={"active_trucks": pdx_trucks,
            "total_miles": round(pdx_total, 1), "empty_miles": round(pdx_empty, 1),
            "deadhead_pct": round(pdx_empty / pdx_total * 100, 1) if pdx_total else 0,
            "freight_revenue": round(pdx_revenue, 2), "new_backhaul_revenue": round(backhaul, 2),
            "running_cost": round(pdx_cost, 2), "billed_detention_hours": round(sum(
                o["hours"] for o in self.outcomes.values() if o["kind"] == "dossier"), 2),
            "recovered_detention_revenue": round(detention, 2), "net_profit": round(pdx_profit, 2),
            "running_count": baseline["running_count"]},
            deltas={"empty_miles_saved": round(saved, 1), "fuel_saved_cad": 0.0,
                "detention_gain_cad": round(detention, 2), "new_backhaul_revenue_cad": round(backhaul, 2),
                "added_operating_cost_cad": round(added_cost, 2),
                "net_profit_delta_cad": contribution_delta,
                "interventions_count": len([i for i in self.interventions if not i["type"].endswith("ABORTED")])},
            interventions=deepcopy(self.interventions),
            backhaul_data_status={
                "eligible_source_orders": len(self.orders),
                "revenue_eligible": bool(self.orders),
                "reason": ("eligible source-priced orders available" if self.orders else
                    "Tlorder has no source freight-rate field; backhaul revenue is blocked"),
            })
        return state
