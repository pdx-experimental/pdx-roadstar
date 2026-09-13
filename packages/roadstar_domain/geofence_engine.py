import math
from datetime import datetime
from typing import List, Optional, Tuple
from .models import Geofence, DetentionRecord

SOUTHERN_ONTARIO_GEOFENCES = [
    Geofence(id="GEO-MILTON-HUB", name="Milton Terminal Hub (RoadStar HQ)", city="Milton", lat=43.5183, lng=-79.8774, radius_meters=2000.0, facility_type="TERMINAL_HUB"),
    Geofence(id="GEO-LONDON-HUB", name="London Distribution Hub", city="London", lat=42.9849, lng=-81.2453, radius_meters=2000.0, facility_type="TERMINAL_HUB"),
    Geofence(id="GEO-BRAMPTON-YYZ", name="Brampton Intermodal & Logistics Gateway", city="Brampton", lat=43.7250, lng=-79.6800, radius_meters=1500.0, facility_type="CUSTOMER_DOCK"),
    Geofence(id="GEO-MISSISSAUGA", name="Mississauga Industrial Park Docks", city="Mississauga", lat=43.6000, lng=-79.6500, radius_meters=1500.0, facility_type="CUSTOMER_DOCK"),
    Geofence(id="GEO-CAMBRIDGE", name="Cambridge Automotive Parts Center", city="Cambridge", lat=43.3616, lng=-80.3144, radius_meters=1500.0, facility_type="CUSTOMER_DOCK"),
    Geofence(id="GEO-WOODSTOCK", name="Woodstock Freight Cross-Dock", city="Woodstock", lat=43.1315, lng=-80.7472, radius_meters=1500.0, facility_type="CUSTOMER_DOCK"),
    Geofence(id="GEO-BARRIE", name="Barrie Northern Gateway Facility", city="Barrie", lat=44.3894, lng=-79.6903, radius_meters=1800.0, facility_type="CUSTOMER_DOCK"),
    Geofence(id="GEO-NIAGARA", name="Niagara Falls Border Terminal", city="Niagara Falls", lat=43.0896, lng=-79.0849, radius_meters=1800.0, facility_type="CUSTOMER_DOCK"),
]


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000  # meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_containing_geofence(lat: float, lng: float) -> Optional[Geofence]:
    for gf in SOUTHERN_ONTARIO_GEOFENCES:
        dist = haversine_distance_meters(lat, lng, gf.lat, gf.lng)
        if dist <= gf.radius_meters:
            return gf
    return None


def calculate_detention_billing(
    arrival_time: datetime,
    current_time: datetime,
    free_hours: float = 2.0,
    hourly_rate_cad: float = 95.0
) -> Tuple[float, float, float]:
    """Calculates total wait hours, billable detention hours (>2h), and total fee in CAD."""
    delta_seconds = (current_time - arrival_time).total_seconds()
    total_wait_hours = max(0.0, delta_seconds / 3600.0)
    billable_hours = max(0.0, total_wait_hours - free_hours)
    total_fee = round(billable_hours * hourly_rate_cad, 2)
    return round(total_wait_hours, 2), round(billable_hours, 2), total_fee
