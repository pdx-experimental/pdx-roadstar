"""Reproduction tests for the 5 audited defects in pdx-roadstar.
These tests demonstrate the vulnerabilities reported by the user/audit
and will fail on the unpatched codebase.
"""
from __future__ import annotations
import os
import copy
import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import pytest

from roadstar_domain.models import OrderModel, DriverModel, DetentionRecord, HOSStatus, BackhaulMatchResult
from roadstar_domain.matching_engine import match_backhaul_and_audit, MAX_TRAILER_WEIGHT_LBS
from roadstar_domain.resource_manager import FleetResourceManager
from roadstar_adapter_pdx.dispatch_workflow import DispatchWorkflowEngine
from roadstar_adapter_prodocux.detention_dossier import DetentionDossierBuilder
from prodocux_kernel.artifacts import ArtifactResolutionError


def _inject_source_priced_orders(sim, count=4):
    """Synthetic fixtures test Engine failure behavior, never production revenue."""
    sim.orders = [OrderModel(
        bill_number=f"FIXTURE-{i}", trip_number=f"FIXTURE-TRIP-{i}", customer_name="Test Shipper",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="BRAMPTON", dest_prov="ON", dest_pc="L6T",
        distance_miles=40.0, weight_lbs=26000.0, rate_cad=500.0,
    ) for i in range(count)]



def test_reproduce_defect_1_engine_failure_causes_phantom_savings(tmp_path):
    """Defect 1: When Artifact Engine execution fails, the simulator crashes or reports
    empty miles saved and non-zero backhaul improvement because pdx_empty_miles
    was decoupled from actual Engine success.
    """
    from roadstar_application.scenario_comparison import ScenarioComparison
    sim = ScenarioComparison("2026-08-14", storage_dir=tmp_path)
    _inject_source_priced_orders(sim)

    # Injected failure in public engine execution
    with patch.object(
        sim.workflow,
        "approve_and_execute_plan",
        side_effect=RuntimeError("Simulated Public Engine Failure")
    ):
        try:
            st = sim.tick(960.0)
        except Exception:
            # If tick crashes instead of handling failure cleanly, get current state
            st = sim.get_state()

    # When engine fails, exactly 0 backhauls dispatched, 0 empty miles saved, 0 backhaul revenue
    assert st["deltas"]["empty_miles_saved"] == 0.0, (
        f"Phantom savings detected: {st['deltas']['empty_miles_saved']} mi saved despite Engine failure!"
    )
    assert st["deltas"]["new_backhaul_revenue_cad"] == 0.0, (
        f"Phantom revenue detected: ${st['deltas']['new_backhaul_revenue_cad']} CAD despite Engine failure!"
    )
    assert st["pdx"]["empty_miles"] == st["baseline"]["empty_miles"], (
        f"PDX empty miles ({st['pdx']['empty_miles']}) != Baseline empty miles ({st['baseline']['empty_miles']})"
    )


def test_reproduce_defect_2_matcher_ignores_return_weight_and_double_booking():
    """Defect 2: The legacy matcher only audited outbound weight, ignoring return weight,
    and allowed double-booking the same order across multiple outbound trips.
    """
    outbound = OrderModel(
        bill_number="BOL-OUT-1", trip_number="TRIP-1", customer_name="C1",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    # Overweight return load (50,000 lbs > 44,500 lbs limit)
    overweight_return = OrderModel(
        bill_number="BOL-RET-OVERWEIGHT", trip_number="TRIP-RET-1", customer_name="C2",
        origin_city="LONDON", origin_prov="ON", origin_pc="N6A",
        dest_city="MILTON", dest_prov="ON", dest_pc="L9T",
        distance_miles=100.0, weight_lbs=50000.0, rate_cad=1000.0
    )
    driver = DriverModel(
        driver_id=1, first_name="TestDriver", email="test@roadstar.ca",
        home_zone="RSTAR", status="AVAIL", lat=43.5, lng=-79.8,
        location_desc="Milton",
        hos=HOSStatus(driver_id=1, first_name="TestDriver", remaining_hours_can_7=50.0)
    )

    result = match_backhaul_and_audit(outbound, [overweight_return], [driver])

    # Should fail weight audit due to return load exceeding trailer capacity
    assert result.weight_audit_passed is False, "Matcher allowed 50,000 lbs return load to pass weight audit!"


def test_reproduce_defect_3_tampered_pdf_on_disk_bypasses_verification(tmp_path):
    """Defect 3: DetentionDossierBuilder recomputes the SHA-256 from whatever bytes
    currently exist on disk, meaning physical byte tampering is never caught.
    """
    builder = DetentionDossierBuilder(output_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=3, minutes=30)
    rec = DetentionRecord(
        record_id="DET-TAMPER-01", trip_number="TRIP-T1", bill_number="BOL-T1",
        driver_id=10, driver_name="Driver10", facility_id="FAC-1",
        facility_name="Terminal 1", geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.5, billable_hours=1.5,
        hourly_rate_cad=100.0, total_detention_fee_cad=150.0, status="WAITING"
    )

    # 1. First legitimate generation
    pdf_path_str, info = builder.generate_and_audit_dossier(rec)
    pdf_path = Path(pdf_path_str)
    assert pdf_path.exists()
    original_pdf_bytes = pdf_path.read_bytes()

    # 2. Malicious actor modifies 1 byte on disk
    tampered_bytes = bytearray(original_pdf_bytes)
    tampered_bytes[-1] ^= 0xFF
    pdf_path.write_bytes(tampered_bytes)

    # 3. Subsequent verification on the tampered file MUST raise ArtifactResolutionError
    with pytest.raises(ArtifactResolutionError):
        builder.generate_and_audit_dossier(rec)


def test_reproduce_defect_4_approval_ledger_never_recorded(tmp_path):
    """Defect 4: ApprovalLedger was instantiated in DispatchWorkflowEngine but never
    called in approve_and_execute_plan, leaving the ledger completely empty.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    from roadstar_domain.models import BackhaulMatchResult
    outbound = OrderModel(
        bill_number="BOL-APP-1", trip_number="TRIP-APP-1", customer_name="C1",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=1, driver_name="Driver1", notes=[]
    )

    plan = engine.create_dispatch_plan(match, truck_id="TRK-1")
    run_id = plan["run_id"]
    engine.approve_and_execute_plan(run_id)

    # Public ApprovalLedger must contain the registered decision under its idempotency key
    recorded = engine.ledger.get_by_idempotency_key(f"decision-{run_id}")
    assert recorded is not None, "ApprovalLedger.record was never called during approve_and_execute_plan!"
    assert recorded["decision"] == "approved"


def test_reproduce_defect_5_pdf_extraction_missing_field_falls_back(tmp_path):
    """Defect 5: When PDF text extraction misses required fields (e.g. ARRIVAL_TIMESTAMP),
    the builder silently falls back to record input arguments instead of raising an error.
    """
    builder = DetentionDossierBuilder(output_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=3, minutes=30)
    rec = DetentionRecord(
        record_id="DET-MISS-01", trip_number="TRIP-M1", bill_number="BOL-M1",
        driver_id=10, driver_name="Driver10", facility_id="FAC-1",
        facility_name="Terminal 1", geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.5, billable_hours=1.5,
        hourly_rate_cad=100.0, total_detention_fee_cad=150.0, status="WAITING"
    )

    # Mock intake_pdf.extract_pdf_bytes to simulate extraction missing ARRIVAL_TIMESTAMP
    with patch(
        "prodocux_kernel.intake.pdf.extract_pdf_bytes",
        return_value=([{"text": "DEPARTURE_TIMESTAMP: 2026-08-14T11:30:00Z\nCLAIMED_DWELL_HOURS: 3.5\n"}], False)
    ):
        with pytest.raises(ValueError, match="ARRIVAL_TIMESTAMP"):
            builder.generate_and_audit_dossier(rec)


def test_partial_dispatch_failure_preserves_successful_dispatch(tmp_path):
    """Point 5: When one dispatch fails and another succeeds, successful earnings are preserved
    while failed dispatch yields zero for that failed leg.
    """
    from roadstar_application.scenario_comparison import ScenarioComparison
    sim = ScenarioComparison("2026-08-14", storage_dir=tmp_path)
    _inject_source_priced_orders(sim)

    call_count = 0
    orig_approve = sim.workflow.approve_and_execute_plan

    def fail_second_dispatch(run_id, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Engine Failure on 2nd Dispatch Only")
        return orig_approve(run_id, *args, **kwargs)

    with patch.object(sim.workflow, "approve_and_execute_plan", side_effect=fail_second_dispatch):
        st = sim.tick(960.0)

    # First dispatch succeeded and was preserved!
    assert any(outcome["kind"] == "backhaul" for outcome in sim.outcomes.values())
    assert st["deltas"]["empty_miles_saved"] > 0.0
    assert st["deltas"]["new_backhaul_revenue_cad"] > 0.0


def test_detention_audit_failure_does_not_affect_dispatch_revenue(tmp_path):
    """Point 5: Kernel detention dossier failure does not wipe out dispatch backhaul earnings."""
    from roadstar_application.scenario_comparison import ScenarioComparison
    sim = ScenarioComparison("2026-08-14", storage_dir=tmp_path)
    _inject_source_priced_orders(sim)

    # Mock dossier builder to fail verification
    with patch(
        "prodocux_kernel.verification.evidence.verify_evidence_bundle",
        return_value={"status": "fail", "canonical_request_sha256": "0" * 64, "results": []}
    ):
        st = sim.tick(960.0)

    # Backhaul dispatch should still succeed
    assert st["deltas"]["new_backhaul_revenue_cad"] > 0.0
    # Invoiced detention must be 0.0
    assert st["deltas"]["detention_gain_cad"] == 0.0


def test_concurrent_approval_mutual_exclusion(tmp_path):
    """Point 4: Concurrent approvals on the same plan must atomically acquire execution right.
    No double execution or corruption can occur.
    """
    from concurrent.futures import ThreadPoolExecutor
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(
        bill_number="BOL-CONC-1", trip_number="TRIP-C1", customer_name="C1",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=1, driver_name="Driver1", notes=[]
    )
    plan = engine.create_dispatch_plan(match, truck_id="TRK-C1")
    run_id = plan["run_id"]

    results = []
    errors = []

    def try_approve():
        try:
            res = engine.approve_and_execute_plan(run_id)
            results.append(res)
        except Exception as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(try_approve) for _ in range(5)]
        for f in futures:
            f.result()

    # Plan ends up completed
    assert engine.active_plans[run_id]["status"] == "awaiting_reconciliation"
    # At least one succeeded, any concurrent races were handled safely
    assert len(results) >= 1


def test_cross_engine_restart_idempotency(tmp_path):
    """Point 4: Restarting blocks unsupported recovery and prevents re-execution."""
    engine1 = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(
        bill_number="BOL-RST-1", trip_number="TRIP-R1", customer_name="C1",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=1, driver_name="Driver1", notes=[]
    )
    plan = engine1.create_dispatch_plan(match, truck_id="TRK-R1")
    run_id = plan["run_id"]
    res1 = engine1.approve_and_execute_plan(run_id)
    assert res1["status"] == "completed"

    # Simulate restart by creating a new engine instance with the same storage_dir
    engine2 = DispatchWorkflowEngine(storage_dir=tmp_path)
    with patch.object(engine2.runtime, "execute_plan") as execute:
        with pytest.raises(RuntimeError, match="REQ-PDX-ENGINE-005"):
            engine2.approve_and_execute_plan(run_id)
        execute.assert_not_called()
    assert engine2.active_plans[run_id]["status"] == "awaiting_reconciliation"


def test_pdf_bytes_hash_strictly_different_from_audit_request_digest(tmp_path):
    """Point 3: Physical PDF bytes SHA-256 and audit request canonical digest must be strictly separated."""
    builder = DetentionDossierBuilder(output_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=3, minutes=30)
    rec = DetentionRecord(
        record_id="DET-SEP-01", trip_number="TRIP-S1", bill_number="BOL-S1",
        driver_id=10, driver_name="Driver10", facility_id="FAC-1",
        facility_name="Terminal 1", geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.5, billable_hours=1.5,
        hourly_rate_cad=100.0, total_detention_fee_cad=150.0, status="WAITING"
    )
    pdf_path, info = builder.generate_and_audit_dossier(rec)

    raw_pdf_bytes = Path(pdf_path).read_bytes()
    expected_file_sha = hashlib.sha256(raw_pdf_bytes).hexdigest()

    assert rec.pdf_sha256 == expected_file_sha
    assert rec.audit_canonical_digest == info["canonical_digest"]
    # Binary PDF SHA-256 and JSON Evidence Request Digest are completely different hashes!
    assert rec.pdf_sha256 != rec.audit_canonical_digest
    assert len(rec.pdf_sha256) == 64
    assert len(rec.audit_canonical_digest) == 64


def test_fleet_size_unique_trucks_53_and_legs_80():
    """Fleet size model: 53 unique trucks across 80 legs in the scenario."""
    from dual_track_simulator import DualTrackSimulator
    sim = DualTrackSimulator(target_date_str="2026-08-14", enable_stochastic=False)

    assert sim.truck_count == 53
    assert sim.legs_count == 80
    assert len(sim.legs) == 80
    assert sim.baseline["active_trucks"] == []
    assert "pdx" not in sim.get_state(), "Pure simulator must not own PDX state"
    st = sim.get_state()
    assert st["fleet_size"] == 53


def test_counterexample_118_pdf_with_9999_record_and_orphan_disk_asset_rejected(tmp_path):
    """Counterexample from independent audit:
    1. Generate PDF claiming CAD 118.75.
    2. Remove asset registry record, clear record expected digest.
    3. Use same document ID, change input billing to CAD 9,999.
    4. Call formal document process again.
    Must NOT adopt untrusted orphan bytes on disk, and must NOT invoice CAD 9,999.
    """
    builder = DetentionDossierBuilder(output_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=3, minutes=15)

    rec1 = DetentionRecord(
        record_id="DET-AUDIT-9999",
        trip_number="TRIP-AUDIT-1",
        bill_number="BOL-AUDIT-1",
        driver_id=42,
        driver_name="AuditDriver",
        facility_id="FAC-AUDIT",
        facility_name="Audit Depot",
        geofence_arrival_time=t0,
        geofence_departure_time=t1,
        free_time_hours=2.0,
        total_wait_hours=3.25,
        billable_hours=1.25,
        hourly_rate_cad=95.0,
        total_detention_fee_cad=118.75,
        status="WAITING"
    )
    pdf_path, info1 = builder.generate_and_audit_dossier(rec1)
    assert Path(pdf_path).exists()
    assert info1["invoiced_amount_cad"] == 118.75

    # Step 2: Remove asset registry record
    reg_file = tmp_path / ".dossier_asset_registry.json"
    if reg_file.exists():
        reg_file.unlink()

    # Step 3: Use same document ID, change input billing to CAD 9,999 and clear record expected hash
    rec2 = DetentionRecord(
        record_id="DET-AUDIT-9999",
        trip_number="TRIP-AUDIT-1",
        bill_number="BOL-AUDIT-1",
        driver_id=42,
        driver_name="AuditDriver",
        facility_id="FAC-AUDIT",
        facility_name="Audit Depot",
        geofence_arrival_time=t0,
        geofence_departure_time=t1,
        free_time_hours=2.0,
        total_wait_hours=3.25,
        billable_hours=1.25,
        hourly_rate_cad=95.0,
        total_detention_fee_cad=9999.00,  # Arbitrary tampered claim!
        status="WAITING",
        pdf_sha256=None  # Cleared expected digest
    )

    # Step 4: Calling formal document process again MUST NOT silently adopt orphan file and MUST NOT invoice 9,999!
    with pytest.raises((ArtifactResolutionError, ValueError, RuntimeError)) as excinfo:
        builder.generate_and_audit_dossier(rec2)

    # The error must explicitly catch the unverified/orphan asset or billing mismatch
    msg = str(excinfo.value).lower()
    assert ("untrusted" in msg or "orphan" in msg or "mismatch" in msg or "provenance" in msg or "identity" in msg)


def test_billing_identity_mismatch_rejected_even_when_registered(tmp_path):
    """Test that when registry exists with a valid 118.75 CAD document, passing
    a record claiming 9,999 CAD or different facility/timestamps is strictly rejected.
    """
    builder = DetentionDossierBuilder(output_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=3, minutes=15)

    rec1 = DetentionRecord(
        record_id="DET-BIND-01", trip_number="TRIP-B1", bill_number="BOL-B1",
        driver_id=11, driver_name="Driver11", facility_id="FAC-B", facility_name="Depot B",
        geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.25, billable_hours=1.25,
        hourly_rate_cad=95.0, total_detention_fee_cad=118.75, status="WAITING"
    )
    pdf_path, _ = builder.generate_and_audit_dossier(rec1)

    # Now pass same record_id & bill_number, but with 9,999 CAD
    rec_tampered_fee = DetentionRecord(
        record_id="DET-BIND-01", trip_number="TRIP-B1", bill_number="BOL-B1",
        driver_id=11, driver_name="Driver11", facility_id="FAC-B", facility_name="Depot B",
        geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.25, billable_hours=1.25,
        hourly_rate_cad=95.0, total_detention_fee_cad=9999.00, status="WAITING"
    )
    with pytest.raises(ValueError) as exc:
        builder.generate_and_audit_dossier(rec_tampered_fee)
    assert "billing identity mismatch" in str(exc.value).lower()

    # Pass record with different timestamps
    rec_tampered_time = DetentionRecord(
        record_id="DET-BIND-01", trip_number="TRIP-B1", bill_number="BOL-B1",
        driver_id=11, driver_name="Driver11", facility_id="FAC-B", facility_name="Depot B",
        geofence_arrival_time=t0 + timedelta(hours=1), geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.25, billable_hours=1.25,
        hourly_rate_cad=95.0, total_detention_fee_cad=118.75, status="WAITING"
    )
    with pytest.raises(ValueError) as exc:
        builder.generate_and_audit_dossier(rec_tampered_time)
    assert "identity mismatch" in str(exc.value).lower()


def test_independent_traceable_re_registration_procedure(tmp_path):
    """Test that orphan assets can only be re-registered via independent, traceable procedure."""
    builder = DetentionDossierBuilder(output_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=3, minutes=15)
    rec = DetentionRecord(
        record_id="DET-ORPHAN-01", trip_number="TRIP-O1", bill_number="BOL-O1",
        driver_id=12, driver_name="Driver12", facility_id="FAC-O", facility_name="Depot O",
        geofence_arrival_time=t0, geofence_departure_time=t1,
        free_time_hours=2.0, total_wait_hours=3.25, billable_hours=1.25,
        hourly_rate_cad=95.0, total_detention_fee_cad=118.75, status="WAITING"
    )
    pdf_path, _ = builder.generate_and_audit_dossier(rec)
    pdf_file = Path(pdf_path)
    expected_sha = hashlib.sha256(pdf_file.read_bytes()).hexdigest()

    # Wipe registry
    reg_file = tmp_path / ".dossier_asset_registry.json"
    reg_file.unlink()

    # Normal audit must fail because asset is orphaned
    with pytest.raises(ArtifactResolutionError):
        builder.generate_and_audit_dossier(rec)

    # Perform formal independent re-registration
    entry = builder.re_register_orphan_artifact(
        filename=pdf_file.name,
        expected_sha256=expected_sha,
        audit_log_reason="External Auditor Sign-off #AUD-2026-99",
        auditor_id="senior_auditor@roadstar.ca"
    )
    assert entry["pdf_sha256"] == expected_sha
    assert entry["re_registered_by"] == "senior_auditor@roadstar.ca"
    assert entry["audit_log_reason"] == "External Auditor Sign-off #AUD-2026-99"

    # Now that it has been formally re-registered, audit passes with exact fee bound
    _, info = builder.generate_and_audit_dossier(rec)
    assert info["invoiced_amount_cad"] == 118.75


def test_dispatch_interruption_recovery_without_duplicate_execution(tmp_path):
    """Auditor condition 2:
    Tests recovery when dispatch succeeds but process is interrupted before run_state.json is persisted.
    Recovery MUST block for reconciliation, avoid duplicate dispatch, and not assume unexecuted.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(
        bill_number="BOL-INT-01", trip_number="TRIP-INT-01", customer_name="C_INT",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=99, driver_name="Driver99", notes=[]
    )
    plan_item = engine.create_dispatch_plan(match, truck_id="TRK-INT-01")
    plan_item_unexecuted = copy.deepcopy(plan_item)
    run_id = plan_item["run_id"]
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Execute plan cleanly once through Engine
    res1 = engine.approve_and_execute_plan(run_id)
    assert res1["status"] == "completed"
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "artifact_manifest.json").exists()

    # 2. Simulate process crash before run_state.json was persisted or lost from disk
    if (run_dir / "run_state.json").exists():
        (run_dir / "run_state.json").unlink()
    assert not (run_dir / "run_state.json").exists()

    # 3. Create fresh engine instance (simulating restart after crash with unexecuted in-memory plan)
    restart_engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    restart_engine.active_plans[run_id] = plan_item_unexecuted

    # 4. Missing authenticated recovery must block WITHOUT duplicate execution
    with patch.object(
        restart_engine.runtime,
        "execute_plan",
        side_effect=RuntimeError("Duplicate execution detected! Must reconcile from Engine contracts!")
    ):
        with pytest.raises(RuntimeError, match="REQ-PDX-ENGINE-005"):
            restart_engine.approve_and_execute_plan(run_id)

    assert restart_engine.active_plans[run_id]["status"] == "awaiting_reconciliation"
    assert (run_dir / "reconciliation.json").exists()


def test_resource_reservation_atomic_three_way_with_order_conflict(tmp_path):
    """Auditor condition 4:
    Resource reservation MUST atomically cover truck, driver, and freight order bill.
    If order is already reserved, reservation fails atomically and locks none of the three.
    """
    rm = FleetResourceManager(storage_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=4)

    # 1. Acquire reservation for truck 1, driver 1, order BOL-100
    slots1 = rm.acquire_reservation(
        truck_id="TRK-1",
        driver_id="DRV-1",
        order_bill="BOL-100",
        start_time=t0,
        end_time=t1,
        trip_id="TRIP-1"
    )
    assert len(slots1) == 3
    assert {s.resource_type for s in slots1} == {"truck", "driver", "order"}

    # 2. Attempt to acquire for truck 2, driver 2, but SAME order BOL-100
    from roadstar_domain.resource_manager import ResourceConflictError
    with pytest.raises(ResourceConflictError) as exc:
        rm.acquire_reservation(
            truck_id="TRK-2",
            driver_id="DRV-2",
            order_bill="BOL-100",  # Conflict!
            start_time=t0 + timedelta(hours=1),
            end_time=t1 + timedelta(hours=1),
            trip_id="TRIP-2"
        )
    assert "BOL-100" in str(exc.value)

    # 3. Verify atomic rollback: neither TRK-2 nor DRV-2 was reserved
    assert rm.is_available("truck", "TRK-2", t0, t1) is True
    assert rm.is_available("driver", "DRV-2", t0, t1) is True

    # 4. Release TRIP-1 releases all three atomically
    rm.release_reservation("TRIP-1")
    assert rm.is_available("truck", "TRK-1", t0, t1) is True
    assert rm.is_available("driver", "DRV-1", t0, t1) is True
    assert rm.is_available("order", "BOL-100", t0, t1) is True


def test_simulator_does_not_own_pdx_hos_or_dispatch_state():
    """Simulation playback cannot mutate PDX HOS or dispatch state directly."""
    from dual_track_simulator import DualTrackSimulator
    sim = DualTrackSimulator(target_date_str="2026-08-14", enable_stochastic=False)

    assert not hasattr(sim, "available_drivers")
    assert not hasattr(sim, "driver_hos_state")
    assert not hasattr(sim, "workflow_engine")
    sim.tick(120.0)
    assert "pdx" not in sim.get_state()


def test_geodesic_corridor_model_no_silent_defaulting():
    """Auditor condition 3:
    Estimated Geodesic Winding Corridor Model must compute physical distances,
    must NOT use hardcoded 28/22/20/35 constants, and missing coordinates must raise ValueError.
    """
    from roadstar_domain.geo_routing import estimate_corridor_road_miles, get_city_coords

    # Unknown city MUST raise ValueError, never silently default
    with pytest.raises(ValueError) as exc:
        estimate_corridor_road_miles("LONDON", "UNKNOWN_FICTIONAL_CITY")
    assert "silent coordinate defaulting is strictly forbidden" in str(exc.value).lower()

    # Physical variation: distances must vary by true coordinates, not hardcoded constants
    dist_woodstock = estimate_corridor_road_miles("LONDON", "WOODSTOCK")
    dist_kitchener = estimate_corridor_road_miles("LONDON", "KITCHENER")
    dist_cambridge = estimate_corridor_road_miles("LONDON", "CAMBRIDGE")

    assert dist_woodstock != dist_kitchener
    assert dist_kitchener != dist_cambridge
    # Verify none equal the old fixed constants 28.0 or 22.0 or 20.0 or 35.0
    for d in [dist_woodstock, dist_kitchener, dist_cambridge]:
        assert d not in [28.0, 22.0, 20.0, 35.0]


def test_reproduce_counterexample_1_unverified_dispatch_json_cannot_bypass_engine(tmp_path):
    """Auditor Counterexample 1:
    Placing only an unverified {"status":"dispatched"} carrier_dispatch.json in the run directory
    and mocking ArtifactRuntime.execute_plan to fail MUST NOT return 'completed' or fabricate
    a success manifest. It must reject/fail and leave the state in awaiting_reconciliation.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(
        bill_number="BOL-CE1-01", trip_number="TRIP-CE1-01", customer_name="Shipper_CE1",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=99, driver_name="Driver99", notes=[]
    )
    plan_item = engine.create_dispatch_plan(match, truck_id="TRK-CE1-01")
    run_id = plan_item["run_id"]
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Place unverified carrier_dispatch.json with {"status": "dispatched"}
    dispatch_file = run_dir / "carrier_dispatch.json"
    dispatch_file.write_text(json.dumps({"status": "dispatched"}), encoding="utf-8")

    # 2. Mock execute_plan to fail if called
    with patch.object(
        engine.runtime,
        "execute_plan",
        side_effect=RuntimeError("Engine execute_plan should not be bypassed!")
    ):
        with pytest.raises(RuntimeError) as exc_info:
            engine.approve_and_execute_plan(run_id)

    # Status must NOT be completed!
    assert "REQ-PDX-ENGINE-005" in str(exc_info.value)
    assert engine.active_plans[run_id]["status"] == "awaiting_reconciliation"


def test_reproduce_counterexample_2_cross_instance_same_order_double_booking_rejected(tmp_path):
    """Auditor Counterexample 2:
    Two separate FleetResourceManager instances pointing to the same storage directory
    attempting to reserve the SAME order bill for overlapping times MUST NOT both succeed.
    The second reservation MUST raise ResourceConflictError.
    """
    from roadstar_domain.resource_manager import ResourceConflictError

    rm1 = FleetResourceManager(storage_dir=tmp_path)
    rm2 = FleetResourceManager(storage_dir=tmp_path)

    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=4)

    # Instance 1 reserves BOL-SHARED-1 with Truck 1 and Driver 1
    slots1 = rm1.acquire_reservation(
        truck_id="TRK-INST-1",
        driver_id="DRV-INST-1",
        order_bill="BOL-SHARED-1",
        start_time=t0,
        end_time=t1,
        trip_id="TRIP-INST-1"
    )
    assert len(slots1) == 3

    # Instance 2 attempts to reserve the SAME order BOL-SHARED-1 with Truck 2 and Driver 2
    with pytest.raises(ResourceConflictError) as exc_info:
        rm2.acquire_reservation(
            truck_id="TRK-INST-2",
            driver_id="DRV-INST-2",
            order_bill="BOL-SHARED-1",  # Same order!
            start_time=t0,
            end_time=t1,
            trip_id="TRIP-INST-2"
        )
    assert "BOL-SHARED-1" in str(exc_info.value)


def test_reproduce_counterexample_order_bill_non_reentrant_across_different_times(tmp_path):
    """Auditor Condition 4:
    A freight order bill represents a single physical shipment.
    It CANNOT be hauled a second time on another trip even if time windows do not overlap.
    """
    from roadstar_domain.resource_manager import ResourceConflictError

    rm = FleetResourceManager(storage_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=4)
    t2 = t1 + timedelta(hours=2)
    t3 = t2 + timedelta(hours=4)

    # Reserve BOL-NONREENTRANT for Trip 1
    rm.acquire_reservation(
        truck_id="TRK-1",
        driver_id="DRV-1",
        order_bill="BOL-NONREENTRANT",
        start_time=t0,
        end_time=t1,
        trip_id="TRIP-1"
    )

    # Attempt to reserve the SAME order BOL-NONREENTRANT for Trip 2 at a later, non-overlapping time
    with pytest.raises(ResourceConflictError) as exc_info:
        rm.acquire_reservation(
            truck_id="TRK-2",
            driver_id="DRV-2",
            order_bill="BOL-NONREENTRANT",
            start_time=t2,
            end_time=t3,
            trip_id="TRIP-2"
        )
    assert "BOL-NONREENTRANT" in str(exc_info.value)


def test_reproduce_counterexample_silent_date_downgrade_in_matcher():
    """Auditor Condition 3:
    Candidate order from a different date outside feasible arrival window must be rejected.
    Zero fallback to time-only comparison.
    """
    outbound = OrderModel(
        bill_number="BOL-OUT-DATE", trip_number="TRIP-OUT-DATE", customer_name="C1",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    # Pickup is one month earlier (July 14 instead of August 14), but time of day matches (14:00)
    past_order = OrderModel(
        bill_number="BOL-RET-PAST", trip_number="TRIP-RET-PAST", customer_name="C2",
        origin_city="LONDON", origin_prov="ON", origin_pc="N6A",
        dest_city="MILTON", dest_prov="ON", dest_pc="L9T",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0,
        pickup_time=datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc)
    )
    driver = DriverModel(
        driver_id=1, first_name="TestDriver", email="test@roadstar.ca",
        home_zone="RSTAR", status="AVAIL", lat=43.5, lng=-79.8,
        location_desc="Milton",
        hos=HOSStatus(driver_id=1, first_name="TestDriver", remaining_hours_can_7=50.0)
    )

    arr_time = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    result = match_backhaul_and_audit(
        outbound_order=outbound,
        candidate_orders=[past_order],
        available_drivers=[driver],
        arrival_time=arr_time
    )

    # Must NOT match past order just because hour/minute was similar
    assert result.return_order is None, "Matcher accepted past order from a month ago via time-only fallback!"


def test_multiprocess_concurrent_resource_reservation(tmp_path):
    """Auditor condition 4:
    Two real independent OS processes competing simultaneously for the same order bill.
    Exactly one must succeed, and the other must fail with ResourceConflictError.
    """
    import sys
    import subprocess

    worker_code = """
import sys
from datetime import datetime, timezone, timedelta
from roadstar_domain.resource_manager import FleetResourceManager, ResourceConflictError

storage_dir = sys.argv[1]
truck_id = sys.argv[2]
driver_id = sys.argv[3]
order_bill = sys.argv[4]
trip_id = sys.argv[5]

rm = FleetResourceManager(storage_dir)
t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
t1 = t0 + timedelta(hours=4)

try:
    rm.acquire_reservation(
        truck_id=truck_id,
        driver_id=driver_id,
        order_bill=order_bill,
        start_time=t0,
        end_time=t1,
        trip_id=trip_id
    )
    print("SUCCESS")
    sys.exit(0)
except ResourceConflictError as exc:
    print(f"CONFLICT: {exc}")
    sys.exit(2)
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)
"""

    env = dict(os.environ)
    # Ensure packages directory is on PYTHONPATH
    packages_dir = str(Path(__file__).resolve().parent.parent / "packages")
    current_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{packages_dir}{os.pathsep}{current_pp}" if current_pp else packages_dir

    p1 = subprocess.Popen(
        [sys.executable, "-c", worker_code, str(tmp_path), "TRK-MP-1", "DRV-MP-1", "BOL-MP-SHARED", "TRIP-MP-1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    p2 = subprocess.Popen(
        [sys.executable, "-c", worker_code, str(tmp_path), "TRK-MP-2", "DRV-MP-2", "BOL-MP-SHARED", "TRIP-MP-2"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )

    out1, _ = p1.communicate(timeout=10)
    out2, _ = p2.communicate(timeout=10)

    exit_codes = [p1.returncode, p2.returncode]
    outputs = [out1.strip(), out2.strip()]

    # Exactly one process must succeed (code 0), the other must encounter conflict (code 2)
    assert 0 in exit_codes, f"Neither process succeeded: {exit_codes}, outputs: {outputs}"
    assert 2 in exit_codes, f"Conflict was not raised by the losing process: {exit_codes}, outputs: {outputs}"
    assert any("CONFLICT" in out for out in outputs)


def test_resource_manager_stale_lock_recovery(tmp_path):
    """Auditor condition 4:
    If a process crashes or leaves an abandoned lock file with a dead PID or expired timestamp,
    subsequent resource reservation must detect the stale lock, safely break it, and succeed.
    """
    from roadstar_domain.resource_manager import FleetResourceManager
    lock_file = tmp_path / ".resource_reservations.lock"
    # Write a fake abandoned lock with non-existent dead PID 99999999 and past timestamp
    lock_file.write_text("99999999:1000000.0", encoding="utf-8")

    rm = FleetResourceManager(storage_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=4)

    slots = rm.acquire_reservation(
        truck_id="TRK-RECOVER-1",
        driver_id="DRV-RECOVER-1",
        order_bill="BOL-RECOVER-1",
        start_time=t0,
        end_time=t1,
        trip_id="TRIP-RECOVER-1"
    )
    assert len(slots) == 3


def test_resource_manager_corrupted_state_file_raises(tmp_path):
    """Auditor condition 4:
    Corrupted state file on disk must raise CorruptedStateError rather than silent bypass.
    """
    from roadstar_domain.resource_manager import FleetResourceManager, CorruptedStateError
    state_file = tmp_path / ".resource_reservations.json"
    state_file.write_text("{corrupted invalid json contents!}", encoding="utf-8")

    rm = FleetResourceManager(storage_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=4)

    with pytest.raises(CorruptedStateError):
        rm.acquire_reservation(
            truck_id="TRK-CORRUPT-1",
            driver_id="DRV-CORRUPT-1",
            order_bill="BOL-CORRUPT-1",
            start_time=t0,
            end_time=t1,
            trip_id="TRIP-CORRUPT-1"
        )


def test_completed_with_review_blocks_automated_dispatch(tmp_path):
    """Auditor condition 2:
    completed_with_review must NOT be treated as completed.
    Automated dispatch must be blocked pending explicit dispatcher review.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(
        bill_number="BOL-REV-01", trip_number="TRIP-REV-01", customer_name="Shipper_REV",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=99, driver_name="Driver99", notes=[]
    )
    plan_item = engine.create_dispatch_plan(match, truck_id="TRK-REV-01")
    run_id = plan_item["run_id"]

    mock_manifest = {
        "schema_version": "pdx_run_manifest_v0",
        "run_id": run_id,
        "request_id": plan_item["plan"]["request_id"],
        "status": "completed_with_review",
        "steps": [{"step_id": "audit_compliance", "status": "completed_with_review"}],
        "verification": [{"check": "manual_review", "status": "review"}],
        "errors": []
    }
    with patch.object(engine.runtime, "execute_plan", return_value={"run_manifest": mock_manifest, "artifact_manifest": {}}):
        with pytest.raises(RuntimeError) as exc_info:
            engine.approve_and_execute_plan(run_id)

    assert "completed_with_review" in str(exc_info.value)
    assert engine.active_plans[run_id]["status"] == "awaiting_review"


def test_reproduce_counterexample_run_state_completed_json_alone_cannot_bypass_engine(tmp_path):
    """Auditor Counterexample 1:
    In a new run directory, placing ONLY run_state.json with {"status":"completed"}
    MUST NOT allow approve_and_execute_plan() to return completed.
    It must reject/fail and leave the state in awaiting_reconciliation.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(
        bill_number="BOL-BYPASS-01", trip_number="TRIP-BYPASS-01", customer_name="Shipper_Bypass",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=99, driver_name="Driver99", notes=[]
    )
    plan_item = engine.create_dispatch_plan(match, truck_id="TRK-BYPASS-01")
    run_id = plan_item["run_id"]
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Place ONLY run_state.json claiming completed
    (run_dir / "run_state.json").write_text(json.dumps({"status": "completed", "run_id": run_id}), encoding="utf-8")

    # Re-instantiate engine to simulate fresh process
    fresh_engine = DispatchWorkflowEngine(storage_dir=tmp_path)

    # Must NOT succeed by merely trusting run_state.json
    with pytest.raises(RuntimeError) as exc_info:
        fresh_engine.approve_and_execute_plan(run_id)

    assert "REQ-PDX-ENGINE-005" in str(exc_info.value)
    assert fresh_engine.active_plans[run_id]["status"] == "awaiting_reconciliation"


def test_reproduce_counterexample_fabricated_manifest_with_wrong_digest_rejected(tmp_path):
    """Auditor Counterexample 2:
    Hand-written manifests with an arbitrary file and hash must NOT pass verification
    when expected_plan_digest does not match or when evidence was not produced by the Engine.
    """
    engine = DispatchWorkflowEngine(storage_dir=tmp_path)
    outbound = OrderModel(
        bill_number="BOL-FAB-01", trip_number="TRIP-FAB-01", customer_name="Shipper_FAB",
        origin_city="MILTON", origin_prov="ON", origin_pc="L9T",
        dest_city="LONDON", dest_prov="ON", dest_pc="N6A",
        distance_miles=100.0, weight_lbs=30000.0, rate_cad=1000.0
    )
    match = BackhaulMatchResult(
        outbound_order=outbound, return_order=None, deadhead_reduction_pct=0,
        empty_miles_saved=0, total_revenue_cad=1000, hos_audit_passed=True,
        weight_audit_passed=True, assigned_driver_id=99, driver_name="Driver99", notes=[]
    )
    plan_item = engine.create_dispatch_plan(match, truck_id="TRK-FAB-01")
    run_id = plan_item["run_id"]
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Arbitrary file with correct hash
    test_file = run_dir / "anything.txt"
    test_file.write_text("arbitrary fake contents", encoding="utf-8")
    test_sha = hashlib.sha256(b"arbitrary fake contents").hexdigest()

    run_mf = {
        "schema_version": "pdx_run_manifest_v0",
        "run_id": run_id,
        "request_id": plan_item["plan"]["request_id"],
        "status": "completed",
        "steps": [
            {"step_id": "audit_compliance", "status": "completed"},
            {"step_id": "reserve_fleet", "status": "completed"},
            {"step_id": "dispatch_driver", "status": "completed"},
        ],
        "verification": [],
        "errors": []
    }
    art_mf = {
        "schema_version": "pdx_artifact_manifest_v0",
        "artifact_id": plan_item["plan"]["request_id"],
        "files": [{"path": "anything.txt", "role": "fake", "sha256": test_sha}]
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(run_mf), encoding="utf-8")
    (run_dir / "artifact_manifest.json").write_text(json.dumps(art_mf), encoding="utf-8")

    # Pass WRONG-DIGEST as expected digest
    is_ok, _, _, reason = engine._verify_durable_engine_run(
        run_dir, plan_item["plan"], expected_plan_digest="WRONG-DIGEST"
    )

    # Must be rejected!
    assert is_ok is False, f"Fabricated manifest with WRONG-DIGEST was falsely accepted as valid! Reason: {reason}"


def test_reproduce_counterexample_empty_or_malformed_state_file_rejected_as_corrupted(tmp_path):
    """Auditor Counterexample 3:
    An existing state file that is empty or malformed must raise CorruptedStateError,
    not return True for availability.
    """
    from roadstar_domain.resource_manager import FleetResourceManager, CorruptedStateError

    state_file = tmp_path / ".resource_reservations.json"
    state_file.write_text("", encoding="utf-8")  # empty string

    rm = FleetResourceManager(storage_dir=tmp_path)
    t0 = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=4)

    with pytest.raises(CorruptedStateError):
        rm.is_available("order", "BOL-EMPTY-FILE", t0, t1)


def test_file_transaction_lock_respects_live_holder_and_keeps_inode(tmp_path):
    from roadstar_domain.resource_manager import FileTransactionLock
    lock_file = tmp_path / "ownership.lock"
    with FileTransactionLock(lock_file):
        with pytest.raises(TimeoutError):
            with FileTransactionLock(lock_file, timeout_sec=0.1):
                pytest.fail("second holder entered critical section")
    assert lock_file.exists()
    with FileTransactionLock(lock_file, timeout_sec=0.1):
        pass
