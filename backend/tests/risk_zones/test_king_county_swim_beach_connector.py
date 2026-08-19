from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.risk_zones.connectors.king_county_swim_beach import (
    KingCountySwimBeachProxyConnector,
)


SINCE = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _observation(locator: str, date: str, time: str | None = "09:30:00") -> dict[str, str]:
    row = {
        "beach": "Lake Sammamish State Park",
        "locator": locator,
        "date": date,
        "watertempc": "20.0",
        "watertempf": "68.0",
        "hightoday": "5.2",
    }
    if time is not None:
        row["time"] = time
    return row


def _site(locator: str, latitude: str = "47.5711", longitude: str = "-122.0452") -> dict[str, str]:
    return {
        "locator": locator,
        "site": "Sammamish beach",
        "latitude": latitude,
        "longitude": longitude,
        "status": "Active",
        "area": "Lake Sammamish",
    }


class Client:
    def __init__(self, observations, sites) -> None:
        self.observations = observations
        self.sites = sites
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, dataset_id: str, **query: object):
        self.calls.append((dataset_id, query))
        return self.observations if dataset_id == "mbzm-4r9y" else self.sites


def test_fetches_reviewed_datasets_and_keeps_newest_requested_proxy_per_locator() -> None:
    client = Client(
        [
            _observation("0615SB", "2026-07-02", "08:00:00"),
            _observation("0615SB", "2026-07-03", "09:30:00"),
            _observation("SAMMLANDINGSB", "2026-07-04", None),
        ],
        [_site("0615SB"), _site("SAMMLANDINGSB", "47.5712", "-122.0453")],
    )

    result = KingCountySwimBeachProxyConnector(("0615SB", "SAMMLANDINGSB")).fetch(
        "POLYGON EMPTY", SINCE, client
    )

    assert [dataset_id for dataset_id, _ in client.calls] == ["mbzm-4r9y", "e9bt-i75a"]
    assert client.calls[0][1] == {
        "select": "beach, locator, date, time, watertempc, watertempf, hightoday",
        "where": "locator IN ('0615SB', 'SAMMLANDINGSB') AND date >= '2026-06-30'",
        "order": "locator asc, date desc, time desc",
        "limit": 500,
    }
    assert client.calls[1][1] == {
        "select": "locator, site, latitude, longitude, status, area",
        "where": "locator IN ('0615SB', 'SAMMLANDINGSB')",
        "order": "locator asc, site asc",
        "limit": 500,
    }
    assert [point.source_row_id for point in result.rows] == [
        "0615SB:2026-07-03T16:30:00+00:00",
        "SAMMLANDINGSB:2026-07-04T07:00:00+00:00",
    ]
    assert result.rows[0].occurred_at == datetime(2026, 7, 3, 16, 30, tzinfo=timezone.utc)
    assert (result.rows[1].latitude, result.rows[1].longitude) == (47.5712, -122.0453)
    assert all(point.weight == 1.0 for point in result.rows)
    assert all(point.category == "access_environment_proxy" and point.is_proxy for point in result.rows)
    assert result.rows[0].source_payload == {
        "observation": _observation("0615SB", "2026-07-03", "09:30:00"),
        "site": _site("0615SB"),
    }
    assert result.attribution == (
        "King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites"
    )


@pytest.mark.parametrize(
    ("observations", "sites"),
    [
        ([{"locator": "0615SB"}], [_site("0615SB")]),
        ([_observation("NOT-A-SITE", "2026-07-02")], [_site("0615SB")]),
        ([_observation("0615SB", "not-a-date")], [_site("0615SB")]),
        ([_observation("0615SB", "2026-07-02junk")], [_site("0615SB")]),
        ([_observation("0615SB", "2026-07-02")], [_site("0615SB", "95", "-122.0452")]),
        ([_observation("0615SB", "2026-07-02")], [_site("0615SB"), _site("0615SB")]),
    ],
)
def test_rejects_schema_drift_and_unreviewed_site_mappings(observations, sites) -> None:
    with pytest.raises(ValueError, match="schema drift"):
        KingCountySwimBeachProxyConnector(("0615SB",)).fetch("POLYGON EMPTY", SINCE, Client(observations, sites))


def test_rejects_observations_older_than_since_and_accepts_an_empty_season() -> None:
    client = Client([_observation("0615SB", "2026-06-30", "08:00:00")], [_site("0615SB")])

    result = KingCountySwimBeachProxyConnector(("0615SB",)).fetch("POLYGON EMPTY", SINCE, client)

    assert result.rows == ()


def test_client_exceptions_propagate_without_a_fixture_fallback() -> None:
    class FailingClient:
        def get(self, *_: object, **__: object):
            raise OSError("network unavailable")

    with pytest.raises(OSError, match="network unavailable"):
        KingCountySwimBeachProxyConnector(("0615SB",)).fetch("POLYGON EMPTY", SINCE, FailingClient())


@pytest.mark.parametrize(
    ("observations_dataset_id", "sites_dataset_id"),
    [("other-observations", "e9bt-i75a"), ("mbzm-4r9y", "other-sites")],
)
def test_constructor_rejects_unreviewed_dataset_ids(observations_dataset_id, sites_dataset_id) -> None:
    with pytest.raises(ValueError, match="schema drift"):
        KingCountySwimBeachProxyConnector(
            ("0615SB",), observations_dataset_id, sites_dataset_id
        )
