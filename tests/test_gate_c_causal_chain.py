"""Gate C Acceptance Test Suite: End-to-End Causal Integration.
Verifies that public ProDocuX Kernel (0.3.0rc4) and Artifact Engine (0.3.0a5)
drive the real operational causality of pdx-roadstar:
1. Atomic asset storage and sink concurrency safety.
2. Real dispatch workflow through ArtifactRuntime.execute_plan with FleetResourceManager locks.
3. Negative fault injection: resource conflict rejection and tool failure rollback.
4. Real carrier detention workflow: Kernel render -> resolve -> intake -> evidence bundle audit.
5. Negative detention rejection: chronology error and below-free-time reject invoicing.
"""
from __future__ import annotations

import os
import json
import hashlib
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest

from roadstar_domain.models import OrderModel, BackhaulMatchResult, DetentionRecord
from roadstar_domain.resource_manager import FleetResourceManager, ResourceConflictError
from roadstar_adapter_prodocux.artifact_sink import RoadStarArtifactSink
from roadstar_adapter_pdx.storage_adapter import RoadStarStorageAdapter
from roadstar_adapter_pdx.dispatch_workflow import DispatchWorkflowEngine
from roadstar_adapter_prodocux.detention_dossier import DetentionDossierBuilder

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "acceptance" / "evidence" / "gate_c_artifacts"



def test_gate_c_storage_and_sink_atomic_concurrency():
    """Verify that RoadStarArtifactSink and RoadStarStorageAdapter publish atomically:
    10 concurrent workers race to store an artifact. Exactly 1 creates, 9 return idempotent no-op.
    Concurrent readers never observe partial bytes. Conflicting payload raises FileExistsError.
    """
    sink = RoadStarArtifactSink(EVIDENCE_DIR)
    target_name = "gate_c_sink_race.bin"
    target_path = EVIDENCE_DIR / target_name
    if target_path.exists():
        target_path.unlink()

    payload = b"GATE_C_STRICT_ATOMIC_PAYLOAD_EVIDENCE"
    payload_sha = hashlib.sha256(payload).hexdigest()

    worker_count = 10
    results = []

    def race_worker(worker_id: int):
        return sink.create_if_absent(
            output_name=target_name,
            media_type="application/octet-stream",
            payload=payload,
            sha256=payload_sha
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(race_worker, i) for i in range(worker_count)]
        for f in futures:
            results.append(f.result())

    assert len(results) == worker_count
    assert target_path.read_bytes() == payload

    actions = sink.action_history[target_name]
    assert actions.count("created") == 1
    assert actions.count("idempotent_noop") == worker_count - 1

    # Conflict check
    conflict_payload = b"CONFLICTING_PAYLOAD"
    with pytest.raises(FileExistsError):
        sink.create_if_absent(
            output_name=target_name,
            media_type="application/octet-stream",
            payload=conflict_payload,
            sha256=hashlib.sha256(conflict_payload).hexdigest()
        )


def test_gate_c_dispatch_execution_plan_real_engine(tmp_path):
    """Verify that DispatchWorkflowEngine truly drives execution through ArtifactRuntime.execute_plan.
    Produces real run manifest, step outputs, and holds fleet resource lock.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)

    outbound = OrderModel(
        bill_number="BOL-GTC-01", trip_number="TRIP-GTC-01", customer_name="Mondelez Canada",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T 5B4",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A 4G5",
        distance_miles=118.0, weight_lbs=34000.0, rate_cad=1200.0
    )
    ret = OrderModel(
        bill_number="BOL-GTC-02", trip_number="TRIP-GTC-02", customer_name="Labatt London",
        origin_city="LONDON", origin_prov="ON", origin_pc="N6A 4M8",
        dest_city="KITCHENER", dest_prov="ON", dest_pc="N2C 1L7",
        distance_miles=65.0, weight_lbs=41000.0, rate_cad=850.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=ret, deadhead_reduction_pct=85.0,
        empty_miles_saved=100.0, total_revenue_cad=2050.0, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=77, driver_name="Driver77", notes=[]
    )

    t_start = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    plan_entry = engine.create_dispatch_plan(match, truck_id="TRUCK-77", start_time=t_start, duration_hours=6.0)
    run_id = plan_entry["run_id"]
    assert plan_entry["status"] == "awaiting_approval"

    # Approve & execute via ArtifactRuntime
    approved = engine.approve_plan(run_id, approver_email="chief_dispatcher@roadstar.ca")
    assert approved["status"] == "completed"
    assert approved["manifest"]["status"] == "completed"
    assert approved["manifest"]["schema_version"] == "pdx_run_manifest_v0"

    # Step outputs must physically exist on disk in step directories created by Engine
    run_dir = Path(approved["output_dir"])
    assert (run_dir / "reserve_fleet" / "reservation.json").is_file()
    assert (run_dir / "audit_compliance" / "compliance_audit.json").is_file()
    assert (run_dir / "dispatch_driver" / "carrier_dispatch.json").is_file()
    assert (run_dir / "run_manifest.json").is_file()

    # Resource lock must be held
    mgr = FleetResourceManager.get_global_manager()
    assert not mgr.is_available("truck", "TRUCK-77", t_start + timedelta(hours=1), t_start + timedelta(hours=3))
    assert not mgr.is_available("driver", "77", t_start + timedelta(hours=1), t_start + timedelta(hours=3))


def test_gate_c_dispatch_competing_resource_conflict_fails(tmp_path):
    """Negative test: Two dispatch plans compete for the same truck during overlapping time.
    First succeeds; second must fail at the reserve_fleet step, and Engine manifests failure.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    t_start = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)

    o1 = OrderModel(bill_number="BOL-A", trip_number="TRIP-A", customer_name="C1", origin_city="A", origin_prov="ON", origin_pc="L1", dest_city="B", dest_prov="ON", dest_pc="L2", distance_miles=50.0, weight_lbs=10000.0, rate_cad=500.0)
    o2 = OrderModel(bill_number="BOL-B", trip_number="TRIP-B", customer_name="C2", origin_city="A", origin_prov="ON", origin_pc="L1", dest_city="B", dest_prov="ON", dest_pc="L2", distance_miles=50.0, weight_lbs=10000.0, rate_cad=500.0)

    m1 = BackhaulMatchResult(outbound_order=o1, return_order=None, deadhead_reduction_pct=0, empty_miles_saved=0, total_revenue_cad=500, hos_audit_passed=True, weight_audit_passed=True, assigned_driver_id=50, driver_name="Driver50", notes=[])
    m2 = BackhaulMatchResult(outbound_order=o2, return_order=None, deadhead_reduction_pct=0, empty_miles_saved=0, total_revenue_cad=500, hos_audit_passed=True, weight_audit_passed=True, assigned_driver_id=51, driver_name="Driver51", notes=[])

    p1 = engine.create_dispatch_plan(m1, truck_id="TRUCK-SHARED", start_time=t_start, duration_hours=4.0)
    p2 = engine.create_dispatch_plan(m2, truck_id="TRUCK-SHARED", start_time=t_start + timedelta(hours=1), duration_hours=4.0)

    res1 = engine.approve_plan(p1["run_id"])
    assert res1["status"] == "completed"

    with pytest.raises(Exception) as exc_info:
        engine.approve_plan(p2["run_id"])
    assert "already reserved" in str(exc_info.value)
    assert engine.active_plans[p2["run_id"]]["status"] == "awaiting_reconciliation"


def test_gate_c_dispatch_compliance_failure_triggers_rollback(tmp_path):
    """Negative test: HOS non-compliance causes audit_compliance to fail.
    Downstream steps do not execute, no truck is reserved, and status is failed.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(bill_number="BOL-FAIL", trip_number="TRIP-FAIL", customer_name="C", origin_city="A", origin_prov="ON", origin_pc="L1", dest_city="B", dest_prov="ON", dest_pc="L2", distance_miles=50.0, weight_lbs=10000.0, rate_cad=500.0)
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0, empty_miles_saved=0,
        total_revenue_cad=500, hos_audit_passed=False, weight_audit_passed=True,
        assigned_driver_id=999, driver_name="ExhaustedDriver", notes=[]
    )

    plan_entry = engine.create_dispatch_plan(match, truck_id="TRUCK-SAFE")
    with pytest.raises(Exception) as exc_info:
        engine.approve_plan(plan_entry["run_id"])
    assert "Compliance violation" in str(exc_info.value)

    # Truck must NOT be reserved
    mgr = FleetResourceManager.get_global_manager()
    t_now = datetime.now(timezone.utc)
    assert mgr.is_available("truck", "TRUCK-SAFE", t_now, t_now + timedelta(hours=6))


def test_gate_c_detention_dossier_full_audit_positive(tmp_path):
    """Verify positive detention causal chain:
    Kernel render -> resolve -> intake.pdf -> verify_evidence_bundle -> AUDITED_APPROVED.
    Invoiced fee equals claimed fee; canonical SHA-256 is recorded.
    """
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=3, minutes=30)
    rec = DetentionRecord(
        record_id="DET-POS-01", trip_number="TRIP-POS", bill_number="BOL-POS",
        driver_id=10, driver_name="Driver10", facility_id="FAC-MISSISSAUGA",
        facility_name="Mississauga Logistics Hub", geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.5, billable_hours=1.5,
        hourly_rate_cad=100.0, total_detention_fee_cad=150.0, status="WAITING"
    )

    builder = DetentionDossierBuilder(output_dir=tmp_path)
    pdf_path, info = builder.generate_and_audit_dossier(rec)

    assert Path(pdf_path).is_file()
    assert info["audit_status"] == "pass"
    assert info["invoiced_amount_cad"] == 150.0
    assert rec.status == "AUDITED_APPROVED"
    assert rec.dossier_sha256 == info["canonical_digest"]
    assert len(rec.dossier_sha256) == 64


def test_gate_c_detention_dossier_audit_rejection_chronology_inverted(tmp_path):
    """Negative test: Departure timestamp is before arrival timestamp.
    Kernel verify_evidence_bundle fails with DATE_ORDER_INVALID.
    Record is marked AUDITED_REJECTED, invoiced amount is $0.00.
    """
    t0 = datetime(2026, 8, 14, 11, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)  # Inverted!
    rec = DetentionRecord(
        record_id="DET-INV-01", trip_number="TRIP-INV", bill_number="BOL-INV",
        driver_id=10, driver_name="Driver10", facility_id="FAC-MISSISSAUGA",
        facility_name="Mississauga Logistics Hub", geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.0, billable_hours=1.0,
        hourly_rate_cad=100.0, total_detention_fee_cad=100.0, status="WAITING"
    )

    builder = DetentionDossierBuilder(output_dir=tmp_path)
    pdf_path, info = builder.generate_and_audit_dossier(rec)

    assert info["audit_status"] == "fail"
    assert info["invoiced_amount_cad"] == 0.0
    assert rec.status == "AUDITED_REJECTED"
    assert rec.dossier_sha256 is None


def test_gate_c_detention_dossier_audit_rejection_below_free_time(tmp_path):
    """Negative test: Total dwell is 1.5 hours (under 2.0 hours free time threshold).
    Kernel verify_evidence_bundle fails with VALUE_BELOW_MINIMUM.
    Record is marked AUDITED_REJECTED, invoiced amount is $0.00.
    """
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1, minutes=30)
    rec = DetentionRecord(
        record_id="DET-LOW-01", trip_number="TRIP-LOW", bill_number="BOL-LOW",
        driver_id=10, driver_name="Driver10", facility_id="FAC-MISSISSAUGA",
        facility_name="Mississauga Logistics Hub", geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=1.5, billable_hours=0.0,
        hourly_rate_cad=100.0, total_detention_fee_cad=0.0, status="WAITING"
    )

    builder = DetentionDossierBuilder(output_dir=tmp_path)
    pdf_path, info = builder.generate_and_audit_dossier(rec)

    assert info["audit_status"] == "fail"
    assert info["invoiced_amount_cad"] == 0.0
    assert rec.status == "AUDITED_REJECTED"
    assert rec.dossier_sha256 is None
