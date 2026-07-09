import type { DroneStatus, RiskZone } from "./types";

export interface ZoneStyle {
  color: string;
  fillColor: string;
  fillOpacity: number;
  dashArray?: string;
  className: string;
}

export function riskZoneStyle(zone: RiskZone): ZoneStyle {
  const clamped = Math.max(0, Math.min(1, zone.risk_score));
  const hue = (1 - clamped) * 210; // 210 = blue (low risk) -> 0 = red (high risk)
  const color = `hsl(${hue}, 80%, 45%)`;
  return {
    color,
    fillColor: color,
    fillOpacity: 0.35,
    dashArray: zone.is_proxy ? "6 4" : undefined,
    className: zone.is_proxy ? "risk-zone risk-zone--proxy" : "risk-zone",
  };
}

const STATUS_COLORS: Record<DroneStatus, string> = {
  idle: "#6b7280",
  en_route: "#f59e0b",
  patrolling: "#2563eb",
  investigating: "#dc2626",
  returning: "#a855f7",
  charging: "#16a34a",
};

export function droneMarkerColor(status: DroneStatus): string {
  return STATUS_COLORS[status];
}
