import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { loadOperationsAlerts, type LakeAlert } from "../lib/operationsData";
import { supabase, type SupabaseLike } from "../lib/supabase";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function AlertsPage({ client = supabase, fetcher = fetch }: { client?: SupabaseLike; fetcher?: typeof fetch }) {
  const [alerts, setAlerts] = useState<LakeAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    void loadOperationsAlerts(client, fetcher, API)
      .then((nextAlerts) => { if (current) setAlerts(nextAlerts); })
      .catch(() => { if (current) setError("Could not load operational alerts."); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [client, fetcher]);

  return (
    <main className="app-page data-page">
      <AppHeader active="alerts" client={client} />
      <section className="data-shell">
        <header className="page-heading">
          <p className="kicker">Response center</p>
          <h1>Active alerts</h1>
          <p>Lake-scoped detections from the currently connected operator runtimes.</p>
        </header>
        {loading && <p className="panel-empty" aria-live="polite">Loading alerts…</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {!loading && !error && !alerts.length && <section className="data-empty"><span className="status-dot" aria-hidden="true" /><div><h2>No active alerts</h2><p>The connected lake runtimes have not reported an alert.</p></div></section>}
        {!!alerts.length && (
          <div className="alert-list">
            {alerts.map((alert) => (
              <article className="alert-record" key={`${alert.lakeId}-${alert.alert_id}`}>
                <div className="alert-record__status"><span className={alert.confirmed ? "record-badge record-badge--confirmed" : "record-badge"}>{alert.confirmed ? "Confirmed" : "Needs review"}</span><span>{alert.source}</span></div>
                <div><p className="panel-eyebrow">{alert.lakeName}</p><h2>{alert.detection_mode} detection</h2></div>
                <dl><div><dt>Drone</dt><dd>{alert.drone_id}</dd></div><div><dt>Latency</dt><dd>{alert.latency_ms === null ? "—" : `${alert.latency_ms} ms`}</dd></div><div><dt>Recorded</dt><dd>{new Date(alert.created_at).toLocaleString()}</dd></div></dl>
                <Link to={`/lakes/${alert.lakeId}`}>Open operations <span aria-hidden="true">→</span></Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
