import pytest
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, r"d:\ProDocuX\prodocux-labs\incubator\pdx-roadstar\packages")

from roadstar_domain.models import HOSStatus, OrderModel, DriverModel
from roadstar_domain.hos_engine import evaluate_hos_compliance, update_hos_tick
from roadstar_domain.geofence_engine import (
    find_containing_geofence,
    calculate_detention_billing,
    SOUTHERN_ONTARIO_GEOFENCES
)
from roadstar_domain.matching_engine import match_backhaul_and_audit


def test_hos_13h_driving_limit():
    hos = HOSStatus(
        driver_id=1,
        first_name="TestDriver",
        current_duty=2,
        duty_status_desc="Driving",
        shift_driving_hours=11.0,
        shift_on_duty_hours=11.0,
        shift_elapsed_hours=12.0,
        remaining_hours_can_7=45.0
    )
    # Adding 3 hours of driving exceeds 13h limit
    comp, viols = evaluate_hos_compliance(hos, planned_drive_hours=3.0, planned_on_duty_hours=3.0)
    assert not comp
    assert any("13-Hour Driving Limit" in v for v in viols)


def test_hos_cycle_1_compliance():
    hos = HOSStatus(
        driver_id=2,
        first_name="CompliantDriver",
        current_duty=0,
        duty_status_desc="Off-Duty",
        shift_driving_hours=2.0,
        shift_on_duty_hours=3.0,
        shift_elapsed_hours=4.0,
        remaining_hours_can_7=35.0
    )
    comp, viols = evaluate_hos_compliance(hos, planned_drive_hours=4.0, planned_on_duty_hours=5.0)
    assert comp
    assert len(viols) == 0


def test_geofence_detection_milton():
    # Coordinates in Milton near RoadStar terminal
    lat, lng = 43.5183, -79.8774
    gf = find_containing_geofence(lat, lng)
    assert gf is not None
    assert "Milton" in gf.name


def test_detention_billing_under_and_over_2_hours():
    now = datetime.now()
    
    # 1. Wait 1.5 hours -> $0 detention (within free 2 hours)
    arr_1_5h = now - timedelta(hours=1.5)
    wait_h, billable_h, fee = calculate_detention_billing(arr_1_5h, now, free_hours=2.0, hourly_rate_cad=95.0)
    assert round(wait_h, 1) == 1.5
    assert billable_h == 0.0
    assert fee == 0.0

    # 2. Wait 3.5 hours -> 1.5 billable hours * $95 = $142.50 CAD
    arr_3_5h = now - timedelta(hours=3.5)
    wait_h, billable_h, fee = calculate_detention_billing(arr_3_5h, now, free_hours=2.0, hourly_rate_cad=95.0)
    assert round(wait_h, 1) == 3.5
    assert round(billable_h, 1) == 1.5
    assert fee == 142.50


def test_backhaul_matching_and_weight_audit():
    outbound = OrderModel(
        bill_number="1001",
        trip_number="2001",
        customer_name="Mondelez",
        origin_city="MILTON",
        origin_prov="ON",
        origin_pc="L9T 5B4",
        dest_city="LONDON",
        dest_prov="ON",
        dest_pc="N6A 4G5",
        distance_miles=115.0,
        weight_lbs=38000.0,
        rate_cad=1250.0
    )
    
    return_cand = OrderModel(
        bill_number="1002",
        trip_number="2002",
        customer_name="Labatt Brewing",
        origin_city="LONDON",
        origin_prov="ON",
        origin_pc="N6A 4M8",
        dest_city="MISSISSAUGA",
        dest_prov="ON",
        dest_pc="L5T 2B2",
        distance_miles=110.0,
        weight_lbs=42000.0,
        rate_cad=1300.0
    )
    
    driver = DriverModel(
        driver_id=10,
        first_name="Alex",
        email="alex@roadstar.ca",
        home_zone="RSTAR",
        status="AVAIL",
        lat=43.5183,
        lng=-79.8774,
        location_desc="Milton Terminal",
        hos=HOSStatus(
            driver_id=10,
            first_name="Alex",
            remaining_hours_can_7=60.0
        )
    )
    
    result = match_backhaul_and_audit(outbound, [return_cand], [driver])
    assert result.return_order is not None
    assert result.return_order.bill_number == "1002"
    assert result.deadhead_reduction_pct == 87.0
    assert result.empty_miles_saved == 100.1
    assert result.hos_audit_passed
    assert result.weight_audit_passed
    assert result.total_revenue_cad == 2550.0
