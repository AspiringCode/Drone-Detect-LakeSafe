"""Reviewed King County swim-beach access and environmental proxy data."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.models import RiskPointProvenance

from .base import ConnectorFetch, NormalizedRiskPoint, SocrataClient, SocrataConnector


PUBLISHER_TIMEZONE = ZoneInfo("America/Los_Angeles")
SUPPORTED_LOCATORS = frozenset({"0615SB", "SAMMLANDINGSB", "E708SB", "A709SB"})


class KingCountySwimBeachProxyConnector(SocrataConnector):
    """Join reviewed seasonal observations to their reviewed monitoring sites."""

    domain = "data.kingcounty.gov"
    connector_key = "king_county_swim_beach_proxy"
    schema_version = "2"
    attribution = "King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites"
    observations_required_fields = frozenset(
        # Socrata omits null measurement keys. This proxy uses observation
        # presence, not temperatures or sample values; never invent those.
        {"beach", "locator", "date"}
    )
    sites_required_fields = frozenset({"locator", "site", "latitude", "longitude", "status", "area"})
    page_size = 500

    def __init__(
        self,
        locators: tuple[str, ...],
        observations_dataset_id: str = "mbzm-4r9y",
        sites_dataset_id: str = "e9bt-i75a",
    ) -> None:
        if not locators or len(set(locators)) != len(locators) or any(locator not in SUPPORTED_LOCATORS for locator in locators):
            raise ValueError("schema drift: unsupported or duplicate swim-beach locator")
        if observations_dataset_id != "mbzm-4r9y":
            raise ValueError("schema drift: unreviewed observations dataset ID")
        if sites_dataset_id != "e9bt-i75a":
            raise ValueError("schema drift: unreviewed sites dataset ID")
        self.locators = tuple(locators)
        self.observations_dataset_id = observations_dataset_id
        self.sites_dataset_id = sites_dataset_id
        self.dataset_id = observations_dataset_id

    @staticmethod
    def _locator_where(locators: tuple[str, ...]) -> str:
        return ", ".join(f"'{locator}'" for locator in locators)

    @staticmethod
    def _occurred_at(row: dict[str, object]) -> datetime:
        try:
            raw_date = str(row["date"])
            try:
                observed_date = date.fromisoformat(raw_date)
            except ValueError:
                observed_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
            raw_time = row.get("time")
            if raw_time in (None, ""):
                observed_time = time.min
            else:
                value = str(raw_time).strip()
                try:
                    observed_time = time.fromisoformat(value)
                except ValueError:
                    observed_time = datetime.strptime(value, "%I:%M %p").time()
        except (TypeError, ValueError) as error:
            raise ValueError("schema drift: invalid publisher date or time") from error
        return datetime.combine(observed_date, observed_time, PUBLISHER_TIMEZONE).astimezone(timezone.utc)

    @staticmethod
    def _coordinates(site: dict[str, object]) -> tuple[float, float]:
        try:
            latitude = float(site["latitude"])
            longitude = float(site["longitude"])
        except (TypeError, ValueError) as error:
            raise ValueError("schema drift: invalid monitoring-site coordinate") from error
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("schema drift: monitoring-site coordinate is out of range")
        return latitude, longitude

    def normalize(self, row: dict[str, object]) -> NormalizedRiskPoint:
        """Normalize a validated joined publisher row for the connector contract."""
        observation = row.get("observation")
        site = row.get("site")
        if not isinstance(observation, dict) or not isinstance(site, dict):
            raise ValueError("schema drift: invalid swim-beach join")
        missing_observation = self.observations_required_fields - observation.keys()
        missing_site = self.sites_required_fields - site.keys()
        if missing_observation or missing_site:
            raise ValueError("schema drift: missing required swim-beach fields")
        locator = observation["locator"]
        if not isinstance(locator, str) or locator not in self.locators or site.get("locator") != locator:
            raise ValueError("schema drift: unreviewed swim-beach locator")
        occurred_at = self._occurred_at(observation)
        latitude, longitude = self._coordinates(site)
        return NormalizedRiskPoint(
            source_row_id=f"{locator}:{occurred_at.isoformat()}",
            latitude=latitude,
            longitude=longitude,
            occurred_at=occurred_at,
            weight=1.0,
            source_payload={"observation": dict(observation), "site": dict(site)},
            category="access_environment_proxy",
            is_proxy=True,
            provenance=RiskPointProvenance(
                self.connector_key, f"{locator}:{occurred_at.isoformat()}", locator, occurred_at,
            ),
        )

    def fetch(
        self, boundary_wkt: str, since: datetime, client: SocrataClient
    ) -> ConnectorFetch:
        del boundary_wkt  # Publisher rows are joined by reviewed site locator, not shoreline containment.
        if since.tzinfo is None or since.utcoffset() is None:
            raise ValueError("since must be timezone-aware")
        local_since = since.astimezone(PUBLISHER_TIMEZONE).date().isoformat()
        locator_list = self._locator_where(self.locators)
        observations = client.get(
            self.observations_dataset_id,
            select="beach, locator, date, time, watertempc, watertempf, hightoday",
            where=f"locator IN ({locator_list}) AND date >= '{local_since}'",
            order="locator asc, date desc, time desc",
            limit=self.page_size,
        )
        sites = client.get(
            self.sites_dataset_id,
            select="locator, site, latitude, longitude, status, area",
            where=f"locator IN ({locator_list})",
            order="locator asc, site asc",
            limit=self.page_size,
        )
        site_by_locator: dict[str, dict[str, object]] = {}
        for raw_site in sites:
            site = dict(raw_site)
            missing = self.sites_required_fields - site.keys()
            locator = site.get("locator")
            if missing or not isinstance(locator, str) or locator not in self.locators:
                raise ValueError("schema drift: invalid monitoring-site mapping")
            if locator in site_by_locator:
                raise ValueError("schema drift: duplicate monitoring-site mapping")
            self._coordinates(site)
            site_by_locator[locator] = site

        newest: dict[str, tuple[datetime, dict[str, object]]] = {}
        utc_since = since.astimezone(timezone.utc)
        for raw_observation in observations:
            observation = dict(raw_observation)
            missing = self.observations_required_fields - observation.keys()
            locator = observation.get("locator")
            if missing or not isinstance(locator, str) or locator not in self.locators:
                raise ValueError("schema drift: invalid swim-beach observation")
            occurred_at = self._occurred_at(observation)
            if occurred_at < utc_since:
                continue
            current = newest.get(locator)
            if current is None or occurred_at > current[0]:
                newest[locator] = (occurred_at, observation)

        rows = tuple(
            self.normalize({"observation": observation, "site": site_by_locator[locator]})
            for locator, (_, observation) in sorted(newest.items())
            if locator in site_by_locator
        )
        if len(rows) != len(newest):
            raise ValueError("schema drift: missing monitoring-site mapping")
        return ConnectorFetch(
            connector_key=self.connector_key,
            connector_schema_version=self.schema_version,
            attribution=self.attribution,
            rows=rows,
        )
