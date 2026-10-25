import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { useOperationsRecords } from "../hooks/useOperationsRecords";
import { IncidentTable, LakeDataCoverage, RecordFilters } from "../components/OperationsRecords";
import { supabase, type SupabaseLike } from "../lib/supabase";

import "./website-touchups.css";

export function ReportsPage({ client = supabase, fetcher = fetch }: { client?: SupabaseLike; fetcher?: typeof fetch }) {
  const { alerts, lakes, loading, failed, checkedAt, retry } = useOperationsRecords(client, fetcher);
  const [lake, setLake] = useState("");
  const [source, setSource] = useState("");
  const filtered = alerts.filter((alert) => (!lake || alert.lakeId === lake) && (!source || alert.source === source));

  const summary = useMemo(() => {
    const timed = alerts.filter((alert) => alert.latency_ms !== null);
    return {
      total: alerts.length,
      confirmed: alerts.filter((alert) => alert.confirmed).length,
      simulated: alerts.filter((alert) => alert.source === "simulated").length,
      averageLatency: timed.length ? `${Math.round(timed.reduce((sum, alert) => sum + (alert.latency_ms ?? 0), 0) / timed.length)} ms` : "—",
    };
  }, [alerts]);

  return (
    <main className="app-page data-page">
      <AppHeader active="reports" client={client} />
      <section className="data-shell reports-touchup">
        <header className="page-heading touch-heading"><div>
          <h1>Operational reports</h1>
          <p>Current available records, not a historical reporting period.</p></div><div className="fleet-refresh"><button className="button-secondary" disabled={loading} onClick={retry}>Refresh reports</button><Link to="/alerts">View current alerts</Link></div>
        </header>
        {loading && <p className="panel-empty" aria-live="polite">Calculating reports…</p>}
        {failed && !loading && <div className="touch-error" role="alert"><p>Could not calculate operational reports.</p><button className="button-secondary" onClick={retry}>Retry</button></div>}
        {!loading && !failed && <>
          <p className="field-help">Checked {checkedAt}. Summary covers all available records below; filters apply to the incident list.</p>
          <section className="report-grid" aria-label="Alert report summary">
            <article className="report-metric"><span className="report-metric__value">{summary.total}</span><h2>Total alerts</h2><p>Available current records</p></article>
            <article className="report-metric"><span className="report-metric__value">{summary.confirmed}</span><h2>Confirmed detections</h2><p>Confirmed by a second drone</p></article>
            <article className="report-metric"><span className="report-metric__value">{summary.averageLatency}</span><h2>Average detection latency</h2><p>Recorded timing, not response duration</p></article>
            <article className="report-metric"><span className="report-metric__value">{summary.simulated}</span><h2>Simulated alerts</h2><p>Clearly labeled demo activity</p></article>
          </section>
          <section className="touch-panel"><h2>Incident records</h2><RecordFilters lakes={lakes} lake={lake} source={source} setLake={setLake} setSource={setSource}/>{filtered.length ? <IncidentTable alerts={filtered}/> : <div className="records-empty"><h3>{alerts.length ? "No records match these filters." : "No incident records available."}</h3><p>Records will appear here when detections are available for your assigned lakes.</p></div>}</section>
          <LakeDataCoverage lakes={lakes}/>
        </>}
      </section>
    </main>
  );
}
