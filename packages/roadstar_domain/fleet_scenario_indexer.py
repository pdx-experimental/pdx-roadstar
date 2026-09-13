"""Fleet Scenario Indexer and Loader for Full Fleet Multi-Day Simulation."""
import os
import json
from typing import Dict, List, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.environ.get(
    "ROADSTAR_SCENARIO_INDEX_PATH",
    os.path.join(BASE_DIR, "data", "indexed_scenarios.json"),
)

def get_available_dates() -> List[Dict[str, Any]]:
    """Returns all available operational dates and summary counts."""
    if not os.path.exists(CACHE_PATH):
        raise FileNotFoundError(f"Scenario cache not found at {CACHE_PATH}")

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    date_list = []
    for d in data.get("dates", []):
        sc = data.get("scenarios", {}).get(d, {})
        date_list.append({
            "date": d,
            "total_trucks": len({leg["truck_id"] for leg in sc.get("legs", [])}),
            "total_legs": len(sc.get("legs", [])),
            "empty_legs": sc.get("empty_legs", 0),
            "detention_legs": sc.get("detention_legs", 0),
            "total_miles": sc.get("total_miles", 0)
        })
    return date_list

def get_scenario_for_date(date_str: str) -> Dict[str, Any]:
    """Returns the full fleet operational scenario for the selected date."""
    if not os.path.exists(CACHE_PATH):
        raise FileNotFoundError(f"Scenario cache not found at {CACHE_PATH}")
        
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if date_str in data.get("scenarios", {}):
        return data["scenarios"][date_str]
    
    raise ValueError(f"No scenario found for date {date_str}")
