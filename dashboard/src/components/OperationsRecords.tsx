import { Link } from "react-router-dom";
import type { LakeAlert, LakeDataScope } from "../lib/operationsData";

export function RecordFilters({ lakes, lake, source, setLake, setSource }: {
  lakes: LakeDataScope[]; lake: string; source: string; setLake: (value: string) => void; setSource: (value: string) => void;
}) {
  return <div className="record-filters"><label>Lake<select value={lake} onChange={(event) => setLake(event.target.value)}><option value="">All assigned lakes</option>{lakes.map((item) => <option key={item.lakeId} value={item.lakeId}>{item.name}</option>)}</select></label><label>Source<select value={source} onChange={(event) => setSource(event.target.value)}><option value="">Real and simulated</option><option value="real">Real</option><option value="simulated">Simulated</option></select></label></div>;
}

export function LakeDataCoverage({ lakes }: { lakes: LakeDataScope[] }) {
  return <section className="touch-panel" aria-label="Lake data coverage"><h2>Lake data coverage</h2>{!lakes.length ? <p>No lakes are assigned to this account.</p> : <ul className="coverage-lakes">{lakes.map((lake) => <li key={lake.lakeId}><div><strong>{lake.name}</strong><p>{lake.available ? "Current records available" : "Current records unavailable"}</p></div><Link to={`/lakes/${lake.lakeId}`}>Open lake</Link></li>)}</ul>}<p className="field-help">Record availability does not confirm patrol coverage or current lake conditions.</p></section>;
}

export function IncidentTable({ alerts }: { alerts: LakeAlert[] }) {
  return <div className="incident-table-wrap" tabIndex={0}><table className="incident-table" aria-label="Incident records"><thead><tr><th>Recorded</th><th>Lake</th><th>Detection</th><th>Source</th><th>Review</th></tr></thead><tbody>{alerts.map((alert) => <tr key={`${alert.lakeId}-${alert.alert_id}`}><td>{new Date(alert.created_at).toLocaleString()}</td><td><Link to={`/lakes/${alert.lakeId}`}>{alert.lakeName}</Link></td><td>{alert.detection_mode}</td><td>{alert.source === "simulated" ? "SIMULATED" : "REAL"}</td><td>{alert.review_decision ? {confirmed:'Confirmed by operator',dismissed:'Dismissed',ended:'Investigation ended'}[alert.review_decision] : 'Needs operator review'}</td></tr>)}</tbody></table></div>;
}
