import type { Capability, FleetDrone } from "../lib/types";

export function AutonomyControls({ capabilities, drones, pendingId, reconciliationId, error, onRequest }: { capabilities: Capability[]; drones: FleetDrone[]; pendingId?: string | null; reconciliationId?: string | null; error?: string | null; onRequest: (droneId: string, request: { eligible: boolean; reason: string }) => void }) {
  if (!capabilities.includes("autonomy.manage")) return null;
  const actionable = drones.filter((drone) => drone.source === "simulated");
  return <section className="panel-card autonomy-card" aria-label="Autonomous circulation controls">
    <div className="panel-heading"><div><p className="panel-eyebrow">Safety control</p><h2>Circulation eligibility</h2></div></div>
    <p className="panel-empty">Autonomy selects coverage assignments after a safety-reviewed eligibility change.</p>
    {reconciliationId && <p className="reconcile-status" role="status">Reconciliation queued</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="autonomy-actions">{actionable.map((drone) => {
      const isCirculating = drone.lifecycle === "circulating";
      const busy = pendingId === drone.inventoryId;
      return <button key={drone.inventoryId} className="button-secondary" disabled={busy} onClick={() => onRequest(drone.inventoryId, { eligible: !isCirculating, reason: isCirculating ? "safety hold" : "coverage" })}>{busy ? "Updating…" : isCirculating ? `Hold ${drone.inventoryId}` : `Add ${drone.inventoryId} to circulation`}</button>;
    })}</div>
  </section>;
}
