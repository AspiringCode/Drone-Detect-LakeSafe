import type { Drone, RegisteredDrone } from "../lib/types";

// Real devices report their inventory UUID; the first block matches the Device ID shown in the registry.
const shortId = (id: string) => id.replace(/^([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i, "$1…");

interface DroneRosterProps {
  drones: Drone[];
  /** Real drones assigned to the lake; those without a live position still get a row. */
  registered?: RegisteredDrone[];
}

export function DroneRoster({ drones, registered = [] }: DroneRosterProps) {
  const live = new Set(drones.map((drone) => drone.drone_id));
  const waiting = registered.filter((drone) => !live.has(drone.inventory_id));
  // Real drones report no zone of their own; theirs comes from the lake's assignment.
  const zone = (drone: Drone) => drone.assigned_zone ?? registered.find((item) => item.inventory_id === drone.drone_id)?.zone_id ?? null;
  // Simulated IDs repeat the lake slug ("lake-sammamish-d0"), so show "Sim 1"; the full ID stays in the title.
  const name = (drone: Drone) => registered.find((item) => item.inventory_id === drone.drone_id)?.serial
    ?? (drone.source === "simulated" ? drone.drone_id.replace(/^.*-d(\d+)$/, (_, n) => `Sim ${Number(n) + 1}`) : shortId(drone.drone_id));
  if (drones.length === 0 && waiting.length === 0) {
    return <p className="panel-empty">No drones yet. Start a simulation, or assign a registered drone to this lake.</p>;
  }

  return (
    <table className="drone-roster">
      <thead>
        <tr>
          <th>Drone</th>
          <th>Status</th>
          <th>Battery</th>
          <th>Zone</th>
        </tr>
      </thead>
      <tbody>
        {drones.map((drone) => (
          <tr key={drone.drone_id}>
            <td><span className="drone-id" title={drone.drone_id}><span aria-hidden="true" />{name(drone)}</span><small className="drone-source">{drone.source}</small></td>
            <td><span className="drone-status" data-status={drone.status}><span className="drone-status__dot" aria-hidden="true" />{drone.status.replace(/_/g, " ")}</span></td>
            <td>
              <div className="battery-reading">
                <span>{Math.round(drone.battery * 100)}%</span>
                <span className="battery-meter" role="progressbar" aria-label={`${drone.drone_id} battery`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(drone.battery * 100)}>
                  <span style={{ width: `${Math.round(drone.battery * 100)}%` }} />
                </span>
              </div>
            </td>
            <td><span className={zone(drone) ? "zone-chip" : "zone-chip zone-chip--empty"}>{zone(drone) ?? "-"}</span></td>
          </tr>
        ))}
        {waiting.map((drone) => (
          <tr key={drone.inventory_id}>
            <td><span className="drone-id" title={drone.inventory_id}><span aria-hidden="true" />{drone.serial ?? shortId(drone.inventory_id)}</span><small className="drone-source">real</small></td>
            <td><span className="drone-status" data-status="offline"><span className="drone-status__dot" aria-hidden="true" />{drone.last_heartbeat_at ? "offline" : "awaiting heartbeat"}</span></td>
            <td>-</td>
            <td><span className={drone.zone_id ? "zone-chip" : "zone-chip zone-chip--empty"}>{drone.zone_id ?? "-"}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
