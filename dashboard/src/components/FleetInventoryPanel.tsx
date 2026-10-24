import type { FleetDrone } from "../lib/types";

export function FleetInventoryPanel({ drones }: { drones: FleetDrone[] }) {
  const circulating = drones.filter((drone) => drone.lifecycle === "circulating").length;
  return <section className="panel-card inventory-card" aria-label="Fleet inventory">
    <div className="panel-heading"><div><p className="panel-eyebrow">Inventory</p><h2>Fleet inventory</h2></div><strong className="inventory-count">{circulating} <small>of {drones.length} records circulating</small></strong></div>
    <p className="field-help">Simulated inventory records assigned to this lake. Live map markers and registered real drones are counted separately.</p>
    {!drones.length ? <p className="panel-empty">No simulated inventory records are assigned to this lake.</p> : <ul className="fleet-inventory-list">{drones.map((drone) => {
      const pending = drone.desiredStateVersion !== drone.acknowledgedStateVersion;
      return <li key={drone.inventoryId}><div><strong>{drone.inventoryId}</strong><span>{drone.source} · {drone.lifecycle}</span></div><div className={pending ? "sync-state sync-state--pending" : "sync-state"}><strong>{pending ? "Update pending" : "Acknowledged"}</strong><span>Desired {drone.desiredStateVersion}</span><span>Acknowledged {drone.acknowledgedStateVersion}</span></div></li>;
    })}</ul>}
  </section>;
}
