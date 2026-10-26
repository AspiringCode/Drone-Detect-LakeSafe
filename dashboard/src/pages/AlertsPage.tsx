import { useState } from "react";
import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { useOperationsRecords } from "../hooks/useOperationsRecords";
import { LakeDataCoverage, RecordFilters } from "../components/OperationsRecords";
import { supabase, type SupabaseLike } from "../lib/supabase";

import "./website-touchups.css";

export function AlertsPage({ client = supabase, fetcher = fetch }: { client?: SupabaseLike; fetcher?: typeof fetch }) {
  const { alerts, lakes, loading, failed, checkedAt, retry } = useOperationsRecords(client, fetcher);
  const [lake, setLake] = useState("");
  const [source, setSource] = useState("");
  const filtered = alerts.filter((alert) => (!lake || alert.lakeId === lake) && (!source || alert.source === source));

  return (
    <main className="app-page data-page">
      <AppHeader active="alerts" client={client} />
      <section className="data-shell">
        <header className="page-heading">
          <h1>Active alerts</h1>
          <p>Review available detections from your assigned lakes.</p>
        </header>
        {loading && <p className="panel-empty" aria-live="polite">Loading alerts…</p>}
        {failed && !loading && <div className="touch-error" role="alert"><p>Could not load operational alerts.</p><button className="button-secondary" onClick={retry}>Retry</button></div>}
        {!loading && !failed && <><p className="field-help">Checked {checkedAt}. This page shows a snapshot; refresh to check for new detections.</p><button className="button-secondary" onClick={retry}>Refresh alerts</button><RecordFilters lakes={lakes} lake={lake} source={source} setLake={setLake} setSource={setSource}/>
        {!filtered.length && <section className="data-empty"><div><h2>{alerts.length ? "No records match these filters." : "No alerts in the available records"}</h2><p>Check lake data coverage below before relying on an empty list.</p></div></section>}
        {!!filtered.length && (
          <div className="alert-list">
            {filtered.map((alert) => (
              <article className="alert-record" key={`${alert.lakeId}-${alert.alert_id}`}>
                <div className="alert-record__status"><span className={alert.confirmed ? "record-badge record-badge--confirmed" : "record-badge"}>{alert.review_decision ? {confirmed:'Confirmed by operator',dismissed:'Dismissed',ended:'Investigation ended'}[alert.review_decision] : alert.confirmed ? 'Corroborated · needs review' : 'Needs review'}</span><span>{alert.source}</span></div>
                <div><h2>{alert.detection_mode} detection</h2><p className="field-help">{alert.lakeName}</p></div>
                <dl><div><dt>Drone</dt><dd>{alert.drone_id}</dd></div><div><dt>Latency</dt><dd>{alert.latency_ms === null ? "—" : `${alert.latency_ms} ms`}</dd></div><div><dt>Recorded</dt><dd>{new Date(alert.created_at).toLocaleString()}</dd></div></dl>
                <Link to={`/lakes/${alert.lakeId}?alert=${encodeURIComponent(alert.alert_id)}`}>Review alert <span aria-hidden="true">→</span></Link>
              </article>
            ))}
          </div>
        )}<LakeDataCoverage lakes={lakes}/></>}
      </section>
    </main>
  );
}
