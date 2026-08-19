"""Build immutable candidate plans from reviewed snapshots, never live fixtures."""

from __future__ import annotations

import math
from uuid import uuid4

from shapely.geometry import Point, Polygon
from shapely.ops import transform

from app.models import LatLon, RiskPointProvenance, ZonePlanCandidate, ZonePlanCell
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


def _incident_points(snapshot, shoreline: Polygon) -> list[WeightedPoint]:
    return [
        WeightedPoint(point.latitude, point.longitude, point.weight, "incidents")
        for point in snapshot.points
        if point.category == "incidents" and not point.is_proxy
        and shoreline.buffer(1e-12).contains(Point(point.longitude, point.latitude))
    ]


def _proxy_seeds(
    snapshot, shoreline: Polygon
) -> list[tuple[LatLon, tuple[RiskPointProvenance, ...]]]:
    by_seed: dict[LatLon, list[RiskPointProvenance]] = {}
    for point in snapshot.points:
        if (
            point.category != "access_environment_proxy" or not point.is_proxy
            or not shoreline.buffer(1e-12).contains(Point(point.longitude, point.latitude))
        ):
            continue
        seed = LatLon(point.latitude, point.longitude)
        if point.provenance is not None and point.provenance not in by_seed.setdefault(seed, []):
            by_seed[seed].append(point.provenance)
        else:
            by_seed.setdefault(seed, [])
    return [(seed, tuple(by_seed[seed])) for seed in sorted(by_seed, key=lambda item: (item.lat, item.lon))]


def _cell(
    cell_id: str, kind: str, seed: LatLon, polygon: Polygon, mean_lat: float,
    risk_score: float, is_proxy: bool, provenance: tuple[RiskPointProvenance, ...] = (),
) -> ZonePlanCell:
    center, radius_m = patrol_center_and_radius(polygon, mean_lat)
    return ZonePlanCell(
        cell_id=cell_id, kind=kind, seed=seed, centroid=center,
        polygon=tuple(unproject((x, y), mean_lat) for x, y in polygon.exterior.coords),
        radius_m=radius_m, risk_score=risk_score, is_proxy=is_proxy, provenance=provenance,
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
    selection = select_hotspots(_incident_points(snapshot, shoreline), (miny, minx, maxy, maxx))
    proxy_seeds = _proxy_seeds(snapshot, shoreline)
    priority_by_seed: dict[LatLon, tuple[float, bool, tuple[RiskPointProvenance, ...]]] = {
        cluster.centroid: (cluster.weight, False, ()) for cluster in selection.hotspots
    }
    for seed, provenance in proxy_seeds:
        weight, is_proxy, existing_provenance = priority_by_seed.get(seed, (1.0, True, ()))
        priority_by_seed[seed] = (
            weight,
            is_proxy,
            tuple(dict.fromkeys((*existing_provenance, *provenance))),
        )
    priority_seeds = list(priority_by_seed)
    unavailable = not priority_seeds
    if unavailable:
        seed = unproject((projected.representative_point().x, projected.representative_point().y), mean_lat)
        cells = (_cell("fallback-0", "fallback", seed, projected, mean_lat, 0.0, True),)
    else:
        seeds = list(priority_seeds)
        kinds = ["hotspot"] * len(seeds)
        coverage_capacity = max(0, patrol_capacity - reserve)
        while len(seeds) < len(priority_seeds) + coverage_capacity:
            candidate, _ = _farthest_coverage_candidate(seeds, projected, mean_lat)
            if any(candidate == existing for existing in seeds):
                break
            seeds.append(candidate)
            kinds.append("coverage")
        max_weight = max(weight for weight, _, _ in priority_by_seed.values())
        cells = tuple(
            _cell(
                f"cell-{index}", kind, seed, polygon, mean_lat,
                round(priority_by_seed[seed][0] / max_weight, 6) if kind == "hotspot" else 0.0,
                priority_by_seed[seed][1] if kind == "hotspot" else True,
                priority_by_seed[seed][2] if kind == "hotspot" else (),
            )
            for index, ((seed, polygon), kind) in enumerate(zip(voronoi_cells(seeds, projected, mean_lat), kinds, strict=True))
        )
    require_valid_plan(cells, shoreline)
    return ZonePlanCandidate(
        plan_id=str(uuid4()), lake_id=snapshot.lake_id, station_id=snapshot.station_id,
        snapshot_id=getattr(snapshot, "snapshot_id", None),
        prior_plan_id=prior_plan_id, activity_data_unavailable=unavailable, cells=cells,
    )
