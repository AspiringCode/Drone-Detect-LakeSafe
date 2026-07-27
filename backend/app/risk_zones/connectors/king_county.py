from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import ConnectorFetch, NormalizedRiskPoint, SocrataClient, SocrataConnector


class KingCountyIncidentConnector(SocrataConnector):
    """The reviewed King County incident-point contract.

    The dataset and columns below are an explicit integration contract.  If the
    publisher changes any required field, normalization fails closed and the
    caller must quarantine the snapshot.  This connector never reaches into
    the repository fixtures.
    """

    domain = "data.kingcounty.gov"
    dataset_id = "lake-safe-reviewed-incidents"
    connector_key = "king_county_incidents"
    schema_version = "1"
    attribution = "King County Open Data"
    required_fields = frozenset(
        {"incident_id", "latitude", "longitude", "occurred_at", "severity"}
    )
    page_size = 500

    def normalize(self, row: dict[str, Any]) -> NormalizedRiskPoint:
        missing = self.required_fields - row.keys()
        if missing:
            raise ValueError(f"schema drift: missing required fields {sorted(missing)}")
        try:
            occurred_at = str(row["occurred_at"])
            if occurred_at.endswith("Z"):
                occurred_at = f"{occurred_at[:-1]}+00:00"
            parsed_time = datetime.fromisoformat(occurred_at).astimezone(timezone.utc)
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
