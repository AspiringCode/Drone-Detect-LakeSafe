import { apiRequest } from "./apiClient";
import type { RealFleetSafetyStatus, RegisteredDrone } from "./types";
import type { SupabaseLike } from "./supabase";

type RealSafetyWire = { autonomy: RealFleetSafetyStatus["realAutonomy"]; source?: "real"; heartbeat_age_seconds?: number | null; eligible?: boolean | null; desired_state_version?: number; acknowledged_state_version?: number; active_assignments?: string[]; pending_assignments?: string[] };
type SimulationWire = { simulated_drones: number; waiting_drones: number; real_drones_unaffected: boolean; zones: number; riskmap: { type: "FeatureCollection"; features: unknown[] } };
export type SimulationAction = "simulation/start" | "simulation/drones" | "simulation/stop" | "zones/regenerate";
/** On start, whether real drones are re-planned with the simulation or keep their zones. */
export type RealDroneChoice = "replan" | "keep";

export async function loadRegisteredDrones(lakeId: string, client?: SupabaseLike, fetcher?: typeof fetch): Promise<RegisteredDrone[]> {
  return (await apiRequest<{ drones: RegisteredDrone[] }>(`/api/lakes/${encodeURIComponent(lakeId)}/registered-drones`, undefined, client, fetcher)).drones;
}

/** Start, grow or stop a lake's simulated session, or re-divide its zones; each returns the resulting zone map. */
export function changeSimulation(lakeId: string, action: SimulationAction, client?: SupabaseLike, fetcher?: typeof fetch, realDrones?: RealDroneChoice): Promise<SimulationWire> {
  const init: RequestInit = realDrones ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ real_drones: realDrones }) } : { method: "POST" };
  return apiRequest<SimulationWire>(`/api/lakes/${encodeURIComponent(lakeId)}/${action}`, init, client, fetcher);
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
