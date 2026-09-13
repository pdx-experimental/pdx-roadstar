"""Build the bundled Southern Ontario vector basemap from one Overpass query."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

BBOX = "42.85,-81.50,43.65,-79.75"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY = f'''[out:json][timeout:90];
(
  way["highway"~"motorway|trunk|primary"]({BBOX});
  way["waterway"="river"]({BBOX});
);
out tags geom;'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "PDX-RoadStar/0.1 (https://github.com/pdx-experimental/pdx-roadstar)"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)

    features = []
    for element in payload.get("elements", []):
        geometry = element.get("geometry") or []
        if len(geometry) < 2:
            continue
        coordinates = [[round(p["lon"], 5), round(p["lat"], 5)] for p in geometry]
        tags = element.get("tags") or {}
        features.append({
            "type": "Feature",
            "properties": {
                "kind": "water" if tags.get("waterway") else "road",
                "class": tags.get("highway") or tags.get("waterway"),
                "name": tags.get("name", ""),
                "ref": tags.get("ref", ""),
            },
            "geometry": {"type": "LineString", "coordinates": coordinates},
        })

    result = {
        "type": "FeatureCollection",
        "attribution": "© OpenStreetMap contributors, ODbL 1.0",
        "source": "https://www.openstreetmap.org/copyright",
        "bbox": [-81.50, 42.85, -79.75, 43.65],
        "features": features,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(features)} features to {args.output}")


if __name__ == "__main__":
    main()
