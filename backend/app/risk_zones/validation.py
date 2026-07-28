"""Geometry and patrol-safety validation for immutable zone-plan candidates."""

from __future__ import annotations

from dataclasses import dataclass
import math

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from app.models import LatLon, ZonePlanCell
from app.risk_zones.tessellation import project


class PlanValidationError(ValueError):
    """A candidate cannot safely replace a lake's active plan."""


@dataclass(frozen=True)
class PlanValidation:
    valid: bool
    failures: tuple[str, ...] = ()


def _projected_polygon(points: tuple[LatLon, ...], mean_lat: float) -> Polygon:
    return Polygon([project(point, mean_lat) for point in points])


def validate_plan(
    cells: tuple[ZonePlanCell, ...], shoreline: Polygon, tolerance: float = 1e-9
) -> PlanValidation:
    """Confirm candidate cells exactly and safely partition the supplied shoreline."""
    if not cells:
        return PlanValidation(False, ("candidate_has_no_cells",))
    if not shoreline.is_valid or shoreline.is_empty:
        return PlanValidation(False, ("invalid_shoreline",))
    mean_lat = shoreline.centroid.y
    boundary = Polygon([(x * math.cos(math.radians(mean_lat)), y) for x, y in shoreline.exterior.coords])
    failures: list[str] = []
    polygons: list[Polygon] = []
    for cell in cells:
        if len(cell.polygon) < 4 or cell.polygon[0] != cell.polygon[-1]:
            failures.append(f"{cell.cell_id}:open_ring")
            continue
        polygon = _projected_polygon(cell.polygon, mean_lat)
        seed = Point(project(cell.seed, mean_lat))
        center = Point(project(cell.centroid, mean_lat))
        if not polygon.is_valid or polygon.is_empty:
            failures.append(f"{cell.cell_id}:invalid_geometry")
        elif not polygon.buffer(tolerance).contains(seed):
            failures.append(f"{cell.cell_id}:seed_not_assignable")
        elif not polygon.buffer(tolerance).contains(center):
            failures.append(f"{cell.cell_id}:center_not_assignable")
        elif not boundary.buffer(tolerance).contains(polygon):
            failures.append(f"{cell.cell_id}:outside_shoreline")
        elif cell.radius_m <= 0:
            failures.append(f"{cell.cell_id}:invalid_patrol_radius")
        polygons.append(polygon)
    if polygons:
        union = unary_union(polygons)
        if boundary.symmetric_difference(union).area > tolerance:
            failures.append("shoreline_gap_or_overrun")
        for index, polygon in enumerate(polygons):
            for other in polygons[index + 1:]:
                if polygon.intersection(other).area > tolerance:
                    failures.append("overlapping_cells")
                    break
    return PlanValidation(not failures, tuple(failures))


def require_valid_plan(cells: tuple[ZonePlanCell, ...], shoreline: Polygon) -> None:
    validation = validate_plan(cells, shoreline)
    if not validation.valid:
        raise PlanValidationError(", ".join(validation.failures))
