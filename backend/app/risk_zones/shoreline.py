"""Load committed lake shoreline polygons."""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import MultiPolygon, Point, Polygon, shape


FIXTURE_DIRECTORY = Path(__file__).resolve().parents[2] / "fixtures"


class ShorelineNotFoundError(Exception):
    """Raised when a requested lake has no committed shoreline polygon."""


def load_lake_polygon(lake_id: str) -> Polygon:
    """Return the committed shoreline polygon for ``lake_id``.

    Shoreline fixtures are intentionally the sole source of geometry here: an
    absent file or feature must be surfaced to callers rather than approximated.
    """
    filename = lake_id.replace("lake-", "lake_") + "_shoreline.geojson"
    fixture_path = FIXTURE_DIRECTORY / filename

    try:
        with fixture_path.open(encoding="utf-8") as fixture_file:
            payload = json.load(fixture_file)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ShorelineNotFoundError(f"No shoreline fixture for {lake_id!r}") from exc

    for feature in payload.get("features", []):
        if feature.get("properties", {}).get("lake_id") == lake_id:
            try:
                geometry = shape(feature["geometry"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ShorelineNotFoundError(
                    f"No valid non-empty shoreline polygon for {lake_id!r}"
                ) from exc
            if geometry.is_empty or not geometry.is_valid:
                raise ShorelineNotFoundError(
                    f"No valid non-empty shoreline polygon for {lake_id!r}"
                )
            if isinstance(geometry, Polygon):
                return geometry
            if isinstance(geometry, MultiPolygon):
                centroid = _catalog_centroid(lake_id)
                matches = [polygon for polygon in geometry.geoms if polygon.covers(centroid)]
                if len(matches) != 1:
                    raise ShorelineNotFoundError(
                        f"MultiPolygon for {lake_id!r} must have exactly one component "
                        "containing its catalog centroid"
                    )
                return matches[0]
            raise ShorelineNotFoundError(
                f"No valid non-empty shoreline polygon for {lake_id!r}"
            )

    raise ShorelineNotFoundError(f"No shoreline polygon for {lake_id!r}")


def _catalog_centroid(lake_id: str) -> Point:
    try:
        with (FIXTURE_DIRECTORY / "reviewed_lakes.json").open(encoding="utf-8") as catalog_file:
            lakes = json.load(catalog_file)["lakes"]
        lake = next(item for item in lakes if item["lake_id"] == lake_id)
        centroid = lake["centroid"]
        return Point(float(centroid["longitude"]), float(centroid["latitude"]))
    except (FileNotFoundError, json.JSONDecodeError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise ShorelineNotFoundError(
            f"No catalog centroid for {lake_id!r}"
        ) from exc
