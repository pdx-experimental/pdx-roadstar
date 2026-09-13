import pytest
import sys
sys.path.insert(0, r"d:\ProDocuX\prodocux-labs\incubator\pdx-roadstar\packages")
sys.path.insert(0, r"d:\ProDocuX\prodocux-labs\incubator\pdx-roadstar\simulator")

from dual_track_simulator import DualTrackSimulator


def test_dual_track_initial_and_tick():
    sim = DualTrackSimulator(target_date_str="2026-08-14", enable_stochastic=True)
    state = sim.get_state()
    assert state["sim_clock"] == "06:00:00 EDT"
    assert state["progress_pct"] == 0.0
    assert state["mode"] == "simulation_only"
    assert state["baseline"]["active_trucks"] == []

    # Advance 120 minutes (06:00 -> 08:00)
    sim.tick(elapsed_minutes=120.0)
    s2 = sim.get_state()
    assert s2["sim_minute"] == 120
    assert s2["progress_pct"] > 10.0
    assert s2["baseline"]["total_miles"] > 0
    assert s2["baseline"]["active_trucks"]
    assert all(t["start_min"] <= 120 for t in s2["baseline"]["active_trucks"])
    assert "pdx" not in s2
    assert "interventions" not in s2
