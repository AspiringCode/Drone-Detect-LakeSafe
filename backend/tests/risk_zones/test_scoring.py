import pytest

from app.risk_zones.connectors import ReviewedConnectorUnavailable
from app.risk_zones.scoring import compute_risk_zones


def test_legacy_scoring_requires_explicit_demo_fixture() -> None:
    with pytest.raises(ReviewedConnectorUnavailable, match="reviewed snapshot/plan pipeline"):
        compute_risk_zones(grid_n=5, use_fixture=False)


def test_scores_normalized_and_proxy_flagged():
    zones = compute_risk_zones(grid_n=5, use_fixture=True)
    assert len(zones) == 25
    assert all(0.0 <= z.risk_score <= 1.0 for z in zones)
    assert any(z.is_proxy for z in zones)
    assert max(z.risk_score for z in zones) == 1.0
    assert min(z.risk_score for z in zones) == 0.0


def test_dense_incident_cell_not_proxy():
    zones = compute_risk_zones(grid_n=5, use_fixture=True)
    hot = max(zones, key=lambda z: z.components["incidents"])
    assert hot.components["incidents"] > 0.0
    assert hot.is_proxy is False


def test_zero_incident_cell_with_proxy_data_is_proxy():
    zones = compute_risk_zones(grid_n=5, use_fixture=True)
    proxy = next(
        z
        for z in zones
        if z.components["incidents"] == 0.0
        and (z.components["depth"] > 0.0 or z.components["crowding"] > 0.0)
    )
    assert proxy.is_proxy is True
