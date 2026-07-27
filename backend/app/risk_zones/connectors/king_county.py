from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import ConnectorFetch, NormalizedRiskPoint, SocrataClient, SocrataConnector


class ReviewedConnectorUnavailable(RuntimeError):
    """No verified publisher mapping exists for a requested connector."""


class KingCountyIncidentConnector(SocrataConnector):
    """The reviewed King County incident-point contract.

    King County's presently documented public offense feed is not a
    point-capable lake-activity feed.  Consequently this class is intentionally
    unseeded: a database-reviewed mapping must provide an exact dataset ID
    before it is allowed to query the publisher.  The normalization contract is
    still explicit, versioned, and fail-closed once such a mapping exists.
    """

    domain = "data.kingcounty.gov"
    dataset_id: str | None
    connector_key = "king_county_incidents"
    schema_version = "1"
    attribution = "King County Open Data"
    required_fields = frozenset(
        {"incident_id", "latitude", "longitude", "occurred_at", "severity"}
    )
    page_size = 500

    def __init__(self, reviewed_dataset_id: str | None = None) -> None:
        self.dataset_id = reviewed_dataset_id

    def normalize(self, row: dict[str, Any]) -> NormalizedRiskPoint:
        missing = self.required_fields - row.keys()
        if missing:
            raise ValueError(f"schema drift: missing required fields {sorted(missing)}")
        try:
            occurred_at = str(row["occurred_at"])
            if occurred_at.endswith("Z"):
                occurred_at = f"{occurred_at[:-1]}+00:00"
            parsed_time = datetime.fromisoformat(occurred_at)
        except (TypeError, ValueError) as error:
            raise ValueError("schema drift: invalid reviewed timestamp") from error
        if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
            raise ValueError("schema drift: timestamp must include an explicit timezone offset")
        try:
            parsed_time = parsed_time.astimezone(timezone.utc)
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            weight = float(row["severity"])
        except (TypeError, ValueError) as error:
            raise ValueError("schema drift: invalid reviewed field value") from error
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or weight < 0:
            raise ValueError("schema drift: reviewed point is out of range")
        return NormalizedRiskPoint(
            source_row_id=str(row["incident_id"]),
            latitude=latitude,
            longitude=longitude,
            occurred_at=parsed_time,
            weight=weight,
            source_payload=dict(row),
        )

    def fetch(
        self, boundary_wkt: str, since: datetime, client: SocrataClient
    ) -> ConnectorFetch:
        if since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        if self.dataset_id is None:
            raise ReviewedConnectorUnavailable(
                "no reviewed point-capable King County data mapping is configured"
            )
        utc_since = since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        where = (
            f"occurred_at >= '{utc_since}' AND "
            f"within_polygon(location, '{boundary_wkt}')"
        )
        rows = client.get(
            self.dataset_id,
            where=where,
            select="incident_id, latitude, longitude, occurred_at, severity",
            order="occurred_at asc, incident_id asc",
            limit=self.page_size,
        )
        return ConnectorFetch(
            connector_key=self.connector_key,
            connector_schema_version=self.schema_version,
            attribution=self.attribution,
            rows=tuple(self.normalize(dict(row)) for row in rows),
        )
