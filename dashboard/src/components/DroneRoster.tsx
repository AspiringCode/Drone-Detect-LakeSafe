import type { Drone } from "../lib/types";

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
            <td>{drone.drone_id}</td>
            <td><span className="drone-status"><span className="drone-status__dot" aria-hidden="true" />{drone.status.replace(/_/g, " ")}</span></td>
            <td>{Math.round(drone.battery * 100)}%</td>
            <td>{drone.assigned_zone ?? "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
