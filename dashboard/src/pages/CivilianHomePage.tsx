import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { PublicAlertCard } from "../components/PublicAlertCard";
import { PublicLakeMap } from "../components/PublicLakeMap";
import { PublicPatrolSummary } from "../components/PublicPatrolSummary";
import { loadPublicAlerts, loadPublicLakes, loadPublicPatrolPresence, type PublicAlert, type PublicFetcher, type PublicLake, type PublicPatrolPresence } from "../lib/publicData";
import "./website-touchups.css";

export function CivilianHomePage({ fetcher = fetch }: { fetcher?: PublicFetcher }) {
  const principal = useOptionalPrincipal()?.principal;
  const [lakes, setLakes] = useState<PublicLake[]>([]);
  const [selectedLakeId, setSelectedLakeId] = useState("");
  const [alerts, setAlerts] = useState<PublicAlert[]>([]);
  const [presence, setPresence] = useState<PublicPatrolPresence[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void (async () => {
      try {
        const available = await loadPublicLakes(fetcher);
        if (!active) return;
        setLakes(available);
        const selected = available.find((item) => item.lake_id === selectedLakeId) ?? available[0];
        const [nextAlerts, nextPresence] = selected
          ? await Promise.all([loadPublicAlerts(selected.lake_id, fetcher), loadPublicPatrolPresence(selected.lake_id, fetcher)])
          : [[], []];
        if (!active) return;
        setAlerts(nextAlerts);
        setPresence(nextPresence);
      } catch {
        if (active) setError("Public lake information is temporarily unavailable. Please try again shortly.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [fetcher, attempt, selectedLakeId]);
  const lake = lakes.find((item) => item.lake_id === selectedLakeId) ?? lakes[0];
  return <main className="civilian-page">
    <header className="civilian-header"><Link className="app-brand" to={principal ? "/lakes" : "/"}><span className="app-brand__name">LakeSafe</span><span className="app-brand__wave" aria-hidden="true">🌊</span></Link><nav>{principal ? <Link to="/profile">Profile settings</Link> : <><Link to="/login">Sign in</Link><Link className="button-link" to="/signup">Create account</Link></>}</nav></header>
    <section className="civilian-hero"><h1>Your lake, at a glance</h1><p>Safety notices and published patrol activity for your next visit.</p></section>
    {lakes.length > 0 && <section className="civilian-content civilian-lake-selector"><div className="public-lake-choices" role="group" aria-label="Choose a lake">{lakes.map((item) => <button type="button" className="button-secondary" aria-pressed={lake?.lake_id === item.lake_id} key={item.lake_id} onClick={() => { if (item.lake_id !== lake?.lake_id) { setLoading(true); setError(""); setSelectedLakeId(item.lake_id); } }}>{item.name}</button>)}</div></section>}
    {(loading || error || !lake) && <section className="civilian-content" aria-label="Lake updates" aria-busy={loading}>
      {loading && <div className="lake-state" role="status"><h2>Loading lake updates…</h2><p>Checking the latest published lake information.</p></div>}
      {!loading && error && <div className="lake-state lake-state--unavailable" role="alert"><div><h2>Lake updates are unavailable</h2><p>{error}</p></div><button className="button-secondary" onClick={() => setAttempt((value) => value + 1)}>Retry</button></div>}
      {!loading && !error && !lake && <div className="lake-state"><h2>No lake updates published yet</h2><p>Public patrol activity and area notices will appear here when available.</p></div>}
    </section>}
    {!loading && !error && lake && <section className="civilian-content civilian-grid"><PublicLakeMap lake={lake} /><div className="civilian-side"><section className="public-alerts"><h2>Public alerts</h2>{alerts.length ? alerts.map((alert) => <PublicAlertCard key={`${alert.category}-${alert.published_at}`} alert={alert} />) : <p>No current public safety notices.</p>}</section><PublicPatrolSummary presence={presence} /><details className="public-how"><summary>How LakeSafe works</summary><p>Choose a lake to read notices and published patrol updates. You can browse this information without an account. Operators sign in to manage their assigned lakes and drones.</p></details><p className="field-help">Visiting today? Check posted signs and local guidance.</p></div></section>}
  </main>;
}
