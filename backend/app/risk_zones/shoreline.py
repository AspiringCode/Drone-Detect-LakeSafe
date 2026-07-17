"""Load committed lake shoreline polygons."""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import Polygon, shape


class ShorelineNotFoundError(Exception):
    """Raised when a requested lake has no committed shoreline polygon."""


def load_lake_polygon(lake_id: str) -> Polygon:
    """Return the committed shoreline polygon for ``lake_id``.

    Shoreline fixtures are intentionally the sole source of geometry here: an
    absent file or feature must be surfaced to callers rather than approximated.
    """
    filename = lake_id.replace("lake-", "lake_") + "_shoreline.geojson"
    fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / filename

    try:
        with fixture_path.open(encoding="utf-8") as fixture_file:
            payload = json.load(fixture_file)
    except FileNotFoundError as exc:
        raise ShorelineNotFoundError(f"No shoreline fixture for {lake_id!r}") from exc

    for feature in payload.get("features", []):
        if feature.get("properties", {}).get("lake_id") == lake_id:
            geometry = shape(feature["geometry"])
            if isinstance(geometry, Polygon):
                return geometry

    raise ShorelineNotFoundError(f"No shoreline polygon for {lake_id!r}")
