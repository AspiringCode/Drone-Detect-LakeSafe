import type { Drone } from "../lib/types";

// Real devices report their inventory UUID; the first block matches the Device ID shown in the registry.
const shortId = (id: string) => id.replace(/^([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i, "$1…");

interface DroneRosterProps {
  drones: Drone[];
}

export function DroneRoster({ drones }: DroneRosterProps) {
  if (drones.length === 0) {
    return <p className="panel-empty">Waiting for fleet telemetry.</p>;
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
            <td><span className="drone-id" title={drone.drone_id}><span aria-hidden="true" />{shortId(drone.drone_id)}</span><small className="drone-source">{drone.source}</small></td>
            <td><span className="drone-status" data-status={drone.status}><span className="drone-status__dot" aria-hidden="true" />{drone.status.replace(/_/g, " ")}</span></td>
            <td>
              <div className="battery-reading">
                <span>{Math.round(drone.battery * 100)}%</span>
                <span className="battery-meter" role="progressbar" aria-label={`${drone.drone_id} battery`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(drone.battery * 100)}>
                  <span style={{ width: `${Math.round(drone.battery * 100)}%` }} />
                </span>
              </div>
            </td>
            <td><span className={drone.assigned_zone ? "zone-chip" : "zone-chip zone-chip--empty"}>{drone.assigned_zone ?? "-"}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
