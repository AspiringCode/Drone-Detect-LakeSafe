"""Build immutable candidate plans from reviewed snapshots, never live fixtures."""

from __future__ import annotations

import math
from uuid import uuid4

from shapely.geometry import Point, Polygon
from shapely.ops import transform

from app.models import LatLon, ZonePlanCandidate, ZonePlanCell
from app.risk_zones.adaptive_clusters import select_hotspots
from app.risk_zones.cluster_strategy import WeightedPoint
from app.risk_zones.tessellation import (
    _farthest_coverage_candidate,
    patrol_center_and_radius,
    unproject,
    voronoi_cells,
)
from app.risk_zones.validation import require_valid_plan


class RiskDataUnavailable(RuntimeError):
    """A reviewed snapshot cannot safely produce a candidate."""


def _project_boundary(shoreline: Polygon, mean_lat: float) -> Polygon:
    return transform(lambda x, y, z=None: (x * math.cos(math.radians(mean_lat)), y), shoreline)


def _points(snapshot, shoreline: Polygon) -> list[WeightedPoint]:
    return [
        WeightedPoint(point.latitude, point.longitude, point.weight, "incidents")
        for point in snapshot.points
        if shoreline.buffer(1e-12).contains(Point(point.longitude, point.latitude))
    ]


def _cell(cell_id: str, kind: str, seed: LatLon, polygon: Polygon, mean_lat: float, risk_score: float) -> ZonePlanCell:
    center, radius_m = patrol_center_and_radius(polygon, mean_lat)
    return ZonePlanCell(
        cell_id=cell_id, kind=kind, seed=seed, centroid=center,
        polygon=tuple(unproject((x, y), mean_lat) for x, y in polygon.exterior.coords),
        radius_m=radius_m, risk_score=risk_score, is_proxy=kind != "hotspot",
    )


def build_candidate(snapshot, shoreline: Polygon, patrol_capacity: int, reserve: int, prior_plan_id: str | None) -> ZonePlanCandidate:
    """Create a fully validated candidate without changing the active-plan pointer.

    Hotspot selection is driven entirely by the snapshot.  Fleet capacity can
    add coverage cells after those supported hotspots, but never removes one.
    """
    if snapshot.status != "ready":
        raise RiskDataUnavailable(snapshot.failure_reason or "risk_snapshot_unavailable")
    if patrol_capacity < 0 or reserve < 0:
        raise ValueError("patrol capacity and reserve must be non-negative")
    if not shoreline.is_valid or shoreline.is_empty:
        raise RiskDataUnavailable("invalid_shoreline")
    mean_lat = shoreline.centroid.y
    projected = _project_boundary(shoreline, mean_lat)
    minx, miny, maxx, maxy = shoreline.bounds
    selection = select_hotspots(_points(snapshot, shoreline), (miny, minx, maxy, maxx))
    hotspot_seeds = [cluster.centroid for cluster in selection.hotspots]
    unavailable = not hotspot_seeds
    if unavailable:
        seed = unproject((projected.representative_point().x, projected.representative_point().y), mean_lat)
        cells = (_cell("fallback-0", "fallback", seed, projected, mean_lat, 0.0),)
    else:
        seeds = list(hotspot_seeds)
        kinds = ["hotspot"] * len(seeds)
        coverage_capacity = max(0, patrol_capacity - reserve)
        while len(seeds) < len(hotspot_seeds) + coverage_capacity:
            candidate, _ = _farthest_coverage_candidate(seeds, projected, mean_lat)
            if any(candidate == existing for existing in seeds):
                break
            seeds.append(candidate)
            kinds.append("coverage")
        max_weight = max(cluster.weight for cluster in selection.hotspots)
        weight_by_seed = {cluster.centroid: cluster.weight for cluster in selection.hotspots}
        cells = tuple(
            _cell(
                f"cell-{index}", kind, seed, polygon, mean_lat,
                round(weight_by_seed.get(seed, 0.0) / max_weight, 6) if kind == "hotspot" else 0.0,
            )
            for index, ((seed, polygon), kind) in enumerate(zip(voronoi_cells(seeds, projected, mean_lat), kinds, strict=True))
        )
    require_valid_plan(cells, shoreline)
    return ZonePlanCandidate(
        plan_id=str(uuid4()), lake_id=snapshot.lake_id, snapshot_id=getattr(snapshot, "snapshot_id", None),
        prior_plan_id=prior_plan_id, activity_data_unavailable=unavailable, cells=cells,
    )
