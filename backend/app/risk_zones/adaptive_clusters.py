"""Deterministic hotspot model selection independent of fleet capacity."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from app.coordination.assignment import haversine_m
from app.models import LatLon

from .cluster_strategy import ClusterZone, WeightedPoint
from .kmeans_strategy import WeightedKMeansStrategy

SEEDS = (42, 43, 44)
STABILITY_TOLERANCE_M = 25.0


@dataclass(frozen=True, slots=True)
class ClusterSelection:
    k: int
    hotspots: tuple[ClusterZone, ...]
    score: float | None
    stable: bool
    reason: str | None = None


def _canonical(points: Sequence[WeightedPoint]) -> list[WeightedPoint]:
    return sorted(
        (point for point in points if point.weight > 0),
        key=lambda point: (point.lat, point.lon, point.category, point.weight),
    )


def _assign(points: Sequence[WeightedPoint], zones: Sequence[ClusterZone]) -> list[int]:
    return [min(range(len(zones)), key=lambda i: haversine_m(zones[i].centroid, LatLon(point.lat, point.lon))) for point in points]


def _weighted_silhouette(points: Sequence[WeightedPoint], zones: Sequence[ClusterZone]) -> float:
    if len(zones) < 2:
        return 0.0
    assignments = _assign(points, zones)
    total_weight = sum(point.weight for point in points)
    if total_weight <= 0:
        return 0.0
    score = 0.0
    for index, point in enumerate(points):
        own = assignments[index]
        own_members = [candidate for candidate, assigned in zip(points, assignments) if assigned == own and candidate is not point]
        if not own_members:
            continue
        a_weight = sum(candidate.weight for candidate in own_members)
        a = sum(haversine_m(LatLon(point.lat, point.lon), LatLon(candidate.lat, candidate.lon)) * candidate.weight for candidate in own_members) / a_weight
        alternatives = []
        for other in range(len(zones)):
            if other == own:
                continue
            group = [candidate for candidate, assigned in zip(points, assignments) if assigned == other]
            if group:
                weight = sum(candidate.weight for candidate in group)
                alternatives.append(sum(haversine_m(LatLon(point.lat, point.lon), LatLon(candidate.lat, candidate.lon)) * candidate.weight for candidate in group) / weight)
        if alternatives:
            b = min(alternatives)
            score += point.weight * ((b - a) / max(a, b))
    return score / total_weight


def _stable(runs: Sequence[Sequence[ClusterZone]]) -> bool:
    if not runs or any(len(run) != len(runs[0]) for run in runs):
        return False
    for left, right in combinations(runs, 2):
        unmatched = list(right)
        for zone in sorted(left, key=lambda item: (item.centroid.lat, item.centroid.lon)):
            nearest_index, distance = min(
                enumerate(haversine_m(zone.centroid, candidate.centroid) for candidate in unmatched),
                key=lambda item: item[1],
            )
            if distance > STABILITY_TOLERANCE_M:
                return False
            unmatched.pop(nearest_index)
    return True


def select_hotspots(
    points: Sequence[WeightedPoint],
    bbox: tuple[float, float, float, float],
    min_k: int = 1,
    max_k: int = 8,
    min_records: int = 2,
    min_weight: float = 1.0,
) -> ClusterSelection:
    """Choose a stable, supported ``k`` using only observed activity data."""
    if min_k < 1 or max_k < min_k or min_records < 1 or min_weight <= 0:
        raise ValueError("invalid hotspot selection thresholds")
    canonical = _canonical(points)
    if len(canonical) < min_records or sum(point.weight for point in canonical) < min_weight:
        return ClusterSelection(0, (), None, False, "insufficient_support")

    best: ClusterSelection | None = None
    upper = min(max_k, len(canonical) // min_records)
    for k in range(min_k, upper + 1):
        runs = [WeightedKMeansStrategy(k=k, seed=seed).refine(canonical, bbox) for seed in SEEDS]
        if any(len(zones) != k for zones in runs):
            continue
        if any(zone.member_count < min_records or zone.weight < min_weight for zones in runs for zone in zones):
            continue
        if not _stable(runs):
            continue
        score = sum(_weighted_silhouette(canonical, zones) for zones in runs) / len(runs)
        candidate = ClusterSelection(k, tuple(runs[0]), score, True)
        if best is None or score > best.score + 1e-12:
            best = candidate
    return best if best is not None else ClusterSelection(0, (), None, False, "insufficient_support")
