export type Source = "real" | "simulated";

export interface LatLon {
  lat: number;
  lon: number;
}

export interface Lake {
  lake_id: string;
  org_id: string;
  name: string;
  centroid_lat: number;
  centroid_lon: number;
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

export interface Alert {
  alert_id: string;
  created_at: string;
  location: LatLon;
  detection_mode: string;
  drone_id: string;
  thermal_clip_ref: string | null;
  confirmed: boolean;
  source: Source;
  latency_ms: number | null;
}

export interface SimulationState {
  drones: Drone[];
  conflicts: [string, string][];
  t: number;
  altitudes?: Record<string, number>;
  confirmed?: boolean;
}
