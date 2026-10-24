import { apiRequest } from "./apiClient";
import type { FleetDrone, RealFleetSafetyStatus, ReconcileStatus, Source, ZonePlanSummary } from "./types";
import type { SupabaseLike } from "./supabase";

type FleetWire = { inventory_id: string; source: Source; lifecycle: string; battery_percent: number | null; health: string; connectivity: string; maintenance_due?: string | null; heartbeat_age_seconds?: number | null; eligible?: boolean | null; desired_state_version: number; acknowledged_state_version: number };
type RealSafetyWire = { autonomy: RealFleetSafetyStatus["realAutonomy"]; source?: "real"; heartbeat_age_seconds?: number | null; eligible?: boolean | null; desired_state_version?: number; acknowledged_state_version?: number; active_assignments?: string[]; pending_assignments?: string[] };
type PlanWire = { plan_id: string; snapshot_id: string; algorithm_version: string; source_fresh_through: string | null; source_attribution?: string[]; activity_data_unavailable?: boolean; cells: Array<{ kind: string; metadata?: { is_proxy?: boolean } }> };

const fleetDrone = (item: FleetWire): FleetDrone => ({
  inventoryId: item.inventory_id, source: item.source, lifecycle: item.lifecycle,
  batteryPercent: item.battery_percent, health: item.health, connectivity: item.connectivity,
  maintenanceDue: item.maintenance_due ?? null, desiredStateVersion: item.desired_state_version,
  acknowledgedStateVersion: item.acknowledged_state_version, heartbeatAgeSeconds: item.heartbeat_age_seconds ?? null,
  eligible: item.eligible ?? null,
});

export async function loadFleet(stationId: string, lakeId: string, client?: SupabaseLike, fetcher?: typeof fetch): Promise<FleetDrone[]> {
  const payload = await apiRequest<{ drones: FleetWire[] }>(`/api/stations/${encodeURIComponent(stationId)}/lakes/${encodeURIComponent(lakeId)}/fleet`, undefined, client, fetcher);
  return payload.drones.map(fleetDrone);
}

export async function loadZonePlan(stationId: string, lakeId: string, client?: SupabaseLike, fetcher?: typeof fetch): Promise<ZonePlanSummary> {
  const plan = await apiRequest<PlanWire>(`/api/stations/${encodeURIComponent(stationId)}/lakes/${encodeURIComponent(lakeId)}/zone-plan`, undefined, client, fetcher);
  return {
    planId: plan.plan_id, snapshotId: plan.snapshot_id, algorithmVersion: plan.algorithm_version,
    sourceFreshThrough: plan.source_fresh_through, activityDataUnavailable: Boolean(plan.activity_data_unavailable),
    priorityCells: plan.cells.filter((cell) => cell.kind === "hotspot").length,
    proxyPriorityCells: plan.cells.filter((cell) => cell.kind === "hotspot" && cell.metadata?.is_proxy === true).length,
    coverageCells: plan.cells.filter((cell) => cell.kind === "coverage").length,
    fallbackCells: plan.cells.filter((cell) => cell.kind === "fallback").length,
    sourceAttribution: plan.source_attribution ?? [],
  };
}

export async function requestCirculation(stationId: string, lakeId: string, droneId: string, request: { eligible: boolean; reason: string }, client?: SupabaseLike, fetcher?: typeof fetch): Promise<ReconcileStatus> {
  const payload = await apiRequest<{ reconciliation_id: string; desired_state_version: number; acknowledged_state_version: number }>(
    `/api/stations/${encodeURIComponent(stationId)}/lakes/${encodeURIComponent(lakeId)}/circulation/${encodeURIComponent(droneId)}`,
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) }, client, fetcher,
  );
  return { reconciliationId: payload.reconciliation_id, desiredStateVersion: payload.desired_state_version, acknowledgedStateVersion: payload.acknowledged_state_version };
}

function safetyStatus(payload: RealSafetyWire): RealFleetSafetyStatus {
  if (!(["paused", "pending_ack", "active", "degraded", "safe_return_requested", "gateway_unavailable"] as const).includes(payload.autonomy)) {
    throw new Error("Real fleet safety status is unavailable");
  }
  return {
    source: "real", realAutonomy: payload.autonomy,
    heartbeatAgeSeconds: payload.heartbeat_age_seconds ?? null, eligible: payload.eligible ?? null,
    desiredStateVersion: payload.desired_state_version ?? 0,
    acknowledgedStateVersion: payload.acknowledged_state_version ?? 0,
    activeAssignments: payload.active_assignments ?? [], pendingAssignments: payload.pending_assignments ?? [],
  };
}

export async function loadRealFleetSafetyStatus(stationId: string, lakeId: string, client?: SupabaseLike, fetcher?: typeof fetch): Promise<RealFleetSafetyStatus> {
  const payload = await apiRequest<RealSafetyWire>(`/api/stations/${encodeURIComponent(stationId)}/lakes/${encodeURIComponent(lakeId)}/safety/status`, undefined, client, fetcher);
  return safetyStatus(payload);
}

/** Safety policy endpoints accept only a fleet-wide policy and a human reason. */
export async function setRealAutonomy(stationId: string, lakeId: string, enabled: boolean, reason: string, client?: SupabaseLike, fetcher?: typeof fetch): Promise<RealFleetSafetyStatus> {
  const payload = await apiRequest<RealSafetyWire>(`/api/stations/${encodeURIComponent(stationId)}/lakes/${encodeURIComponent(lakeId)}/safety/autonomy`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ enabled, reason }),
  }, client, fetcher);
  return safetyStatus(payload);
}

export async function requestSafeReturn(stationId: string, lakeId: string, reason: string, client?: SupabaseLike, fetcher?: typeof fetch): Promise<RealFleetSafetyStatus> {
  const payload = await apiRequest<RealSafetyWire>(`/api/stations/${encodeURIComponent(stationId)}/lakes/${encodeURIComponent(lakeId)}/safety/safe-return`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ reason }),
  }, client, fetcher);
  return safetyStatus(payload);
}

/** A request changes desired state only.  The acknowledged runtime lifecycle
 * remains server-reported until a later fleet refresh confirms the change. */
export function applyReconcileStatus(drones: FleetDrone[], droneId: string, status: ReconcileStatus): FleetDrone[] {
  return drones.map((drone) => drone.inventoryId === droneId ? {
    ...drone,
    desiredStateVersion: status.desiredStateVersion,
    acknowledgedStateVersion: status.acknowledgedStateVersion,
  } : drone);
}
