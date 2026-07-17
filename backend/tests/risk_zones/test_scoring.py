from app.risk_zones.tessellation import compute_tessellated_zones


def test_tessellated_scores_normalized_and_coverage_cells_proxy_flagged():
    zones = compute_tessellated_zones("lake-sammamish", drone_count=5, use_fixture=True)
    assert zones
    assert all(0.0 <= z.risk_score <= 1.0 for z in zones)
    assert any(z.is_proxy for z in zones)
    assert max(z.risk_score for z in zones) == 1.0
    assert min(z.risk_score for z in zones) == 0.0


def test_dense_incident_cell_not_proxy():
    zones = compute_tessellated_zones("lake-sammamish", drone_count=5, use_fixture=True)
    hotspot_zones = [z for z in zones if "incidents" in z.components]
    hot = max(hotspot_zones, key=lambda z: z.components["incidents"])
    assert hot.components["incidents"] > 0.0
    assert hot.is_proxy is False


def test_coverage_cell_is_proxy():
    zones = compute_tessellated_zones("lake-sammamish", drone_count=5, use_fixture=True)
    proxy = next(z for z in zones if not z.components)
    assert proxy.is_proxy is True
