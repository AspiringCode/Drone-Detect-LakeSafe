import { apiRequest } from "./apiClient";
import type { FleetDrone, ReconcileStatus, ZonePlanSummary } from "./types";
import type { SupabaseLike } from "./supabase";

type FleetWire = { inventory_id: string; source: "simulated"; lifecycle: string; battery_percent: number | null; health: string; connectivity: string; maintenance_due?: string | null; desired_state_version: number; acknowledged_state_version: number };
type PlanWire = { plan_id: string; snapshot_id: string; algorithm_version: string; source_fresh_through: string | null; activity_data_unavailable?: boolean; cells: Array<{ kind: string }> };

const fleetDrone = (item: FleetWire): FleetDrone => ({
  inventoryId: item.inventory_id, source: item.source, lifecycle: item.lifecycle,
  batteryPercent: item.battery_percent, health: item.health, connectivity: item.connectivity,
  maintenanceDue: item.maintenance_due ?? null, desiredStateVersion: item.desired_state_version,
  acknowledgedStateVersion: item.acknowledged_state_version,
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
    hotspotCells: plan.cells.filter((cell) => cell.kind === "hotspot").length,
    coverageCells: plan.cells.filter((cell) => cell.kind === "coverage").length,
  };
}

export async function requestCirculation(stationId: string, lakeId: string, droneId: string, request: { eligible: boolean; reason: string }, client?: SupabaseLike, fetcher?: typeof fetch): Promise<ReconcileStatus> {
  const payload = await apiRequest<{ reconciliation_id: string; desired_state_version: number; acknowledged_state_version: number }>(
    `/api/stations/${encodeURIComponent(stationId)}/lakes/${encodeURIComponent(lakeId)}/circulation/${encodeURIComponent(droneId)}`,
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) }, client, fetcher,
  );
  return { reconciliationId: payload.reconciliation_id, desiredStateVersion: payload.desired_state_version, acknowledgedStateVersion: payload.acknowledged_state_version };
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
