"""Read-only fleet scenario playback. No dispatch, approval or artifact side effects."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import threading
from roadstar_domain.fleet_scenario_indexer import get_scenario_for_date


class FleetSimulator:
    """Synthetic timetable over dataset legs; never imports PDX or Kernel adapters."""
    def __init__(self, target_date_str="2026-08-14", enable_stochastic=True):
        self.target_date_str = target_date_str
        datetime.strptime(target_date_str, "%Y-%m-%d")
        self.scenario = get_scenario_for_date(target_date_str)
        if not self.scenario.get("legs"):
            raise ValueError("Scenario has no legs; no fabricated fallback is available")
        self.enable_stochastic = enable_stochastic
        self._lock = threading.RLock()
        self.reset()

    def reset(self):
        with self._lock:
            self.sim_minute = 0.0
            self.is_finished = False
            self.legs = []
            timeline = {}
            for idx, source in enumerate(self.scenario["legs"]):
                truck = source["truck_id"]
                distance = float(source["distance_miles"])
                dwell = float(source["dwell_hours"])
                if not math.isfinite(distance) or distance < 0 or not math.isfinite(dwell) or dwell < 0:
                    raise ValueError(f"Invalid scenario distance/dwell for {truck}")
                start = timeline.get(truck, (sum(map(ord, truck)) * 17) % 180)
                duration = max(1.0, distance / 55 * 60)
                end = start + duration
                timeline[truck] = end + max(30, dwell * 60)
                origin = (source.get("orig_lat"), source.get("orig_lng"))
                destination = (source.get("dest_lat"), source.get("dest_lng"))
                # Cache coordinates have no GPS provenance. In particular, a
                # positive-distance leg with identical endpoints cannot animate.
                valid = all(isinstance(v, (int, float)) and math.isfinite(v) for v in origin + destination)
                valid = valid and all(abs(c[0]) <= 90 and abs(c[1]) <= 180 for c in (origin, destination))
                valid = valid and not (distance > 0 and origin == destination)
                self.legs.append(dict(
                    id=truck, leg_id=f"{self.target_date_str}:{idx}", driver=source["driver_name"],
                    orig=source["origin"], dest=source["destination"],
                    orig_coords=origin if valid else None, dest_coords=destination if valid else None,
                    geometry_status="dataset_endpoints_unverified" if valid else "unavailable",
                    lat=None, lng=None, start_min=start, end_min=end, dist=distance,
                    is_empty=bool(source["is_empty"]), dwell=dwell, speed=0,
                    leg_type="Empty Deadhead Return" if source["is_empty"] else "Loaded Linehaul",
                    status="Staging / Ready"))
            self.truck_count = len({leg["id"] for leg in self.legs})
            self.legs_count = len(self.legs)
            self._update()
            return self.get_state()

    def _update(self):
        total = empty = dwell_hours = revenue = 0.0
        running = 0
        for leg in self.legs:
            start, end = leg["start_min"], leg["end_min"]
            fraction = min(1.0, max(0.0, (self.sim_minute - start) / (end - start)))
            miles = leg["dist"] * fraction
            total += miles
            empty += miles if leg["is_empty"] else 0
            if not leg["is_empty"]:
                revenue += miles * 2.85  # Explicit simulation assumption, not invoiced revenue.
            elapsed_dwell = min(leg["dwell"], max(0, (self.sim_minute - end) / 60))
            dwell_hours += max(0, elapsed_dwell - 2)
            moving = start <= self.sim_minute < end
            running += int(moving)
            leg["speed"] = round(leg["dist"] / (end - start) * 60 * 1.609344, 1) if moving else 0
            leg["status"] = ("Pre-Trip / Loading" if self.sim_minute < start else
                             "In Transit" if moving else
                             "Dock Dwell" if self.sim_minute < end + leg["dwell"] * 60 else
                             "Delivery Complete / Staged")
            if leg["orig_coords"] is not None:
                leg["lat"], leg["lng"] = tuple(round(a + (b-a)*fraction, 5)
                    for a,b in zip(leg["orig_coords"], leg["dest_coords"]))
        cost = total * 1.85
        # A scenario leg exists in the source schedule, but it does not become a
        # simulated trip until playback has started and its release time is due.
        released_legs = [leg for leg in self.legs
                         if self.sim_minute > 0 and leg["start_min"] <= self.sim_minute]
        self.baseline = dict(total_miles=round(total, 1), empty_miles=round(empty, 1),
            loaded_miles=round(total-empty, 1), deadhead_pct=round(empty/total*100, 1) if total else 0,
            freight_revenue=round(revenue, 2), running_cost=round(cost, 2),
            unbilled_detention_hours=round(dwell_hours, 2), disputed_detention_loss=round(dwell_hours*95, 2),
            net_profit=round(round(revenue, 2)-round(cost, 2), 2), running_count=running,
            active_trucks=released_legs)

    def tick(self, elapsed_minutes=5.0):
        if isinstance(elapsed_minutes, bool) or not isinstance(elapsed_minutes, (int,float)) or not math.isfinite(elapsed_minutes) or elapsed_minutes <= 0:
            raise ValueError("elapsed_minutes must be a positive finite number")
        with self._lock:
            self.sim_minute = min(960, self.sim_minute + elapsed_minutes)
            self.is_finished = self.sim_minute >= 960
            self._update()
            return self.get_state()

    def get_state(self):
        with self._lock:
            # Scenario clock is labelled Eastern local time. Avoid depending on
            # host tzdata; the operational date determines EDT/EST.
            month = datetime.strptime(self.target_date_str, "%Y-%m-%d").month
            eastern = timezone(timedelta(hours=-4 if 3 <= month <= 11 else -5), "EDT" if 3 <= month <= 11 else "EST")
            clock = datetime.strptime(self.target_date_str, "%Y-%m-%d").replace(hour=6, tzinfo=eastern) + timedelta(minutes=self.sim_minute)
            return deepcopy(dict(target_date=self.target_date_str, sim_clock=clock.strftime("%H:%M:%S %Z"),
                sim_minute=self.sim_minute, progress_pct=round(self.sim_minute/960*100, 1),
                is_finished=self.is_finished, enable_stochastic=False, fleet_size=self.truck_count,
                legs_count=self.legs_count, baseline=self.baseline,
                geometry_unavailable_legs=sum(t["geometry_status"] == "unavailable" for t in self.legs),
                mode="simulation_only", accounting_basis="Model assumptions: $2.85/loaded mile, $1.85/mi cost, $95/h excess dwell. No invoicing.",
                schedule_basis="Synthetic sequential timetable at 55 mph, not historical departure timestamps."))


# Existing URL/import compatibility; this class no longer executes PDX operations.
DualTrackSimulator = FleetSimulator
