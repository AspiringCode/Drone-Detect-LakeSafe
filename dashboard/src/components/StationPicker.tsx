import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { useOptionalActiveStation } from "../hooks/useActiveStation";

export function StationPicker({ page = false, contextLabel }: { page?: boolean; contextLabel?: string }) {
  const principal = useOptionalPrincipal()?.principal;
  const active = useOptionalActiveStation();
  const stations = principal?.memberships.filter((membership) => membership.status === "active") ?? [];
  return <label className={`station-picker${page ? " station-picker--page" : ""}`}>
    <span className="sr-only">Active station</span>
    <select aria-label="Active station" value={active?.station?.station_id ?? ""} onChange={(event) => active?.select(event.target.value)}>
      {!stations.length && <option value="">{contextLabel ?? "No active station"}</option>}
      {stations.map((station) => <option value={station.station_id} key={station.station_id}>{station.station_name}</option>)}
    </select>
  </label>;
}
