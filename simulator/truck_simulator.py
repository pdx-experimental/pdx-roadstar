"""Southern Ontario Highway 401 Corridor Telematics & Delay Simulation Engine."""
from __future__ import annotations
import math
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from roadstar_domain.models import DriverModel, Geofence, DetentionRecord
from roadstar_domain.geofence_engine import (
    SOUTHERN_ONTARIO_GEOFENCES,
    find_containing_geofence,
    calculate_detention_billing,
)
from roadstar_domain.hos_engine import update_hos_tick

# Key Highway 401 Waypoints between Milton and London
HWY_401_CORRIDOR_WAYPOINTS = [
    {"name": "Milton RoadStar HQ", "lat": 43.5183, "lng": -79.8774},
    {"name": "Highway 401 / Hwy 6 (Guelph)", "lat": 43.4680, "lng": -80.1200},
    {"name": "Cambridge / Hwy 24", "lat": 43.4150, "lng": -80.3200},
    {"name": "Kitchener / Homer Watson", "lat": 43.3900, "lng": -80.4400},
    {"name": "Ayr / Drumbo Interchange", "lat": 43.3000, "lng": -80.5500},
    {"name": "Woodstock / Hwy 403 Junction", "lat": 43.1315, "lng": -80.7472},
    {"name": "Ingersoll Rest Area", "lat": 43.0300, "lng": -80.8900},
    {"name": "Dorchester Bypass", "lat": 42.9950, "lng": -81.0800},
    {"name": "London Terminal Hub", "lat": 42.9849, "lng": -81.2453},
]


class SimulatedTruck:
    def __init__(self, truck_id: str, driver: DriverModel, start_idx: int = 0):
        self.truck_id = truck_id
        self.driver = driver
        self.waypoint_idx = start_idx
        self.progress_between = 0.0  # 0.0 to 1.0 between current and next waypoint
        self.direction = 1  # 1 = westward to London, -1 = eastward to Milton
        self.speed_kmh = 98.0
        self.current_lat = HWY_401_CORRIDOR_WAYPOINTS[start_idx]["lat"]
        self.current_lng = HWY_401_CORRIDOR_WAYPOINTS[start_idx]["lng"]
        self.odometer_km = 142850.0
        self.trip_distance_km = 0.0
        self.breadcrumbs: List[Dict[str, float]] = [{"lat": self.current_lat, "lng": self.current_lng}]
        self.is_delayed_hwy401 = False
        self.at_dock = False
        self.dock_arrival_time: Optional[datetime] = None
        self.current_geofence: Optional[Geofence] = None
        self.detention_record: Optional[DetentionRecord] = None


class TelematicsSimulator:
    def __init__(self, drivers: List[DriverModel]):
        self.current_sim_time = datetime(2026, 8, 14, 11, 0, 0, tzinfo=timezone.utc)
        self.trucks: Dict[str, SimulatedTruck] = {}
        self.detention_history: List[DetentionRecord] = []
        
        # Initialize primary simulation trucks
        if drivers:
            t1 = SimulatedTruck("TRK-B3339", drivers[0], start_idx=0)  # Starting at Milton
            self.trucks[t1.truck_id] = t1
        if len(drivers) > 1:
            t2 = SimulatedTruck("TRK-B8269", drivers[1], start_idx=4)  # Mid-corridor near Ayr
            self.trucks[t2.truck_id] = t2
        if len(drivers) > 2:
            t3 = SimulatedTruck("TRK-B5794", drivers[2], start_idx=8)  # London dock
            t3.at_dock = True
            t3.dock_arrival_time = self.current_sim_time - timedelta(hours=2.7)  # Over 2 hours!
            t3.current_geofence = SOUTHERN_ONTARIO_GEOFENCES[1]  # London Hub
            # Create active detention record
            rec = DetentionRecord(
                record_id="DET-LON-8821",
                trip_number="TRIP-622819",
                bill_number="BOL-412300",
                driver_id=t3.driver.driver_id,
                driver_name=t3.driver.first_name,
                facility_id="GEO-LONDON-HUB",
                facility_name="London Distribution Hub (Dock 12)",
                geofence_arrival_time=t3.dock_arrival_time,
                geofence_departure_time=None,
                free_time_hours=2.0,
                total_wait_hours=2.7,
                billable_hours=0.7,
                hourly_rate_cad=95.0,
                total_detention_fee_cad=66.50,
                status="WAITING"
            )
            t3.detention_record = rec
            self.detention_history.append(rec)
            self.trucks[t3.truck_id] = t3

    def tick(self, elapsed_minutes: float = 5.0) -> Dict[str, Any]:
        """Advances simulation by elapsed_minutes."""
        if not isinstance(elapsed_minutes, (int, float)) or math.isnan(elapsed_minutes) or math.isinf(elapsed_minutes) or elapsed_minutes <= 0:
            raise ValueError(f"Invalid elapsed_minutes: {elapsed_minutes}. Must be positive finite float.")

        self.current_sim_time += timedelta(minutes=elapsed_minutes)
        elapsed_hours = elapsed_minutes / 60.0

        for t in self.trucks.values():
            if t.at_dock:
                # Truck is dwelling at dock
                update_hos_tick(t.driver.hos, elapsed_hours, duty_mode=3)  # On-duty dock
                if t.detention_record:
                    wait_h, billable_h, fee = calculate_detention_billing(
                        t.detention_record.geofence_arrival_time,
                        self.current_sim_time,
                        free_hours=t.detention_record.free_time_hours,
                        hourly_rate_cad=t.detention_record.hourly_rate_cad
                    )
                    t.detention_record.total_wait_hours = wait_h
                    t.detention_record.billable_hours = billable_h
                    t.detention_record.total_detention_fee_cad = fee
                continue

            # In transit
            effective_speed = 22.0 if t.is_delayed_hwy401 else t.speed_kmh
            dist_travelled_km = effective_speed * elapsed_hours
            t.odometer_km += dist_travelled_km
            t.trip_distance_km += dist_travelled_km

            # Update HOS
            update_hos_tick(t.driver.hos, elapsed_hours, duty_mode=2)  # Driving

            # Advance along waypoint segments
            curr_wp = HWY_401_CORRIDOR_WAYPOINTS[t.waypoint_idx]
            next_idx = t.waypoint_idx + t.direction
            if next_idx < 0 or next_idx >= len(HWY_401_CORRIDOR_WAYPOINTS):
                # Reverse direction (e.g. turnaround or return leg)
                t.direction *= -1
                next_idx = t.waypoint_idx + t.direction

            next_wp = HWY_401_CORRIDOR_WAYPOINTS[next_idx]

            # Linear interpolation between waypoints
            t.progress_between += 0.12 * (1.0 if not t.is_delayed_hwy401 else 0.25)
            if t.progress_between >= 1.0:
                t.progress_between = 0.0
                t.waypoint_idx = next_idx
                t.current_lat = next_wp["lat"]
                t.current_lng = next_wp["lng"]
            else:
                t.current_lat = curr_wp["lat"] + (next_wp["lat"] - curr_wp["lat"]) * t.progress_between
                t.current_lng = curr_wp["lng"] + (next_wp["lng"] - curr_wp["lng"]) * t.progress_between

            t.driver.lat = t.current_lat
            t.driver.lng = t.current_lng
            t.breadcrumbs.append({"lat": round(t.current_lat, 5), "lng": round(t.current_lng, 5)})
            if len(t.breadcrumbs) > 40:
                t.breadcrumbs.pop(0)

            # Check geofence entry
            gf = find_containing_geofence(t.current_lat, t.current_lng)
            if gf and not t.current_geofence:
                t.current_geofence = gf
                # Entered facility!
                if "DOCK" in gf.facility_type or "HUB" in gf.facility_type:
                    t.at_dock = True
                    t.dock_arrival_time = self.current_sim_time
                    rec_id = f"DET-{gf.city.upper()[:3]}-{self.current_sim_time.strftime('%M%S')}"
                    rec = DetentionRecord(
                        record_id=rec_id,
                        trip_number="TRIP-622820",
                        bill_number="BOL-412305",
                        driver_id=t.driver.driver_id,
                        driver_name=t.driver.first_name,
                        facility_id=gf.id,
                        facility_name=gf.name,
                        geofence_arrival_time=self.current_sim_time,
                        free_time_hours=2.0,
                        total_wait_hours=0.0,
                        billable_hours=0.0,
                        hourly_rate_cad=95.0,
                        total_detention_fee_cad=0.0,
                        status="WAITING"
                    )
                    t.detention_record = rec
                    self.detention_history.append(rec)
            elif not gf:
                if t.current_geofence and t.detention_record:
                    # Departed geofence
                    t.detention_record.geofence_departure_time = self.current_sim_time
                    t.detention_record.status = "COMPLETED"
                t.current_geofence = None

        return self.get_state()

    def trigger_hwy401_incident(self, delayed: bool = True) -> None:
        for t in self.trucks.values():
            if not t.at_dock:
                t.is_delayed_hwy401 = delayed

    def release_dock_dwell(self, truck_id: str) -> None:
        if truck_id in self.trucks:
            t = self.trucks[truck_id]
            t.at_dock = False
            if t.detention_record:
                t.detention_record.geofence_departure_time = self.current_sim_time
                t.detention_record.status = "COMPLETED"

    def get_state(self) -> Dict[str, Any]:
        return {
            "sim_time": self.current_sim_time.isoformat(),
            "trucks": [
                {
                    "truck_id": t.truck_id,
                    "driver_id": t.driver.driver_id,
                    "driver_name": t.driver.first_name,
                    "lat": round(t.current_lat, 5),
                    "lng": round(t.current_lng, 5),
                    "speed_kmh": round(22.0 if t.is_delayed_hwy401 else t.speed_kmh, 1),
                    "odometer_km": round(t.odometer_km, 1),
                    "is_delayed_hwy401": t.is_delayed_hwy401,
                    "at_dock": t.at_dock,
                    "geofence": t.current_geofence.name if t.current_geofence else None,
                    "breadcrumbs": t.breadcrumbs,
                    "hos": t.driver.hos.model_dump(),
                    "detention": t.detention_record.model_dump() if t.detention_record else None
                }
                for t in self.trucks.values()
            ],
            "active_detentions": [
                r.model_dump() for r in self.detention_history if r.total_wait_hours > 2.0
            ]
        }
