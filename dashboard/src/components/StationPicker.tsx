import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { useOptionalActiveStation } from "../hooks/useActiveStation";
import type { Capability } from "../lib/types";

export function StationPicker({ page = false, contextLabel, stationId, onSelect, capability, disabled = false }: { page?: boolean; contextLabel?: string; stationId?: string; onSelect?: (id: string) => void; capability?: Capability; disabled?: boolean }) {
  const principal = useOptionalPrincipal()?.principal;
  const active = useOptionalActiveStation();
  const stations = principal?.memberships.filter((membership) => membership.status === "active" && (!capability || membership.capabilities.includes(capability))) ?? [];
  return <label className={`station-picker${page ? " station-picker--page" : ""}`}>
    <span className="sr-only">Active station</span>
    <select aria-label="Active station" disabled={disabled} value={stationId ?? active?.station?.station_id ?? ""} onChange={(event) => { active?.select(event.target.value); onSelect?.(event.target.value); }}>
      {!stations.length && <option value="">{contextLabel ?? "No active station"}</option>}
      {stations.map((station) => <option value={station.station_id} key={station.station_id}>{station.station_name}</option>)}
    </select>
  </label>;
}
