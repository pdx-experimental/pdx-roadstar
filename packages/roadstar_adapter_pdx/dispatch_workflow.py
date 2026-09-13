from __future__ import annotations
import os
import uuid
import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pdx_artifact_core import (
    ApprovalLedger,
    canonical_digest,
    create_approval_request,
    create_checkpoint,
    validate_execution_plan,
)
from pdx_artifact_engine.registry import SkillRegistry, SkillDefinition
from pdx_artifact_engine.runtime import ArtifactRuntime

from roadstar_domain.models import BackhaulMatchResult
from roadstar_domain.resource_manager import FleetResourceManager, ResourceConflictError, FileTransactionLock
from roadstar_adapter_pdx.storage_adapter import RoadStarStorageAdapter

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DISPATCH_RUNS_DIR = BASE_DIR / "acceptance" / "evidence" / "dispatch_runs"


class ExecutionLock(FileTransactionLock):
    """Adapter for the shared OS lock primitive; no recovery claims are made."""

    def __init__(self, lock_path: Path, run_id: str, timeout_sec: float = 5.0):
        super().__init__(lock_path, timeout_sec)


def _build_dispatch_skill_registry() -> SkillRegistry:
    skills = [
        SkillDefinition.from_dict({
            "name": "roadstar.reserve_fleet",
            "version": "1.0.0",
            "domain": "logistics",
            "description": "Atomically reserves truck, driver, and freight order resources",
            "entrypoint": "python:roadstar.reserve_fleet",
            "inputs": ["truck_id", "driver_id", "start_time", "end_time", "trip_id", "order_bill"],
            "outputs": ["reservation_id", "status"],
            "failure_codes": [{"code": "RESOURCE_CONFLICT", "description": "Resource already reserved"}]
        }),
        SkillDefinition.from_dict({
            "name": "roadstar.audit_compliance",
            "version": "1.0.0",
            "domain": "logistics",
            "description": "Audits driver HOS regulations and axle weight limits",
            "entrypoint": "python:roadstar.audit_compliance",
            "inputs": ["driver_id", "hos_passed", "weight_passed"],
            "outputs": ["audit_status", "compliance_token"],
            "failure_codes": [{"code": "COMPLIANCE_FAILED", "description": "HOS or weight violation"}]
        }),
        SkillDefinition.from_dict({
            "name": "roadstar.dispatch_carrier",
            "version": "1.0.0",
            "domain": "logistics",
            "description": "Confirms telematics dispatch to on-board fleet unit",
            "entrypoint": "python:roadstar.dispatch_carrier",
            "inputs": ["driver_id", "driver_name", "trips"],
            "outputs": ["dispatch_id", "status"],
            "failure_codes": [{"code": "DISPATCH_FAILED", "description": "Telematics delivery failed"}]
        })
    ]
    return SkillRegistry(skills)



class DispatchWorkflowEngine:
    """Manages dispatch execution plans, human-in-the-loop approvals, and receipts."""

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        resource_manager: Optional[FleetResourceManager] = None
    ) -> None:
        self.ledger = ApprovalLedger()
        self.storage_dir = (Path(storage_dir) if storage_dir else DISPATCH_RUNS_DIR).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage = RoadStarStorageAdapter(self.storage_dir)
        self.resource_manager = resource_manager or FleetResourceManager.get_global_manager()
        self.registry = _build_dispatch_skill_registry()

        executors = {
            "roadstar.reserve_fleet": self._exec_reserve_fleet,
            "roadstar.audit_compliance": self._exec_audit_compliance,
            "roadstar.dispatch_carrier": self._exec_dispatch_carrier,
        }
        self.runtime = ArtifactRuntime(
            registry=self.registry,
            executors=executors,
            storage=self.storage,
            allow_mock=False
        )
        self.active_plans: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _exec_reserve_fleet(self, inputs: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        truck_id = str(inputs["truck_id"])
        driver_id = str(inputs["driver_id"])
        trip_id = str(inputs["trip_id"])
        order_bill = str(inputs.get("order_bill") or "") or None
        start_t = datetime.fromisoformat(str(inputs["start_time"]))
        end_t = datetime.fromisoformat(str(inputs["end_time"]))

        slots = self.resource_manager.acquire_reservation(
            truck_id=truck_id,
            driver_id=driver_id,
            order_bill=order_bill,
            start_time=start_t,
            end_time=end_t,
            trip_id=trip_id
        )

        record = {
            "reservation_id": f"res-{trip_id}",
            "status": "reserved",
            "truck_id": truck_id,
            "driver_id": driver_id,
            "order_bill": order_bill,
            "trip_id": trip_id,
            "start_time": start_t.isoformat(),
            "end_time": end_t.isoformat(),
        }
        res_file = output_dir / "reservation.json"
        res_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {
            "result": record,
            "files": [res_file],
            "outputs": {"reservation_id": record["reservation_id"], "status": "reserved"}
        }

    def _exec_audit_compliance(self, inputs: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        hos_ok = bool(inputs.get("hos_passed", False))
        weight_ok = bool(inputs.get("weight_passed", False))
        if not (hos_ok and weight_ok):
            raise ValueError(f"Compliance violation: hos_passed={hos_ok}, weight_passed={weight_ok}")

        record = {
            "audit_status": "passed",
            "compliance_token": f"token-{inputs.get('driver_id')}-{uuid.uuid4().hex[:6]}",
            "hos_passed": True,
            "weight_passed": True,
        }
        audit_file = output_dir / "compliance_audit.json"
        audit_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {
            "result": record,
            "files": [audit_file],
            "outputs": record
        }

    def _exec_dispatch_carrier(self, inputs: dict[str, Any], output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "dispatch_id": f"disp-{uuid.uuid4().hex[:8]}",
            "status": "dispatched",
            "driver_id": str(inputs["driver_id"]),
            "driver_name": str(inputs["driver_name"]),
            "trips": list(inputs["trips"]),
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }
        dispatch_file = output_dir / "carrier_dispatch.json"
        dispatch_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {
            "result": record,
            "files": [dispatch_file],
            "outputs": record
        }

    def create_dispatch_plan(
        self,
        match_result: BackhaulMatchResult,
        truck_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        duration_hours: float = 6.0,
    ) -> Dict[str, Any]:
        run_id = f"plan-{uuid.uuid4().hex[:8]}"
        outbound = match_result.outbound_order
        ret = match_result.return_order
        actual_truck_id = truck_id or f"TRUCK-{match_result.assigned_driver_id}"
        t_start = start_time or datetime.now(timezone.utc)
        t_end = t_start + timedelta(hours=duration_hours)
        primary_trip_id = outbound.trip_number

        steps = [
            {
                "id": "audit_compliance",
                "kind": "tool",
                "tool": "roadstar.audit_compliance",
                "inputs": {
                    "driver_id": str(match_result.assigned_driver_id),
                    "hos_passed": bool(match_result.hos_audit_passed),
                    "weight_passed": bool(match_result.weight_audit_passed),
                },
            },
            {
                "id": "reserve_fleet",
                "kind": "tool",
                "tool": "roadstar.reserve_fleet",
                "inputs": {
                    "truck_id": actual_truck_id,
                    "driver_id": str(match_result.assigned_driver_id),
                    "order_bill": outbound.bill_number,
                    "start_time": t_start.isoformat(),
                    "end_time": t_end.isoformat(),
                    "trip_id": primary_trip_id,
                },
                "depends_on": ["audit_compliance"],
            },
            {
                "id": "dispatch_driver",
                "kind": "tool",
                "tool": "roadstar.dispatch_carrier",
                "inputs": {
                    "driver_id": str(match_result.assigned_driver_id),
                    "driver_name": str(match_result.driver_name),
                    "trips": [outbound.trip_number] + ([ret.trip_number] if ret else [])
                },
                "depends_on": ["reserve_fleet"],
            }
        ]

        plan = {
            "schema_version": "pdx_execution_plan_v1",
            "request_id": run_id,
            "producer": {"type": "roadstar.dispatcher_engine", "name": "PDX Autonomous Dispatch"},
            "intent": {
                "artifact_type": "dispatch_package",
                "summary": f"City dispatch and deadhead reduction for Driver {match_result.driver_name}",
            },
            "steps": steps,
        }

        validate_execution_plan(plan)
        plan_digest = canonical_digest(plan)

        cp = create_checkpoint(
            plan=plan,
            run_id=run_id,
            subject_digest=plan_digest,
            completed_step_ids=[],
            pending_step_ids=[s["id"] for s in steps],
            evidence_digests={"plan": plan_digest},
            checkpoint_id=f"cp-{uuid.uuid4().hex[:8]}",
        )
        approval_req = create_approval_request(
            cp,
            summary=f"Dispatcher Review Required: {outbound.origin_city} -> {outbound.dest_city}",
        )

        with self._lock:
            self.active_plans[run_id] = {
                "run_id": run_id,
                "status": "awaiting_approval",
                "plan": plan,
                "digest": plan_digest,
                "checkpoint": cp,
                "approval_request": approval_req,
                "match_result": match_result,
                "truck_id": actual_truck_id,
                "trip_id": primary_trip_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "approved_at": None,
                "receipt": None,
                "manifest": None,
            }

        return self.active_plans[run_id]

    def _verify_durable_engine_run(self, run_output_dir, plan, expected_plan_digest):
        """Loose files cannot establish an Engine execution's provenance."""
        return False, None, None, (
            "REQ-PDX-ENGINE-005: pdx-artifact-engine==0.3.0a5 has no authenticated "
            "completed-run recovery API; loose-file recovery requires reconciliation"
        )

    @staticmethod
    def _persist_state(item, state_file):
        data = {k: v for k, v in item.items() if k != "match_result"}
        temporary = state_file.with_name(f".run_state_{uuid.uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, state_file)

    def approve_and_execute_plan(
        self, run_id: str, approver_email: str = "dispatcher@roadstar.ca",
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute a new plan through the public Engine. Never recover loose files.

        Unknown outcomes retain resource reservations until reconciliation.
        A repeated request must not dispatch again, even after process death.
        """
        if Path(run_id).name != run_id or run_id in (".", ".."):
            raise ValueError("Invalid run identifier")
        run_dir = self.storage_dir / run_id
        if output_dir is not None and Path(output_dir).resolve() != run_dir.resolve():
            raise ValueError("Dispatch output_dir must equal the canonical run directory")
        run_dir.mkdir(parents=True, exist_ok=True)
        state_file = run_dir / "run_state.json"
        with ExecutionLock(run_dir / ".execution.lock", run_id):
            with self._lock:
                item = self.active_plans.get(run_id)
            existing = [p for p in run_dir.iterdir() if p.name != ".execution.lock"]
            if existing:
                # Do not load plans, decisions or success claims from untrusted files.
                item = item or {"run_id": run_id}
                item["status"] = "awaiting_reconciliation"
                item["error"] = self._verify_durable_engine_run(run_dir, None, None)[3]
                self.active_plans[run_id] = item
                self._persist_state(item, run_dir / "reconciliation.json")
                raise RuntimeError(item["error"])
            if item is None:
                raise KeyError(f"Run {run_id} not found")
            if item.get("status") != "awaiting_approval":
                raise RuntimeError(f"Run {run_id} cannot execute from {item.get('status')}")
            plan, cp, req = item["plan"], item["checkpoint"], item["approval_request"]
            validate_execution_plan(plan)
            if canonical_digest(plan) != item["digest"] or cp["plan_digest"] != item["digest"]:
                raise ValueError("Dispatch plan changed after approval request creation")
            now = datetime.now(timezone.utc)
            decision = {
                "idempotency_key": f"decision-{run_id}",
                "checkpoint_id": cp["checkpoint_id"],
                "approval_request_id": req["approval_request_id"],
                "subject_digest": cp["subject_digest"],
                "plan_digest": cp["plan_digest"],
                "evidence_digests": dict(cp["evidence_digests"]),
                "decision": "approved",
            }
            # Public approval validation must succeed BEFORE any executor side effect.
            ledger_entry = self.ledger.record(cp, req, decision)
            item.update(status="executing", approved_at=now.isoformat(), ledger_entry=ledger_entry)
            # Durable attempt marker precedes Engine entry. Crash => blocked, never replay.
            self._persist_state(item, state_file)
            try:
                result = self.runtime.execute_plan(plan, run_dir)
                manifest = result.get("run_manifest", {})
                status = manifest.get("status")
                item["manifest"] = manifest
                if status != "completed":
                    item["status"] = "awaiting_review" if status == "completed_with_review" else "awaiting_reconciliation"
                    raise RuntimeError(f"ArtifactRuntime execution returned {status}; reconciliation/review required; errors: {manifest.get('errors')}")
                item["receipt"] = {
                    "schema_version": "pdx_step_receipt_v1", "step_id": "dispatcher_approval",
                    "run_id": run_id, "status": "approved", "approver": approver_email,
                    "timestamp": now.isoformat(), "plan_digest": item["digest"],
                    "ledger_entry": ledger_entry,
                }
                item.update(status="completed", output_dir=str(run_dir))
                self._persist_state(item, state_file)
                return dict(item)
            except Exception as exc:
                # A carrier may have received dispatch before the runtime/write failed.
                # Releasing its order here could cause a second physical shipment.
                if item.get("status") != "awaiting_review":
                    item["status"] = "awaiting_reconciliation"
                item["error"] = str(exc)
                self._persist_state(item, state_file)
                raise

    def approve_plan(self, run_id: str, approver_email: str = "dispatcher@roadstar.ca") -> Dict[str, Any]:
        """Backwards-compatible wrapper that executes the plan."""
        return self.approve_and_execute_plan(run_id, approver_email=approver_email)
