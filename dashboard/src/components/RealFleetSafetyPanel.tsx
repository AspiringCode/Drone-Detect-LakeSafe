import { useState } from "react";
import type { Capability, RealFleetSafetyStatus } from "../lib/types";

function describeState(state: RealFleetSafetyStatus["realAutonomy"]) {
  const descriptions = {
    paused: "Real autonomy is paused.",
    pending_ack: "Waiting for device acknowledgement. Desired policy is not active yet.",
    active: "Real autonomy is acknowledged by the active fleet.",
    degraded: "Reduced real-fleet capacity is active; unavailable devices are excluded.",
    safe_return_requested: "A fleet-wide safe return has been requested and awaits device acknowledgement.",
    gateway_unavailable: "The real-device gateway is unavailable. The last acknowledged state is preserved.",
  } as const;
  return descriptions[state];
}

function heartbeat(age: number | null) {
  return age === null ? "No signed heartbeat received" : `Last signed heartbeat ${age} seconds ago`;
}

export function RealFleetSafetyPanel({ capabilities, status, busy = false, error, onSetAutonomy, onRequestSafeReturn }: {
  capabilities: Capability[];
  status: RealFleetSafetyStatus;
  busy?: boolean;
  error?: string | null;
  onSetAutonomy: (enabled: boolean, reason: string) => void;
  onRequestSafeReturn: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const canManage = capabilities.includes("autonomy.manage");
  const submit = (action: "enable" | "pause" | "return") => {
    const trimmed = reason.trim();
    if (!trimmed) { setValidationError("A safety reason is required."); return; }
    setValidationError(null);
    if (action === "return") onRequestSafeReturn(trimmed);
    else onSetAutonomy(action === "enable", trimmed);
  };
  return <section className="panel-card real-fleet-safety" aria-label="Real fleet safety status">
    <div className="panel-heading"><h2>Real drone safety</h2><span className={`real-safety-state real-safety-state--${status.realAutonomy}`}>{status.realAutonomy.replace(/_/g, " ")}</span></div>
    <p className="real-safety-copy" role="status">{describeState(status.realAutonomy)}</p>
    <dl className="real-safety-details">
      <div><dt>Heartbeat</dt><dd>{heartbeat(status.heartbeatAgeSeconds)}</dd></div>
      <div><dt>Eligibility</dt><dd>{status.eligible === null ? "Not reported" : status.eligible ? "Eligible" : "Not eligible"}</dd></div>
    </dl>
    {canManage && <div className="real-safety-actions">
      <label>Safety reason<textarea aria-label="Safety reason" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} placeholder="Record the operational reason" /></label>
      {(validationError || error) && <p className="form-error" role="alert">{validationError ?? error}</p>}
      <div className="real-safety-buttons">
        {status.realAutonomy === "paused" || status.realAutonomy === "gateway_unavailable" ? <button className="button-secondary" disabled={busy} onClick={() => submit("enable")}>Enable real autonomy</button> : <button className="button-secondary" disabled={busy} onClick={() => submit("pause")}>Pause real autonomy</button>}
        <button className="button-secondary real-safety-return" disabled={busy} onClick={() => submit("return")}>Request fleet safe return</button>
      </div>
    </div>}
  </section>;
}
