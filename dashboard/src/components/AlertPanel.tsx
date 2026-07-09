import type { Alert } from "../lib/types";
import { SimulatedBadge } from "./SimulatedBadge";

interface AlertPanelProps {
  alert: Alert | null;
  onEscalate?: (alertId: string) => Promise<void> | void;
  apiBaseUrl?: string;
}

async function defaultEscalate(alertId: string, apiBaseUrl: string): Promise<void> {
  await fetch(`${apiBaseUrl}/api/alerts/${alertId}/escalate`, { method: "POST" });
}

export function AlertPanel({ alert, onEscalate, apiBaseUrl = "" }: AlertPanelProps) {
  if (!alert) {
    return <div className="alert-panel alert-panel--empty">No active alert.</div>;
  }

  const mapsUrl = `https://www.google.com/maps?q=${alert.location.lat},${alert.location.lon}`;

  const handleDispatch = () => {
    const escalate = onEscalate ?? ((id: string) => defaultEscalate(id, apiBaseUrl));
    void escalate(alert.alert_id);
  };

  return (
    <div className="alert-panel">
      <div className="alert-panel__header">
        <SimulatedBadge source={alert.source} />
        <span className="alert-panel__mode">{alert.detection_mode}</span>
      </div>
      <p>
        GPS: {alert.location.lat.toFixed(5)}, {alert.location.lon.toFixed(5)}{" "}
        <a href={mapsUrl} target="_blank" rel="noreferrer">
          Open in Maps
        </a>
      </p>
      <p>{alert.confirmed ? "Confirmed by second drone" : "Awaiting second-drone confirmation"}</p>
      {alert.thermal_clip_ref && <p>Thermal clip: {alert.thermal_clip_ref}</p>}
      {alert.detection_mode === "operator-assist" && (
        <p className="alert-panel__operator-assist">
          The model highlighted a candidate distress signature. A human operator must confirm
          before dispatch.
        </p>
      )}
      <button type="button" className="alert-panel__dispatch" onClick={handleDispatch}>
        Confirm &amp; Dispatch
      </button>
    </div>
  );
}
