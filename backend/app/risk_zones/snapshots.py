"""Immutable, canonical inputs for data-driven risk-zone planning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from typing import Sequence

from .connectors.base import ConnectorFetch, NormalizedRiskPoint
from app.models import RiskPointProvenance


@dataclass(frozen=True, slots=True)
class SnapshotSource:
    connector_key: str
    schema_version: str
    attribution: str


@dataclass(frozen=True, slots=True)
class RiskSnapshotInput:
    lake_id: str
    station_id: str
    status: str
    failure_reason: str | None
    boundary: str
    since: datetime
    captured_at: datetime
    sources: tuple[SnapshotSource, ...]
    connector_versions: tuple[tuple[str, str], ...]
    points: tuple[NormalizedRiskPoint, ...]
    canonical_json: str
    sha256: str


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot times must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_boundary(boundary: object) -> str:
    value = getattr(boundary, "wkt", boundary)
    if not isinstance(value, str):
        raise ValueError("boundary must be WKT text or expose .wkt")
    return value


def _point_payload(point: NormalizedRiskPoint) -> dict[str, object]:
    payload = {
        "source_row_id": point.source_row_id,
        "latitude": point.latitude,
        "longitude": point.longitude,
        "occurred_at": _utc(point.occurred_at).isoformat().replace("+00:00", "Z"),
        "weight": point.weight,
        "category": point.category,
        "is_proxy": point.is_proxy,
        "source_payload": point.source_payload,
    }
    if point.provenance is not None:
        provenance_payload = {
            "connector_key": point.provenance.connector_key,
            "source_row_id": point.provenance.source_row_id,
            "locator": point.provenance.locator,
            "observed_at": _utc(point.provenance.observed_at).isoformat().replace("+00:00", "Z"),
        }
        for field in (
            "source_latitude", "source_longitude", "derived_seed_latitude",
            "derived_seed_longitude", "adjustment_distance_m", "adjustment_reason",
        ):
            value = getattr(point.provenance, field)
            if value is not None:
                provenance_payload[field] = value
        payload["provenance"] = provenance_payload
    return payload


def _with_connector_provenance(
    point: NormalizedRiskPoint, connector_key: str
) -> NormalizedRiskPoint:
    provenance = point.provenance
    return replace(
        point,
        provenance=replace(
            provenance, connector_key=connector_key, source_row_id=point.source_row_id
        ) if provenance is not None else RiskPointProvenance(
            connector_key, point.source_row_id, None, point.occurred_at,
        ),
    )


def _empty_snapshot(
    lake_id: str,
    station_id: str,
    boundary: str,
    since: datetime,
    now: datetime,
    reason: str,
) -> RiskSnapshotInput:
    payload = {
        "lake_id": lake_id,
        "station_id": station_id,
        "boundary": boundary,
        "since": since.isoformat().replace("+00:00", "Z"),
        "captured_at": now.isoformat().replace("+00:00", "Z"),
        "status": "quarantined",
        "failure_reason": reason,
        "sources": [],
        "points": [],
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return RiskSnapshotInput(
        lake_id, station_id, "quarantined", reason, boundary, since, now, (), (), (),
        canonical_json, hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    )


def build_fallback_snapshot(
    lake_id: str, station_id: str, boundary: object, since: datetime, now: datetime
) -> RiskSnapshotInput:
    """Create the explicit no-activity input allowed for fallback-coverage lakes.

    This is distinct from a missing reviewed connector: callers may use it only
    when the lake itself was persisted with ``fallback_coverage`` status.
    """
    boundary_wkt = _canonical_boundary(boundary)
    utc_since, captured_at = _utc(since), _utc(now)
    payload = {
        "lake_id": lake_id, "station_id": station_id, "boundary": boundary_wkt,
        "since": utc_since.isoformat().replace("+00:00", "Z"),
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "status": "ready", "failure_reason": None, "sources": [], "points": [],
        "fallback_coverage": True,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return RiskSnapshotInput(
        lake_id, station_id, "ready", None, boundary_wkt, utc_since, captured_at, (), (), (),
        canonical_json, hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    )


def build_snapshot(
    lake_id: str,
    station_id: str,
    connectors: Sequence[ConnectorFetch | BaseException],
    boundary: object,
    since: datetime,
    now: datetime,
) -> RiskSnapshotInput:
    """Canonicalize reviewed connector fetches without ever inventing data.

    Connector failures are represented as quarantined snapshots so a caller can
    persist the failure while preserving the lake's prior active plan.
    """
    boundary_wkt = _canonical_boundary(boundary)
    utc_since, captured_at = _utc(since), _utc(now)
    if not connectors:
        return _empty_snapshot(lake_id, station_id, boundary_wkt, utc_since, captured_at, "no_reviewed_connector")
    for connector in connectors:
        if isinstance(connector, BaseException):
            reason = "connector_schema_failure" if isinstance(connector, ValueError) else "connector_fetch_failure"
            return _empty_snapshot(lake_id, station_id, boundary_wkt, utc_since, captured_at, reason)
        if not isinstance(connector, ConnectorFetch):
            return _empty_snapshot(lake_id, station_id, boundary_wkt, utc_since, captured_at, "connector_schema_failure")

    try:
        fetches = sorted(connectors, key=lambda item: (item.connector_key, item.connector_schema_version, item.attribution))
        sources = tuple(SnapshotSource(item.connector_key, item.connector_schema_version, item.attribution) for item in fetches)
        point_pairs = [
            (point, _point_payload(point))
            for item in fetches
            for row in item.rows
            for point in (_with_connector_provenance(row, item.connector_key),)
        ]
        point_pairs.sort(key=lambda pair: json.dumps(
            pair[1], sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ))
        points = tuple(point for point, _payload in point_pairs)
        point_payloads = [point_payload for _point, point_payload in point_pairs]
    except (AttributeError, TypeError, ValueError, OverflowError):
        return _empty_snapshot(lake_id, station_id, boundary_wkt, utc_since, captured_at, "connector_schema_failure")
    payload = {
        "lake_id": lake_id,
        "station_id": station_id,
        "boundary": boundary_wkt,
        "since": utc_since.isoformat().replace("+00:00", "Z"),
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "status": "ready",
        "failure_reason": None,
        "sources": [
            {"connector_key": source.connector_key, "schema_version": source.schema_version, "attribution": source.attribution}
            for source in sources
        ],
        "points": point_payloads,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return RiskSnapshotInput(
        lake_id=lake_id,
        station_id=station_id,
        status="ready",
        failure_reason=None,
        boundary=boundary_wkt,
        since=utc_since,
        captured_at=captured_at,
        sources=sources,
        connector_versions=tuple((source.connector_key, source.schema_version) for source in sources),
        points=points,
        canonical_json=canonical_json,
        sha256=hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    )
