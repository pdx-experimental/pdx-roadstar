import pytest
import sys
sys.path.insert(0, r"d:\ProDocuX\prodocux-labs\incubator\pdx-roadstar\packages")
sys.path.insert(0, r"d:\ProDocuX\prodocux-labs\incubator\pdx-roadstar\simulator")

from roadstar_domain.models import DriverModel, HOSStatus
from truck_simulator import TelematicsSimulator


def test_telematics_simulator_tick():
    d1 = DriverModel(
        driver_id=1,
        first_name="Driver1",
        email="d1@roadstar.ca",
        home_zone="RSTAR",
        status="AVAIL",
        lat=43.5183,
        lng=-79.8774,
        location_desc="Milton",
        hos=HOSStatus(driver_id=1, first_name="Driver1", remaining_hours_can_7=60.0)
    )
    d2 = DriverModel(
        driver_id=2,
        first_name="Driver2",
        email="d2@roadstar.ca",
        home_zone="RSTAR",
        status="AVAIL",
        lat=43.3000,
        lng=-80.5500,
        location_desc="Ayr",
        hos=HOSStatus(driver_id=2, first_name="Driver2", remaining_hours_can_7=50.0)
    )
    d3 = DriverModel(
        driver_id=3,
        first_name="Driver3",
        email="d3@roadstar.ca",
        home_zone="RSTAR",
        status="AVAIL",
        lat=42.9849,
        lng=-81.2453,
        location_desc="London",
        hos=HOSStatus(driver_id=3, first_name="Driver3", remaining_hours_can_7=40.0)
    )

    sim = TelematicsSimulator([d1, d2, d3])
    state = sim.get_state()
    assert len(state["trucks"]) == 3
    assert len(state["active_detentions"]) >= 1  # Truck 3 starts with >2h dwell

    # Advance 15 minutes
    new_state = sim.tick(elapsed_minutes=15.0)
    assert len(new_state["trucks"]) == 3
    # Truck 3 at dock should have increased wait hours
    t3 = [t for t in new_state["trucks"] if t["truck_id"] == "TRK-B5794"][0]
    assert t3["at_dock"]
    assert t3["detention"]["total_wait_hours"] > 2.7
