"""Strict legacy day-scenario view with no representative-data fallbacks."""
from __future__ import annotations

from typing import Any, Dict

from .data_loader import load_dataset
from .fleet_scenario_indexer import get_scenario_for_date


def load_day_scenario(target_date_str: str = "2026-08-14") -> Dict[str, Any]:
    """Return source-valid orders and the indexed scenario for one exact date."""
    _, orders = load_dataset()
    scenario = get_scenario_for_date(target_date_str)
    legs = list(scenario.get("legs", []))
    return {
        "target_date": target_date_str,
        "orders": [order.model_dump(mode="json") for order in orders],
        "historical_legs": legs,
        "backhaul_data_status": {
            "eligible_source_orders": len(orders),
            "revenue_eligible": bool(orders),
            "reason": ("eligible source-priced orders available" if orders else
                       "Tlorder has no source freight-rate field; backhaul revenue is blocked"),
        },
        "summary": {
            "total_orders": len(orders),
            "total_legs": len(legs),
            "historical_empty_legs": sum(bool(leg.get("is_empty")) for leg in legs),
            "historical_detention_legs": sum(float(leg.get("dwell_hours", 0)) > 2 for leg in legs),
        },
    }
