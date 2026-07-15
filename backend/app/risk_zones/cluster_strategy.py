from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.models import LatLon

Category = Literal["incidents", "depth", "crowding"]


@dataclass(frozen=True)
class WeightedPoint:
    lat: float
    lon: float
    weight: float
    category: Category


@dataclass(frozen=True)
class ClusterZone:
    centroid: LatLon
    radius_m: float
    weight: float
    member_count: int
    category_weights: dict[str, float]


class ZoneClusterStrategy(Protocol):
    def refine(
        self, points: list[WeightedPoint], bbox: tuple[float, float, float, float]
    ) -> list[ClusterZone]:
        """Return dense clusters found in `points` within `bbox`.

        This is the swap point: any implementation of this method can replace
        the default WeightedKMeansStrategy (app.risk_zones.kmeans_strategy)
        without changes anywhere else in the risk-zone pipeline.
        """
        ...
