"""Run repeatable end-to-end scenario accounting audits."""
from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages"), str(ROOT / "simulator")]

from roadstar_application.scenario_comparison import ScenarioComparison


def run_round(round_number: int, target_date: str, tick_minutes: int) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"roadstar-audit-{round_number}-") as tmp:
        comparison = ScenarioComparison(target_date, storage_dir=Path(tmp))
        initial = comparison.get_state()
        assert initial["sim_minute"] == 0
        assert initial["baseline"]["active_trucks"] == []
        assert initial["pdx"]["active_trucks"] == []
        assert initial["interventions"] == []

        state = initial
        for _ in range(960 // tick_minutes):
            state = comparison.tick(tick_minutes)
        completed = [i for i in state["interventions"] if not i["type"].endswith("ABORTED")]
        backhauls = [i for i in completed if i["type"] == "PDX_BACKHAUL_MATCH"]
        dossiers = [i for i in completed if i["type"] == "PRODOCUX_DETENTION_DOSSIER"]
        aborted = [i for i in state["interventions"] if i["type"].endswith("ABORTED")]

        d = state["deltas"]
        recomputed = round(
            d["new_backhaul_revenue_cad"]
            + d["detention_gain_cad"]
            - d["added_operating_cost_cad"], 2
        )
        assert recomputed == d["net_profit_delta_cad"]
        assert round(state["pdx"]["net_profit"] - state["baseline"]["net_profit"], 2) == d["net_profit_delta_cad"]
        assert d["interventions_count"] == len(completed)
        assert len({i["run_id"] for i in backhauls}) == len(backhauls)
        assert len(comparison.claimed_bills) == len(backhauls)
        assert all(i.get("financial_delta") == "$0.00 CAD" for i in aborted)
        assert all((comparison.root / "dossiers" / i["filename"]).is_file() for i in dossiers)
        matched_orders = [o for o in comparison.orders if o.bill_number in comparison.claimed_bills]

        return {
            "round": round_number,
            "target_date": target_date,
            "tick_minutes": tick_minutes,
            "released_legs": len(state["baseline"]["active_trucks"]),
            "completed_interventions": len(completed),
            "engine_backhauls": len(backhauls),
            "kernel_dossiers": len(dossiers),
            "aborted_zero_credit": len(aborted),
            "aborted_reasons": dict(Counter(i["desc"].split(":", 1)[0] for i in aborted)),
            "empty_miles_saved": d["empty_miles_saved"],
            "claimed_bills": len(comparison.claimed_bills),
            "matched_bill_numbers": sorted(comparison.claimed_bills),
            "matched_orders": sorted([{
                "bill_number": o.bill_number,
                "route": f"{o.origin_city}, {o.origin_prov} -> {o.dest_city}, {o.dest_prov}",
                "distance_miles": o.distance_miles,
                "weight_lbs": o.weight_lbs,
                "rate_cad": o.rate_cad,
            } for o in matched_orders], key=lambda row: row["bill_number"]),
            "backhaul_revenue_cad": d["new_backhaul_revenue_cad"],
            "detention_gain_cad": d["detention_gain_cad"],
            "added_operating_cost_cad": d["added_operating_cost_cad"],
            "net_profit_delta_cad": d["net_profit_delta_cad"],
            "recomputed_delta_cad": recomputed,
            "baseline_net_profit_cad": state["baseline"]["net_profit"],
            "pdx_net_profit_cad": state["pdx"]["net_profit"],
        }


if __name__ == "__main__":
    rounds = [
        run_round(1, "2026-08-14", 960),
        run_round(2, "2026-08-14", 15),
        run_round(3, "2026-08-13", 60),
        run_round(4, "2026-08-27", 60),
        run_round(5, "2026-07-24", 60),
    ]
    same_day = [row for row in rounds if row["target_date"] == "2026-08-14"]
    ignored = {"round", "tick_minutes"}
    assert len({json.dumps({k: v for k, v in row.items() if k not in ignored}, sort_keys=True) for row in same_day}) == 1
    assert all(row["engine_backhauls"] == 0 and row["backhaul_revenue_cad"] == 0 for row in rounds)
    print(json.dumps({
        "public_packages": {
            "prodocux": version("prodocux"),
            "pdx-artifact-engine": version("pdx-artifact-engine"),
        },
        "rounds": rounds,
        "repeatable": True,
    }, indent=2))
