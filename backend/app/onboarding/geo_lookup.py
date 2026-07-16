from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_PRIMARY_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_KUMI_URL = "https://overpass.kumi.systems/api/interpreter"
USER_AGENT = "LakeSafe-CAC/1.0"
OVERPASS_RADIUS_M = 10_000


class AddressNotFoundError(ValueError):
    """Raised when Nominatim cannot locate an onboarding address."""


@dataclass(frozen=True)
class LatLon:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class NearbyLake:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class NearbyLakeLookup:
    address: str
    coordinates: LatLon
    lakes: list[NearbyLake]


def _get_json(client: httpx.Client, url: str, **kwargs: Any) -> Any:
    response = client.get(url, **kwargs)
    response.raise_for_status()
    return response.json()


def _overpass_query(latitude: float, longitude: float) -> str:
    return (
        "[out:json][timeout:25];"
        f"(nwr[\"natural\"=\"water\"](around:{OVERPASS_RADIUS_M},{latitude},{longitude});"
        f"nwr[\"water\"](around:{OVERPASS_RADIUS_M},{latitude},{longitude}););"
        "out center tags;"
    )


def _lake_from_element(element: dict[str, Any]) -> NearbyLake | None:
    name = element.get("tags", {}).get("name")
    center = element.get("center")
    if not name:
        return None
    if center is not None:
        latitude, longitude = center.get("lat"), center.get("lon")
    else:
        latitude, longitude = element.get("lat"), element.get("lon")
    if latitude is None or longitude is None:
        return None
    return NearbyLake(name=str(name), latitude=float(latitude), longitude=float(longitude))


def lookup_nearby_lakes(address: str) -> NearbyLakeLookup:
    """Geocode an address and return named water bodies within ten kilometres."""
    client = httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT})
    try:
        results = _get_json(
            client,
            NOMINATIM_URL,
            params={"q": address, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": USER_AGENT},
        )
        if not results:
            raise AddressNotFoundError(f"No location found for {address!r}")
        coordinates = LatLon(latitude=float(results[0]["lat"]), longitude=float(results[0]["lon"]))
        query = _overpass_query(coordinates.latitude, coordinates.longitude)
        try:
            data = _get_json(client, OVERPASS_PRIMARY_URL, params={"data": query})
        except httpx.HTTPError:
            data = _get_json(client, OVERPASS_KUMI_URL, params={"data": query})
        lakes = [lake for element in data.get("elements", []) if (lake := _lake_from_element(element))]
        return NearbyLakeLookup(address=address, coordinates=coordinates, lakes=lakes)
    finally:
        client.close()
