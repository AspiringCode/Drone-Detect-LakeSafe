export type Source = "real" | "simulated";

export type Capability =
  | "station.read" | "alert.manage" | "autonomy.manage" | "fleet_safety.manage"
  | "lake.create" | "inventory.manage" | "member.manage";

export interface StationMembership {
  station_id: string;
  station_name: string;
  status: "active" | "invited" | "suspended" | "revoked" | "inactive_station" | string;
  roles: string[];
  capabilities: Capability[];
}

export interface Principal {
  user_id: string;
  email: string;
  aal: "aal1" | "aal2" | string;
  account_class: "civilian" | "officer";
  verification_status: "not_started" | "pending" | "verified" | "rejected" | "expired" | "revoked" | string;
  reviewer: boolean;
  judge_demo_access?: boolean;
  memberships: StationMembership[];
}

export interface LatLon {
  lat: number;
  lon: number;
}

export interface Lake {
  lake_id: string;
  org_id: string | null;
  station_id?: string;
  name: string;
  centroid_lat: number;
  centroid_lon: number;
  map_bounds?: [number, number, number, number] | null;
}
export interface LakeCandidate { name: string; lat: number; lon: number; }

export interface RiskZone {
  zone_id: string;
  centroid: LatLon;
  polygon: LatLon[];
  risk_score: number;
  components: Record<string, number>;
  is_proxy: boolean;
}

export type DroneStatus =
  | "idle"
  | "en_route"
  | "patrolling"
  | "investigating"
  | "returning"
  | "charging";

export interface Drone {
  drone_id: string;
  pos: LatLon;
  battery: number;
  status: DroneStatus;
  assigned_zone: string | null;
  source: Source;
}

export interface Detection {
  frame_idx: number;
  bbox: [number, number, number, number];
  confidence: number;
  timestamp: string;
  source: Source;
}

export type AlertDecision = 'confirmed' | 'dismissed' | 'ended';
export interface Investigation {
  alert_id: string; detecting: string; confirmer: string | null;
  phase: 'en_route' | 'awaiting_finding' | 'finding_received' | 'returning' | 'returned' | 'unavailable' | 'failed';
  finding: 'observed' | 'not_observed' | 'inconclusive' | null;
  detail?: string | null; finding_alert_id?: string | null;
}
export interface Alert {
  alert_id: string;
  created_at: string;
  location: LatLon;
  detection_mode: string;
  drone_id: string;
  thermal_clip_ref: string | null;
  reviewed_at?: string | null;
  review_decision?: AlertDecision | null;
  investigation?: Investigation | null;
  confirmed: boolean;
  source: Source;
  latency_ms: number | null;
  confidence?: number | null;
  bbox?: [number,number,number,number] | null;
}

export interface SimulationState {
  drones: Drone[];
  conflicts: [string, string][];
  t: number;
  altitudes?: Record<string, number>;
  confirmed?: boolean;
  latest_alert?: Alert | null;
  alerts?: Alert[];
  simulation_running?: boolean;
}

/** A real drone assigned to a lake, listed whether or not it is heartbeating. */
export interface RegisteredDrone {
  inventory_id: string;
  manufacturer: string | null;
  serial: string | null;
  last_heartbeat_at: string | null;
  /** The zone this drone patrols; null when every zone is taken. */
  zone_id?: string | null;
}

export type RealAutonomyState = "paused" | "pending_ack" | "active" | "degraded" | "safe_return_requested" | "gateway_unavailable";

export interface RealFleetSafetyStatus {
  source: "real";
  realAutonomy: RealAutonomyState;
  heartbeatAgeSeconds: number | null;
  eligible: boolean | null;
  desiredStateVersion: number;
  acknowledgedStateVersion: number;
  activeAssignments?: string[];
  pendingAssignments?: string[];
}
