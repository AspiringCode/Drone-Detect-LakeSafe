from shapely.geometry import shape

from app.risk_zones.heatmap import zones_to_geojson
from app.risk_zones.scoring import compute_risk_zones


def test_zones_to_geojson_feature_collection_valid_polygons():
    zones = compute_risk_zones(grid_n=2, use_fixture=True)
    geojson = zones_to_geojson(zones)

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == len(zones)

    for feature in geojson["features"]:
        assert "risk_score" in feature["properties"]
        assert "zone_id" in feature["properties"]
        assert "is_proxy" in feature["properties"]
        geom = shape(feature["geometry"])
        assert geom.is_valid
        assert geom.geom_type == "Polygon"
