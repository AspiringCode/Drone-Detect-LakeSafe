from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import transform, unary_union

from app.coordination.assignment import haversine_m
from app.models import LatLon
from app.models import RiskPointProvenance
from app.risk_zones.connectors.base import NormalizedRiskPoint
from app.risk_zones.plan_builder import RiskDataUnavailable, _assignable_proxy_seed
from app.lakes import catalog
from app.lakes.catalog import load_reviewed_lake
from app.main import build_lake_runtime, lake_runtimes
from app.risk_zones.shoreline import load_lake_polygon


EXPECTED_LAKES = {
    "lake-sammamish": ("Lake Sammamish", ((47.55684, -122.07032), (47.64865, -122.08846))),
    "lake-pine": ("Pine Lake", ((47.58737, -122.03977),)),
    "lake-beaver": ("Beaver Lake", ((47.58738, -122.00242),)),
}


@pytest.mark.parametrize("lake_id", EXPECTED_LAKES)
def test_reviewed_catalog_loads_immutable_typed_entries(lake_id: str) -> None:
    entry = load_reviewed_lake(lake_id)

    assert entry.lake_id == lake_id
    assert entry.name == EXPECTED_LAKES[lake_id][0]
    assert tuple((point.latitude, point.longitude) for point in entry.official_priority_coordinates) == EXPECTED_LAKES[lake_id][1]
    assert entry.locators == tuple(point.locator for point in entry.official_priority_coordinates)
    with pytest.raises(FrozenInstanceError):
        entry.name = "Changed"  # type: ignore[misc]


def test_reviewed_catalog_unknown_lake_fails_closed() -> None:
    with pytest.raises(ValueError, match="reviewed lake"):
        load_reviewed_lake("lake-unknown")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(schema_version=2),
        lambda payload: payload["lakes"].pop(),
        lambda payload: payload["lakes"][0]["centroid"].update(latitude="47.6"),
    ],
)
def test_reviewed_catalog_rejects_wrong_schema_ids_and_nonnumeric_coordinates(
    monkeypatch: pytest.MonkeyPatch, mutate
) -> None:
    payload = json.loads(catalog.CATALOG_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: json.dumps(payload))

    with pytest.raises(ValueError, match="reviewed lake catalog"):
        load_reviewed_lake("lake-sammamish")


def test_all_three_reviewed_runtimes_are_registered_with_exact_names() -> None:
    assert set(lake_runtimes) == set(EXPECTED_LAKES)
    assert {lake_id: runtime.name for lake_id, runtime in lake_runtimes.items()} == {
        lake_id: expected[0] for lake_id, expected in EXPECTED_LAKES.items()
    }


def test_all_three_runtimes_have_distinct_valid_risk_map_bounds() -> None:
    bounds = {}
    for lake_id in EXPECTED_LAKES:
        runtime = build_lake_runtime(lake_id)
        polygons = [Polygon([(point.lon, point.lat) for point in zone.polygon]) for zone in runtime.zones]
        assert polygons and all(polygon.is_valid and not polygon.is_empty for polygon in polygons)
        bounds[lake_id] = tuple(round(value, 6) for value in unary_union(polygons).bounds)

    assert len(set(bounds.values())) == len(EXPECTED_LAKES)


@pytest.mark.parametrize("lake_id", EXPECTED_LAKES)
def test_runtime_cells_preserve_the_complete_official_shoreline_topology(lake_id: str) -> None:
    runtime = build_lake_runtime(lake_id)
    shoreline = load_lake_polygon(lake_id)
    cells = [
        Polygon(
            [(point.lon, point.lat) for point in zone.polygon],
            [[(point.lon, point.lat) for point in ring] for ring in zone.holes],
        )
        for zone in runtime.zones
    ]

    assert unary_union(cells).symmetric_difference(shoreline).area == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize("lake_id", EXPECTED_LAKES)
def test_runtime_proxy_priority_cells_represent_exact_catalog_seeds(lake_id: str) -> None:
    runtime = build_lake_runtime(lake_id)
    shoreline = load_lake_polygon(lake_id)
    priority_zones = [zone for zone in runtime.zones if zone.components.get("access_environment_proxy", 0) > 0]

    assert len(priority_zones) == len(EXPECTED_LAKES[lake_id][1])
    assert all(zone.is_proxy and zone.risk_score > 0 for zone in priority_zones)
    provenance_by_source = {
        (item.source_latitude, item.source_longitude): (zone, item)
        for zone in priority_zones
        for item in zone.provenance
    }
    assert set(provenance_by_source) == set(EXPECTED_LAKES[lake_id][1])
    for source_coordinate, (zone, provenance) in provenance_by_source.items():
        source = LatLon(*source_coordinate)
        assert provenance.connector_key == "king_county_swim_beach_proxy"
        assert provenance.source_row_id == f"catalog:{provenance.locator}"
        assert provenance.observed_at.isoformat() == "2026-08-18T00:00:00+00:00"
        assert zone.seed == LatLon(provenance.derived_seed_latitude, provenance.derived_seed_longitude)
        assert shoreline.contains(Point(zone.seed.lon, zone.seed.lat))
        assert haversine_m(source, zone.seed) <= 100

        if shoreline.contains(Point(source.lon, source.lat)):
            assert zone.seed.lat == pytest.approx(source.lat)
            assert zone.seed.lon == pytest.approx(source.lon)
            assert provenance.adjustment_distance_m == pytest.approx(0)
            assert provenance.adjustment_reason is None
        else:
            metric = Transformer.from_crs(4326, 32610, always_xy=True)
            source_metric = Point(*metric.transform(source.lon, source.lat))
            seed_metric = Point(*metric.transform(zone.seed.lon, zone.seed.lat))
            boundary_metric = Polygon([
                metric.transform(longitude, latitude)
                for longitude, latitude in shoreline.exterior.coords
            ])
            nearest_boundary = boundary_metric.boundary.interpolate(
                boundary_metric.boundary.project(source_metric)
            )
            assert nearest_boundary.distance(seed_metric) == pytest.approx(5, abs=0.15)
            assert provenance.adjustment_distance_m == pytest.approx(source_metric.distance(seed_metric), abs=0.15)
            assert provenance.adjustment_reason == "projected_inside_official_shoreline"


@pytest.mark.parametrize("lake_id", EXPECTED_LAKES)
def test_runtime_has_five_distinct_interior_demo_drone_positions(lake_id: str) -> None:
    runtime = build_lake_runtime(lake_id)
    shoreline = load_lake_polygon(lake_id)
    positions = {(drone.pos.lat, drone.pos.lon) for drone in runtime.engine.drones}

    assert len(runtime.engine.drones) == 5
    assert len(positions) == 5
    assert all(shoreline.contains(Point(drone.pos.lon, drone.pos.lat)) for drone in runtime.engine.drones)
    assert runtime.shore_station == load_reviewed_lake(lake_id).shore_station.as_lat_lon()


def _metric_square_and_proxy(outside_distance_m: float) -> tuple[Polygon, NormalizedRiskPoint]:
    to_geo = Transformer.from_crs(32610, 4326, always_xy=True)
    shoreline_metric = Polygon([(570000, 5270000), (571000, 5270000), (571000, 5271000), (570000, 5271000)])
    shoreline = transform(to_geo.transform, shoreline_metric)
    source = transform(to_geo.transform, Point(570000 - outside_distance_m, 5270500))
    observed_at = __import__("datetime").datetime(2026, 8, 18, tzinfo=__import__("datetime").timezone.utc)
    provenance = RiskPointProvenance(
        "king_county_swim_beach_proxy", "catalog:TEST", "TEST", observed_at,
        source.y, source.x,
    )
    return shoreline, NormalizedRiskPoint(
        "catalog:TEST", source.y, source.x, observed_at, 1.0, {},
        "access_environment_proxy", True, provenance,
    )


def test_catalog_projection_enforces_final_source_to_seed_tolerance() -> None:
    accepted_shoreline, accepted = _metric_square_and_proxy(94)
    seed, provenance = _assignable_proxy_seed(accepted, accepted_shoreline)
    assert provenance.adjustment_distance_m == pytest.approx(99, abs=0.2)
    assert accepted_shoreline.contains(Point(seed.lon, seed.lat))

    rejected_shoreline, rejected = _metric_square_and_proxy(96)
    with pytest.raises(RiskDataUnavailable, match="outside_reviewed_tolerance"):
        _assignable_proxy_seed(rejected, rejected_shoreline)


def test_catalog_projection_explicitly_rejects_sources_beyond_100_metres() -> None:
    shoreline, point = _metric_square_and_proxy(101)
    with pytest.raises(RiskDataUnavailable, match="outside_reviewed_tolerance"):
        _assignable_proxy_seed(point, shoreline)
