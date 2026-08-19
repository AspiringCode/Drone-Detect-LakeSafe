"""Demo-only loader for committed, synthetic risk-zone fixture rows.

This module performs no network requests. Production planning uses reviewed,
immutable snapshots through the connector and plan pipeline instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal


DemoRowKind = Literal["incidents", "depth_contours", "access_points"]
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "king_county_sample.json"
_REQUIRED_FIELDS = {
    "incidents": frozenset({"id", "lat", "lon", "type"}),
    "depth_contours": frozenset({"id", "lat", "lon", "severity"}),
    "access_points": frozenset({"id", "lat", "lon", "name", "crowding"}),
}


def _valid_demo_row(kind: DemoRowKind, row: dict[str, object]) -> bool:
    number = (int, float)
    common = (
        isinstance(row["id"], str)
        and isinstance(row["lat"], number)
        and not isinstance(row["lat"], bool)
        and isinstance(row["lon"], number)
        and not isinstance(row["lon"], bool)
    )
    if kind == "incidents":
        return common and isinstance(row["type"], str)
    if kind == "depth_contours":
        return (
            common
            and isinstance(row["severity"], number)
            and not isinstance(row["severity"], bool)
        )
    return (
        common
        and isinstance(row["name"], str)
        and isinstance(row["crowding"], number)
        and not isinstance(row["crowding"], bool)
    )


def load_demo_rows(kind: DemoRowKind) -> list[dict[str, object]]:
    """Validate and copy one synthetic row group for an explicit local demo."""
    if kind not in _REQUIRED_FIELDS:
        raise ValueError(f"unknown demo fixture kind: {kind}")
    try:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        rows = payload[kind]
        required = _REQUIRED_FIELDS[kind]
        if not isinstance(rows, list) or not rows:
            raise TypeError
        if any(not isinstance(row, dict) or not required <= row.keys() for row in rows):
            raise TypeError
        if any(not _valid_demo_row(kind, row) for row in rows):
            raise TypeError
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("invalid demo fixture schema") from error
    return [dict(row) for row in rows]
