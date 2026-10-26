import { useEffect, useState } from "react";
import type { Alert, AlertDecision } from "../lib/types";
import { SimulatedBadge } from "./SimulatedBadge";

interface AlertPanelProps {
  alert: Alert | null;
  onEscalate?: (alertId: string) => Promise<void> | void;
  apiBaseUrl?: string;
  onEvidence?: (alertId: string) => Promise<{ url: string; expires_in: number }>;
  onDecision?: (alertId: string,decision: AlertDecision) => Promise<void>;
  onRelatedAlert?: (alertId: string)=>void;
}

export function AlertPanel({ alert, onEscalate, onEvidence, onDecision,onRelatedAlert }: AlertPanelProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [decision,setDecision]=useState<AlertDecision | null>(alert?.review_decision ?? null);
  useEffect(()=>{setDecision(alert?.review_decision ?? null);},[alert?.alert_id,alert?.review_decision]);
  const [evidence, setEvidence] = useState<{url: string; expires: number} | null>(null);
  useEffect(() => { setReviewed(Boolean(alert?.reviewed_at)); setError(""); setEvidence(null); }, [alert?.alert_id, alert?.reviewed_at]);
  useEffect(() => { if (!evidence) return; const timer = window.setTimeout(() => setEvidence(null), Math.max(0, evidence.expires - Date.now())); return () => window.clearTimeout(timer); }, [evidence]);
  if (!alert) {
    return <div className="alert-panel alert-panel--empty"><span className="status-dot" aria-hidden="true" />No active alert.</div>;
  }

  const mapsUrl = `https://www.google.com/maps?q=${alert.location.lat},${alert.location.lon}`;
  const investigation=alert.investigation;
  const finding=investigation?.finding;
  const decide=async (value: AlertDecision)=>{if(!onDecision || busy)return;setBusy(true);setError('');try{await onDecision(alert.alert_id,value);setDecision(value);}catch(failure){setError(failure instanceof Error?failure.message:'Decision could not be saved.');}finally{setBusy(false);}};

  const handleReview = async () => { if (!onEscalate) return; setBusy(true); setError(""); try { await onEscalate(alert.alert_id); setReviewed(true); } catch (failure) { setError(failure instanceof Error ? failure.message : "Review could not be saved. Try again."); } finally { setBusy(false); } };
  const loadEvidence = async () => { if (!onEvidence) return; setBusy(true); setError(""); try { const result = await onEvidence(alert.alert_id); if (!/^https?:\/\//i.test(result.url)) throw new Error("Evidence URL unavailable."); setEvidence({url: result.url, expires: Date.now() + result.expires_in * 1000}); } catch { setError("Evidence could not be loaded. Check station access and try again."); } finally { setBusy(false); } };

  return (
    <div className="alert-panel">
      <div className="alert-panel__header">
        <SimulatedBadge source={alert.source} />
        <span className="alert-panel__mode">{alert.detection_mode}</span>
      </div>
      <dl className="alert-observation"><div><dt>Detecting drone</dt><dd>{alert.drone_id}</dd></div><div><dt>Recorded</dt><dd>{new Date(alert.created_at).toLocaleString()}</dd></div>{typeof alert.confidence==='number' && <div><dt>Model score</dt><dd>{Math.round(alert.confidence*100)}%</dd></div>}</dl>
      <p>
        GPS: {alert.location.lat.toFixed(5)}, {alert.location.lon.toFixed(5)}{" "}
        <a href={mapsUrl} target="_blank" rel="noreferrer">
          Open in Maps
        </a>
      </p>
      <section className="investigation-summary" aria-label="Second-drone investigation" aria-live="polite">
        <h3>Second-drone findings</h3>
        {investigation?.confirmer && <p>Investigating drone: <strong>{investigation.confirmer}</strong></p>}
        <p>{finding==='observed' ? (alert.source==='simulated'?'Simulated second-drone detection corroborates the alert.':'Independent second-drone detection corroborates the alert.') : finding==='not_observed' ? 'The second drone did not observe the detection.' : finding==='inconclusive' ? 'The second drone’s finding is inconclusive.' : 'No independent finding yet.'}</p>
        {investigation && <p className="field-help">{{en_route:'Second drone is being sent to investigate.',awaiting_finding:'Awaiting a second-drone observation; arrival alone does not confirm the alert.',finding_received:'Finding received. Review the observation before deciding.',returning:'Return requested. Waiting for original patrol to resume.',returned:'Original patrol resumed.',unavailable:'No second drone is available to investigate.',failed:'Investigation or return needs operator attention.'}[investigation.phase]}</p>}
        {investigation?.detail && <p className="field-help">{investigation.detail}</p>}
        {investigation?.finding_alert_id && onRelatedAlert && <button className="button-secondary" onClick={()=>onRelatedAlert(investigation.finding_alert_id!)}>Open second-drone report</button>}
        {!alert.thermal_clip_ref && <p className="field-help">{alert.source==='simulated'?'This demo uses a simulated finding; no camera clip is recorded.':'No thermal clip was attached. Review available observations or verify conditions before confirming.'}</p>}
      </section>
      {alert.thermal_clip_ref && onEvidence && <p>{evidence ? <a href={evidence.url} target="_blank" rel="noreferrer">Open thermal evidence (temporary link)</a> : <button className="button-secondary" disabled={busy} onClick={() => void loadEvidence()}>Review thermal evidence</button>}</p>}
      {alert.detection_mode === "operator-assist" && (
        <p className="alert-panel__operator-assist">
          The model highlighted a candidate distress signature. A human operator must confirm
          before taking action.
        </p>
      )}
      {onDecision && <div className="alert-decisions">
        {!decision && <><button disabled={busy} onClick={()=>void decide('confirmed')}>Confirm detection</button><button className="button-secondary" disabled={busy} onClick={()=>void decide('dismissed')}>Dismiss and resume patrol</button></>}
        {(!decision || decision==='confirmed') && <button className="button-secondary" disabled={busy} onClick={()=>void decide('ended')}>End investigation and resume patrol</button>}
        {decision && <p role="status"><strong>{{confirmed:'Detection confirmed by operator',dismissed:'Dismissed by operator',ended:'Investigation ended by operator'}[decision]}</strong></p>}
      </div>}
      {!onDecision && onEscalate && <button type="button" className="alert-panel__dispatch" disabled={busy || reviewed} onClick={() => void handleReview()}>
        {reviewed ? "Reviewed" : busy ? "Saving review…" : "Mark reviewed"}
      </button>}
      <p className="field-help">{alert.source === "simulated" ? "Simulation reviews last for this session. " : ""}No emergency services are contacted. Confirming keeps the investigation open; ending or dismissing requests a return to patrol.</p>
      {error && <p role="alert" className="form-error">{error}</p>}
    </div>
  );
}
