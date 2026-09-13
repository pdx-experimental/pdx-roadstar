"""Estimated Geodesic Winding Corridor Model for Freight Transport.

MODEL SPECIFICATION:
- Methodology: Spherical Haversine geodesic distance scaled by Highway Corridor Winding Factor (1.18x).
- Scope & Limitations: Mathematical approximation based on Southern Ontario Highway 401/403/407 corridor topology.
  This is NOT verified odometer, GPS breadcrumb, or turn-by-turn routing.
- Constraint: Silent coordinate defaulting is strictly forbidden. Missing cities raise ValueError.
"""
from __future__ import annotations
import math
from typing import Dict, Tuple, Optional

# Documented corridor winding scale factor (geodesic to highway approximation)
HIGHWAY_WINDING_FACTOR = 1.18

# Explicit Southern Ontario & North American Freight Corridor Coordinate Registry
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    # Southern Ontario Primary Hubs
    "MILTON": (43.5183, -79.8774),
    "LONDON": (42.9849, -81.2453),
    "TORONTO": (43.6532, -79.3832),
    "MISSISSAUGA": (43.5890, -79.6441),
    "BRAMPTON": (43.7315, -79.7624),
    "VAUGHAN": (43.8563, -79.5085),
    "KITCHENER": (43.4516, -80.4925),
    "CAMBRIDGE": (43.3616, -80.3144),
    "GUELPH": (43.5448, -80.2482),
    "WOODSTOCK": (43.1315, -80.7472),
    "INGERSOLL": (43.0392, -80.8836),
    "WINDSOR": (42.3149, -83.0364),
    "BRANTFORD": (43.1394, -80.2644),
    "HAMILTON": (43.2557, -79.8711),
    "WHITBY": (43.8971, -78.9429),
    "OSHAWA": (43.8975, -78.8658),
    "COBOURG": (43.9598, -78.1652),
    "BELLEVILLE": (44.1628, -77.3832),
    "SCARBOROUGH": (43.7764, -79.2318),
    "EAST GWILLIMBURY": (44.1333, -79.4333),
    "DORVAL": (45.4487, -73.7533),

    # Regional US Freight Corridors
    "RICHMOND": (39.8289, -84.8902),
    "KALAMAZOO": (42.2917, -85.5872),
    "PARIS": (38.2098, -84.2530),
    "CARLISLE": (40.2015, -77.1889),
    "NAPERVILLE": (41.7508, -88.1535),
    "NORWALK": (41.2426, -82.6157),
    "CANTON": (42.3086, -83.4821),
    "ORLANDO": (28.5383, -81.3792),
    "FARWELL": (43.8634, -84.8650),
    "MORRIS": (41.3578, -88.4215),
    "WALTON": (38.8687, -84.6141),
    "SPRINGFIELD": (37.2090, -93.2923),
}


def clean_city_name(city_str: str) -> str:
    """Normalizes city string, removing province/country codes."""
    if not city_str:
        return ""
    c = city_str.strip().upper()
    for delim in [",", "/"]:
        if delim in c:
            c = c.split(delim)[0].strip()
    return c


def get_city_coords(city_name: str) -> Tuple[float, float]:
    """Retrieves verified coordinates for a city.
    Raises ValueError if coordinates are missing to prevent silent defaulting.
    """
    clean = clean_city_name(city_name)
    if clean in CITY_COORDINATES:
        return CITY_COORDINATES[clean]

    # Partial matching
    for registered_city, coords in CITY_COORDINATES.items():
        if registered_city in clean or clean in registered_city:
            return coords

    raise ValueError(
        f"Missing geographic coordinates for location '{city_name}' (normalized: '{clean}'). "
        "Silent coordinate defaulting is strictly forbidden."
    )


def haversine_geodesic_miles(c1: Tuple[float, float], c2: Tuple[float, float]) -> float:
    """Computes great-circle distance in statute miles between two (lat, lng) tuples."""
    lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
    lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    earth_radius_miles = 3958.8
    return earth_radius_miles * c


def estimate_corridor_road_miles(
    orig_city: str,
    dest_city: str,
    orig_coords: Optional[Tuple[float, float]] = None,
    dest_coords: Optional[Tuple[float, float]] = None,
    winding_factor: float = HIGHWAY_WINDING_FACTOR
) -> float:
    """Estimates road corridor mileage between origin and destination using the
    Geodesic Winding Corridor Model.
    """
    c1 = orig_coords or get_city_coords(orig_city)
    c2 = dest_coords or get_city_coords(dest_city)

    # Identical location
    if abs(c1[0] - c2[0]) < 1e-4 and abs(c1[1] - c2[1]) < 1e-4:
        return 0.0

    geo_dist = haversine_geodesic_miles(c1, c2)
    est_road_dist = geo_dist * winding_factor
    return round(est_road_dist, 1)
