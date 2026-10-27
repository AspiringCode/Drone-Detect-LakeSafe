"""Restore operational simulation contexts from persisted, validated plans."""
from functools import lru_cache
import math
from shapely.ops import transform
from shapely import wkb
from shapely.geometry import shape
from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from app.models import LatLon, RiskZone
from app.supabase_transport import create_server_client as create_client
from app.risk_zones.tessellation import patrol_center_and_radius


def geometry(value):
    return shape(value) if isinstance(value, dict) else wkb.loads(bytes.fromhex(value))


def zones_from_plan(context):
    shoreline = geometry(context["shoreline"])
    if shoreline.is_empty or not shoreline.is_valid:
        raise ValueError("Invalid stored shoreline")
    zones = []
    for cell in context.get("cells") or []:
        boundary, seed = geometry(cell["boundary"]), geometry(cell["seed"])
        if boundary.geom_type != "Polygon" or boundary.is_empty or not boundary.is_valid:
            raise ValueError("Invalid stored plan geometry")
        # Match candidate validation's sub-millimetre tolerance after PostGIS round trips.
        covered = shoreline.covers(boundary) or shoreline.buffer(1e-9).covers(boundary)
        if not covered or seed.geom_type != "Point" or not boundary.covers(seed):
            raise ValueError("Invalid stored plan geometry")
        metadata = cell.get("metadata") or {}
        mean_lat = boundary.centroid.y
        scale = math.cos(math.radians(mean_lat))
        center, radius_m = patrol_center_and_radius(transform(lambda x, y, z=None: (x * scale, y), boundary), mean_lat)
        zones.append(RiskZone(
            zone_id=str(cell["zone_plan_cell_id"]), centroid=center,
            polygon=[LatLon(y, x) for x, y in boundary.exterior.coords],
            risk_score=float(cell["risk_score"]), components={}, is_proxy=bool(metadata.get("is_proxy")),
            radius_m=radius_m, seed=LatLon(seed.y, seed.x),
            holes=tuple(tuple(LatLon(y, x) for x, y in ring.coords) for ring in boundary.interiors),
        ))
    if not zones:
        raise ValueError("Stored plan has no cells")
    return zones


class SupabaseLakeRuntimeRepository:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("Lake setup service is unavailable")
        self._client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def runtime_context(self, lake_id):
        row = self._client.table("lakes").select("lake_id,station_id,name,shoreline,demo_source_lake_id,stations(simulation_only)").eq("lake_id", lake_id).maybe_single().execute().data
        if not row:
            return None
        if row.get("demo_source_lake_id") and (row.get("stations") or {}).get("simulation_only") is True:
            return {**row, "setup_status": "ready", "simulation_source_lake_id": row["demo_source_lake_id"], "plan_id": None, "cells": []}
        plan = self._client.table("zone_plans").select("zone_plan_id,zone_plan_cells(zone_plan_cell_id,ordinal,boundary,seed,risk_score,metadata)").eq("lake_id", lake_id).eq("station_id", row["station_id"]).eq("status", "active").maybe_single().execute().data
        job = self._client.table("risk_refresh_jobs").select("status,failure_reason").eq("lake_id", lake_id).maybe_single().execute().data or {}
        return {**row, "setup_status": "ready" if plan else ("failed" if job.get("status") == "failed" else "queued"),
                "refresh_status": job.get("status"), "plan_id": plan["zone_plan_id"] if plan else None,
                "cells": sorted(plan.get("zone_plan_cells") or [], key=lambda cell: cell["ordinal"]) if plan else []}


@lru_cache(maxsize=1)
def get_lake_runtime_repository():
    return SupabaseLakeRuntimeRepository()
