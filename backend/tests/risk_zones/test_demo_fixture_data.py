from __future__ import annotations

from pathlib import Path

import pytest


def test_demo_loader_returns_valid_copied_rows_for_each_supported_kind() -> None:
    from app.risk_zones.demo_fixture_data import load_demo_rows

    required_fields = {
        "incidents": {"id", "lat", "lon", "type"},
        "depth_contours": {"id", "lat", "lon", "severity"},
        "access_points": {"id", "lat", "lon", "name", "crowding"},
    }
    for kind, expected_fields in required_fields.items():
        first = load_demo_rows(kind)  # type: ignore[arg-type]
        assert first
        assert all(expected_fields <= row.keys() for row in first)
        first[0]["id"] = "mutated"
        assert load_demo_rows(kind)[0]["id"] != "mutated"  # type: ignore[arg-type]


def test_demo_loader_rejects_unknown_kind() -> None:
    from app.risk_zones.demo_fixture_data import load_demo_rows

    with pytest.raises(ValueError, match="unknown demo fixture kind"):
        load_demo_rows("unknown")  # type: ignore[arg-type]


def test_demo_loader_rejects_invalid_fixture_schema(monkeypatch) -> None:
    from app.risk_zones import demo_fixture_data

    monkeypatch.setattr(demo_fixture_data, "FIXTURE_PATH", Path(__file__))

    with pytest.raises(ValueError, match="invalid demo fixture schema"):
        demo_fixture_data.load_demo_rows("incidents")


def test_demo_loader_rejects_invalid_kind_specific_values(monkeypatch) -> None:
    from app.risk_zones import demo_fixture_data

    monkeypatch.setattr(
        demo_fixture_data.json,
        "loads",
        lambda _text: {
            "depth_contours": [
                {"id": "d01", "lat": 47.58, "lon": -122.09, "severity": "high"}
            ]
        },
    )

    with pytest.raises(ValueError, match="invalid demo fixture schema"):
        demo_fixture_data.load_demo_rows("depth_contours")
