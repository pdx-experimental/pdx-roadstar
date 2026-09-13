import os
import sys
from datetime import datetime, timedelta
import pytest

sys.path.insert(0, r"d:\ProDocuX\prodocux-labs\incubator\pdx-roadstar\packages")

from roadstar_domain.models import OrderModel, BackhaulMatchResult, DetentionRecord
from roadstar_adapter_pdx.dispatch_workflow import DispatchWorkflowEngine
from roadstar_adapter_prodocux.detention_dossier import DetentionDossierBuilder


def test_pdx_execution_plan_creation_and_approval():
    outbound = OrderModel(
        bill_number="BOL-4091",
        trip_number="TRIP-6221",
        customer_name="Mondelez Canada",
        origin_city="MILTON",
        origin_prov="ON",
        origin_pc="L9T 5B4",
        dest_city="LONDON",
        dest_prov="ON",
        dest_pc="N6A 4G5",
        distance_miles=118.0,
        weight_lbs=34000.0,
        rate_cad=1200.0
    )
    return_order = OrderModel(
        bill_number="BOL-4092",
        trip_number="TRIP-6222",
        customer_name="Labatt London",
        origin_city="LONDON",
        origin_prov="ON",
        origin_pc="N6A 4M8",
        dest_city="KITCHENER",
        dest_prov="ON",
        dest_pc="N2C 1L7",
        distance_miles=65.0,
        weight_lbs=41000.0,
        rate_cad=850.0
    )
    match_result = BackhaulMatchResult(
        outbound_order=outbound,
        return_order=return_order,
        deadhead_reduction_pct=85.0,
        empty_miles_saved=100.0,
        total_revenue_cad=2050.0,
        hos_audit_passed=True,
        weight_audit_passed=True,
        assigned_driver_id=42,
        driver_name="Dave",
        notes=["Test dispatch plan"]
    )

    engine = DispatchWorkflowEngine()
    plan_entry = engine.create_dispatch_plan(match_result)
    run_id = plan_entry["run_id"]

    assert plan_entry["status"] == "awaiting_approval"
    assert plan_entry["plan"]["schema_version"] == "pdx_execution_plan_v1"
    assert len(plan_entry["plan"]["steps"]) == 3

    # Now approve and execute through ArtifactRuntime
    approved = engine.approve_plan(run_id, approver_email="chief_dispatcher@roadstar.ca")
    assert approved["status"] == "completed"
    assert approved["manifest"]["status"] == "completed"
    assert approved["receipt"]["schema_version"] == "pdx_step_receipt_v1"
    assert approved["receipt"]["status"] == "approved"
    assert approved["receipt"]["approver"] == "chief_dispatcher@roadstar.ca"


def test_prodocux_detention_dossier_pdf_generation(tmp_path):
    arrival = datetime.now() - timedelta(hours=3.5)
    departure = datetime.now()
    record = DetentionRecord(
        record_id="DET-TEST-001",
        trip_number="TRIP-622819",
        bill_number="BOL-412300",
        driver_id=13,
        driver_name="Driver13",
        facility_id="GEO-MISSISSAUGA",
        facility_name="Mississauga Logistics Dock 4",
        geofence_arrival_time=arrival,
        geofence_departure_time=departure,
        free_time_hours=2.0,
        total_wait_hours=3.5,
        billable_hours=1.5,
        hourly_rate_cad=95.0,
        total_detention_fee_cad=142.50,
        status="WAITING"
    )

    out_dir = str(tmp_path)
    pdf_path = DetentionDossierBuilder.generate_dossier_pdf(record, out_dir)
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000
    assert record.dossier_sha256 is not None
    assert len(record.dossier_sha256) == 64  # valid SHA-256 string
