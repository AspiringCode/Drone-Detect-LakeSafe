import { useEffect, useState } from "react";
import type { Alert } from "../lib/types";
import { SimulatedBadge } from "./SimulatedBadge";

interface AlertPanelProps {
  alert: Alert | null;
  onEscalate?: (alertId: string) => Promise<void> | void;
  apiBaseUrl?: string;
  onEvidence?: (alertId: string) => Promise<{ url: string; expires_in: number }>;
}

export function AlertPanel({ alert, onEscalate, onEvidence }: AlertPanelProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [evidence, setEvidence] = useState<{url: string; expires: number} | null>(null);
  useEffect(() => { setReviewed(Boolean(alert?.reviewed_at)); setError(""); setEvidence(null); }, [alert?.alert_id, alert?.reviewed_at]);
  useEffect(() => { if (!evidence) return; const timer = window.setTimeout(() => setEvidence(null), Math.max(0, evidence.expires - Date.now())); return () => window.clearTimeout(timer); }, [evidence]);
  if (!alert) {
    return <div className="alert-panel alert-panel--empty"><span className="status-dot" aria-hidden="true" />No active alert.</div>;
  }

  const mapsUrl = `https://www.google.com/maps?q=${alert.location.lat},${alert.location.lon}`;

  const handleReview = async () => { if (!onEscalate) return; setBusy(true); setError(""); try { await onEscalate(alert.alert_id); setReviewed(true); } catch (failure) { setError(failure instanceof Error ? failure.message : "Review could not be saved. Try again."); } finally { setBusy(false); } };
  const loadEvidence = async () => { if (!onEvidence) return; setBusy(true); setError(""); try { const result = await onEvidence(alert.alert_id); if (!/^https?:\/\//i.test(result.url)) throw new Error("Evidence URL unavailable."); setEvidence({url: result.url, expires: Date.now() + result.expires_in * 1000}); } catch { setError("Evidence could not be loaded. Check station access and try again."); } finally { setBusy(false); } };

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
      {alert.thermal_clip_ref && onEvidence && <p>{evidence ? <a href={evidence.url} target="_blank" rel="noreferrer">Open thermal evidence (temporary link)</a> : <button className="button-secondary" disabled={busy} onClick={() => void loadEvidence()}>Review thermal evidence</button>}</p>}
      {alert.detection_mode === "operator-assist" && (
        <p className="alert-panel__operator-assist">
          The model highlighted a candidate distress signature. A human operator must confirm
          before taking action.
        </p>
      )}
      {onEscalate && <button type="button" className="alert-panel__dispatch" disabled={busy || reviewed} onClick={() => void handleReview()}>
        {reviewed ? "Reviewed" : busy ? "Saving review…" : "Mark reviewed"}
      </button>}
      <p className="field-help">{alert.source === "simulated" ? "Simulation reviews last for this session. " : ""}This records operator review only. No emergency services are contacted.</p>
      {error && <p role="alert" className="form-error">{error}</p>}
    </div>
  );
}
