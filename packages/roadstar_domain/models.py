from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class HOSStatus(BaseModel):
    driver_id: int
    first_name: str
    current_duty: int = 0  # 0: Off-duty, 1: Sleeper, 2: Driving, 3: On-duty (not driving)
    duty_status_desc: str = "Off-Duty"
    remaining_hours_can_7: float = 70.0  # Canadian Cycle 1 (70h/7d)
    remaining_hours_can_14: float = 120.0  # Canadian Cycle 2 (120h/14d)
    shift_driving_hours: float = 0.0  # Max 13h
    shift_on_duty_hours: float = 0.0  # Max 14h
    shift_elapsed_hours: float = 0.0  # Max 16h window
    is_compliant: bool = True
    violations: List[str] = Field(default_factory=list)


class DriverModel(BaseModel):
    driver_id: int
    first_name: str
    email: str
    home_zone: str
    status: str  # AVAIL, ASSGN, DISP, DEPSHIP, DEPCONS, VACATION
    lat: Optional[float]
    lng: Optional[float]
    location_desc: str
    current_trip: int = 0
    assigned_truck: Optional[str] = None
    hos: HOSStatus


class OrderModel(BaseModel):
    bill_number: str
    trip_number: str
    customer_name: str
    origin_city: str
    origin_prov: str
    origin_pc: str
    dest_city: str
    dest_prov: str
    dest_pc: str
    distance_miles: float
    load_type: str = "Dry Van"
    load_description: str = "General Freight"
    weight_lbs: float = 0.0
    pallets: int = 0
    temperature: str = "Ambient"
    temp_controlled: bool = False
    status: str = "OPEN"  # OPEN, PLANNED, DISPATCHED, DELIVERED
    assigned_driver: Optional[str] = None
    rate_cad: float = 0.0
    pickup_time: Optional[datetime] = None
    delivery_time: Optional[datetime] = None
    currently_assigned: bool = False
    is_synthetic_projection: bool = False
    original_pickup_time: Optional[datetime] = None
    projection_shift_days: int = 0


class Geofence(BaseModel):
    id: str
    name: str
    city: str
    province: str = "ON"
    lat: float
    lng: float
    radius_meters: float = 1500.0
    facility_type: str = "CUSTOMER_DOCK"  # TERMINAL_HUB, CUSTOMER_DOCK


class DetentionRecord(BaseModel):
    record_id: str
    trip_number: str
    bill_number: str
    driver_id: int
    driver_name: str
    facility_id: str
    facility_name: str
    geofence_arrival_time: datetime
    geofence_departure_time: Optional[datetime] = None
    free_time_hours: float = 2.0
    total_wait_hours: float = 0.0
    billable_hours: float = 0.0
    hourly_rate_cad: float = 95.0
    total_detention_fee_cad: float = 0.0
    status: str = "WAITING"  # WAITING, COMPLETED, BILLED, DISPUTE_SECURED
    pdf_sha256: Optional[str] = None  # SHA-256 hex digest of the raw PDF binary bytes
    audit_canonical_digest: Optional[str] = None  # Canonical digest of the ProDocuX audit request
    dossier_sha256: Optional[str] = None  # Backwards-compatible alias for audit request digest
    dossier_filename: Optional[str] = None
    asset_id: Optional[str] = None


class BackhaulMatchResult(BaseModel):
    outbound_order: OrderModel
    return_order: Optional[OrderModel] = None
    deadhead_reduction_pct: float = 0.0
    empty_miles_saved: float = 0.0
    total_revenue_cad: float = 0.0
    hos_audit_passed: bool = True
    weight_audit_passed: bool = True
    assigned_driver_id: int = 0
    driver_name: str = ""
    notes: List[str] = Field(default_factory=list)
