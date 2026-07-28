from __future__ import annotations

import random

from app.coordination.assignment import haversine_m
from app.models import LatLon
from app.risk_zones.cluster_strategy import ClusterZone, WeightedPoint

MIN_RADIUS_M = 15.0
MAX_RADIUS_M = 150.0
RADIUS_PERCENTILE = 80
DEFAULT_SEED = 42
MAX_ITERATIONS = 50
CONVERGENCE_THRESHOLD_M = 1.0
MIN_CLUSTER_WEIGHT = 1.0
CATEGORIES = ("incidents", "depth", "crowding")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    frac = k - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


class WeightedKMeansStrategy:
    """Default ZoneClusterStrategy: weighted k-means++ init + weighted Lloyd's
    algorithm iteration.

    Research pointers if replacing/refining this: "weighted k-means++
    initialization" and "weighted Lloyd's algorithm" are the standard names
    for the two pieces used here. Centroids are plain lat/lon weighted
    averages (no geodesic centroid correction) - consistent with the
    existing grid code's own flat-earth centroid approximation
    (app/risk_zones/scoring.py's `(south + north) / 2` cell centroids), which
    is accurate enough at this lake's ~5.5km x 2.9km scale.
    """

    def __init__(self, k: int | None = None, seed: int = DEFAULT_SEED) -> None:
        self.k = k
        self.seed = seed

    def refine(
        self, points: list[WeightedPoint], bbox: tuple[float, float, float, float]
    ) -> list[ClusterZone]:
        # Canonical ordering keeps seeded k-means reproducible even when a
        # connector returns the same immutable records in a different order.
        points = sorted(points, key=lambda point: (point.lat, point.lon, point.category, point.weight))
        if not points:
            return []
        k = self.k or 1
        k = min(k, len(points))
        rng = random.Random(self.seed)

        centroids = self._init_centroids(points, k, rng)
        members: list[list[WeightedPoint]] = [[] for _ in centroids]
        for _ in range(MAX_ITERATIONS):
            members = [[] for _ in centroids]
            for point in points:
                idx = min(
                    range(len(centroids)),
                    key=lambda i: haversine_m(
                        centroids[i], LatLon(point.lat, point.lon)
                    ),
                )
                members[idx].append(point)

            new_centroids: list[LatLon] = []
            max_move = 0.0
            for centroid, group in zip(centroids, members):
                if not group:
                    new_centroids.append(centroid)
                    continue
                wsum = sum(p.weight for p in group)
                lat = sum(p.lat * p.weight for p in group) / wsum
                lon = sum(p.lon * p.weight for p in group) / wsum
                new_centroid = LatLon(lat, lon)
                max_move = max(max_move, haversine_m(centroid, new_centroid))
                new_centroids.append(new_centroid)
            centroids = new_centroids
            if max_move < CONVERGENCE_THRESHOLD_M:
                break

        zones: list[ClusterZone] = []
        for centroid, group in zip(centroids, members):
            if not group:
                continue
            total_weight = sum(p.weight for p in group)
            if total_weight < MIN_CLUSTER_WEIGHT:
                continue
            distances = [haversine_m(centroid, LatLon(p.lat, p.lon)) for p in group]
            radius = _percentile(distances, RADIUS_PERCENTILE)
            radius = max(MIN_RADIUS_M, min(MAX_RADIUS_M, radius))
            category_weights = {cat: 0.0 for cat in CATEGORIES}
            for p in group:
                category_weights[p.category] = category_weights.get(p.category, 0.0) + p.weight
            zones.append(
                ClusterZone(
                    centroid=centroid,
                    radius_m=radius,
                    weight=total_weight,
                    member_count=len(group),
                    category_weights=category_weights,
                )
            )
        return zones

    def _init_centroids(
        self, points: list[WeightedPoint], k: int, rng: random.Random
    ) -> list[LatLon]:
        """Weighted k-means++: each subsequent centroid is chosen with
        probability proportional to (distance-to-nearest-existing-centroid^2
        * point weight), so high-weight far-away points are preferentially
        chosen as seeds without ignoring point weight entirely."""
        first_idx = rng.choices(
            range(len(points)), weights=[p.weight for p in points], k=1
        )[0]
        centroids = [LatLon(points[first_idx].lat, points[first_idx].lon)]
        while len(centroids) < k:
            scores = [
                min(haversine_m(c, LatLon(p.lat, p.lon)) ** 2 for c in centroids)
                * p.weight
                for p in points
            ]
            total = sum(scores)
            if total <= 0:
                next_idx = rng.randrange(len(points))
            else:
                r = rng.uniform(0, total)
                acc = 0.0
                next_idx = len(points) - 1
                for i, score in enumerate(scores):
                    acc += score
                    if acc >= r:
                        next_idx = i
                        break
            centroids.append(LatLon(points[next_idx].lat, points[next_idx].lon))
        return centroids
