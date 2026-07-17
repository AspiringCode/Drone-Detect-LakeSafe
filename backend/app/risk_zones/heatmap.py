from __future__ import annotations

import json
from pathlib import Path

from app.models import RiskZone
from app.risk_zones.tessellation import compute_tessellated_zones


def zones_to_geojson(zones: list[RiskZone]) -> dict:
    features = []
    for zone in zones:
        coordinates = [[point.lon, point.lat] for point in zone.polygon]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
                "properties": {
                    "zone_id": zone.zone_id,
                    "risk_score": zone.risk_score,
                    "is_proxy": zone.is_proxy,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _write_fixture() -> Path:
    path = Path(__file__).resolve().parents[2] / "fixtures" / "lake_sammamish_riskmap.geojson"
    zones = compute_tessellated_zones(
        "lake-sammamish", drone_count=5, use_fixture=True
    )
    path.write_text(json.dumps(zones_to_geojson(zones), indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(_write_fixture())
