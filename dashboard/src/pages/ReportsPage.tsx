import { useEffect, useMemo, useState } from "react";
import { AppHeader } from "../components/AppHeader";
import { loadOperationsAlerts, type LakeAlert } from "../lib/operationsData";
import { supabase, type SupabaseLike } from "../lib/supabase";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function ReportsPage({ client = supabase, fetcher = fetch }: { client?: SupabaseLike; fetcher?: typeof fetch }) {
  const [alerts, setAlerts] = useState<LakeAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    void loadOperationsAlerts(client, fetcher, API)
      .then((nextAlerts) => { if (current) setAlerts(nextAlerts); })
      .catch(() => { if (current) setError("Could not calculate operational reports."); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [client, fetcher]);

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
      <section className="data-shell">
        <header className="page-heading">
          <p className="kicker">Operational record</p>
          <h1>Operational reports</h1>
          <p>Live summaries calculated from the alerts currently available to this account.</p>
        </header>
        {loading && <p className="panel-empty" aria-live="polite">Calculating reports…</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {!loading && !error && (
          <section className="report-grid" aria-label="Alert report summary">
            <article className="report-metric"><span className="report-metric__value">{summary.total}</span><h2>Total alerts</h2><p>Across connected lakes</p></article>
            <article className="report-metric"><span className="report-metric__value">{summary.confirmed}</span><h2>Confirmed responses</h2><p>Operator-confirmed records</p></article>
            <article className="report-metric"><span className="report-metric__value">{summary.averageLatency}</span><h2>Average latency</h2><p>For records with timing data</p></article>
            <article className="report-metric"><span className="report-metric__value">{summary.simulated}</span><h2>Simulated alerts</h2><p>Clearly labeled demo activity</p></article>
          </section>
        )}
      </section>
    </main>
  );
}
