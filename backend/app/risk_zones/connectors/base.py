from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, Sequence

from app.models import RiskPointProvenance


class SocrataClient(Protocol):
    def get(self, dataset_id: str, **query: Any) -> Sequence[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class NormalizedRiskPoint:
    source_row_id: str
    latitude: float
    longitude: float
    occurred_at: datetime
    weight: float
    source_payload: dict[str, Any]
    category: Literal["incidents", "access_environment_proxy"] = "incidents"
    is_proxy: bool = False
    provenance: RiskPointProvenance | None = None


@dataclass(frozen=True, slots=True)
class ConnectorFetch:
    connector_key: str
    connector_schema_version: str
    attribution: str
    rows: tuple[NormalizedRiskPoint, ...]


class SocrataConnector(ABC):
    """A reviewed, versioned SoQL contract for a single publisher dataset."""

    domain: str
    dataset_id: str
    connector_key: str
    schema_version: str
    attribution: str
    required_fields: frozenset[str]

    @abstractmethod
    def normalize(self, row: dict[str, Any]) -> NormalizedRiskPoint: ...

    @abstractmethod
    def fetch(
        self, boundary_wkt: str, since: datetime, client: SocrataClient
    ) -> ConnectorFetch: ...
