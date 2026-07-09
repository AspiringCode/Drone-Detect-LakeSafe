import type { Drone } from "../lib/types";

interface DroneRosterProps {
  drones: Drone[];
}

export function DroneRoster({ drones }: DroneRosterProps) {
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
            <td>{drone.status}</td>
            <td>{Math.round(drone.battery * 100)}%</td>
            <td>{drone.assigned_zone ?? "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
