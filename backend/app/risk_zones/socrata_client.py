from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from sodapy import Socrata
except Exception:  # pragma: no cover - dependency may be absent in lean test envs
    Socrata = None

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "king_county_sample.json"


def _load_fixture(kind: str) -> list[dict[str, Any]]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return list(payload[kind])


def _fetch_live(dataset_id: str, limit: int = 500) -> list[dict[str, Any]]:
    if Socrata is None:
        raise RuntimeError("sodapy is unavailable")
    client = Socrata("data.kingcounty.gov", None, timeout=10)
    return list(client.get(dataset_id, limit=limit))


def fetch_incidents(use_fixture: bool = False) -> list[dict[str, Any]]:
    """Fetch incident rows, falling back to the committed Lake Sammamish fixture.

    Live King County dataset ID/granularity remains a Task 3 assessment point; the
    fixture preserves the offline seam for risk-zone development and tests.
    """
    if use_fixture:
        return _load_fixture("incidents")
    try:
        return _fetch_live("placeholder_incidents")
    except Exception:
        return _load_fixture("incidents")


def fetch_depth_contours(use_fixture: bool = False) -> list[dict[str, Any]]:
    if use_fixture:
        return _load_fixture("depth_contours")
    try:
        return _fetch_live("placeholder_depth_contours")
    except Exception:
        return _load_fixture("depth_contours")


def fetch_access_points(use_fixture: bool = False) -> list[dict[str, Any]]:
    if use_fixture:
        return _load_fixture("access_points")
    try:
        return _fetch_live("placeholder_access_points")
    except Exception:
        return _load_fixture("access_points")
