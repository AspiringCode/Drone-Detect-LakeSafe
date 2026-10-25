import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { PublicAlertCard } from "../components/PublicAlertCard";
import { PublicLakeMap } from "../components/PublicLakeMap";
import { PublicPatrolSummary } from "../components/PublicPatrolSummary";
import { WaveMark } from "../components/WaveMark";
import { loadPublicAlerts, loadPublicLakes, loadPublicPatrolPresence, type PublicAlert, type PublicFetcher, type PublicLake, type PublicPatrolPresence } from "../lib/publicData";
import "./website-touchups.css";

export function CivilianHomePage({ fetcher = fetch }: { fetcher?: PublicFetcher }) {
  const principal = useOptionalPrincipal()?.principal;
  const [lakes, setLakes] = useState<PublicLake[]>([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedLakeId = searchParams.get("lake") ?? "";
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30000); return () => window.clearInterval(timer); }, []);
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
        setCheckedAt(new Date());
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
    <a className="skip-link" href="#public-content">Skip to main content</a>
    <header className="civilian-header"><Link className="app-brand" to={principal ? "/lakes" : "/"}><span className="app-brand__name">LakeSafe</span><WaveMark /></Link><nav>{principal ? <>{principal.account_class === "officer" && <Link className="button-link" to="/lakes">Return to workspace</Link>}<Link to="/profile">Profile settings</Link></> :<><Link to="/login">Sign in</Link><Link to="/signup">Create account</Link></>}</nav></header>
    <section id="public-content" tabIndex={-1} className="civilian-hero"><h1>Your lake, at a glance</h1><p>Safety notices and published patrol activity for your next visit.</p></section>
    <div className="civilian-content public-freshness"><p className="field-help">{checkedAt ? `Checked at ${checkedAt.toLocaleTimeString()}.` : "Not checked yet."} {checkedAt && now - checkedAt.getTime() > 300000 ? "This view may be out of date. Refresh for current published updates." : "Published updates may lag current conditions."} {lake?.refreshed_at && Number.isFinite(Date.parse(lake.refreshed_at)) && now - Date.parse(lake.refreshed_at) > 900000 && "The latest published lake update is over 15 minutes old."}</p><button className="button-secondary" disabled={loading} onClick={() => setAttempt((value) => value + 1)}>Refresh lake updates</button></div>
    {lakes.length > 0 && <section className="civilian-content civilian-lake-selector"><div className="public-lake-choices" role="group" aria-label="Choose a lake">{lakes.map((item) => <button type="button" className="button-secondary" aria-pressed={lake?.lake_id === item.lake_id} key={item.lake_id} onClick={() => { if (item.lake_id !== lake?.lake_id) { setLoading(true); setError(""); setSearchParams((previous) => { previous.set("lake", item.lake_id); return previous; }); } }}>{item.name}</button>)}</div></section>}
    {(loading || error || !lake) && <section className="civilian-content" aria-label="Lake updates" aria-busy={loading}>
      {loading && <div className="lake-state" role="status"><h2>Loading lake updates…</h2><p>Checking the latest published lake information.</p></div>}
      {!loading && error && <div className="lake-state lake-state--unavailable" role="alert"><div><h2>Lake updates are unavailable</h2><p>{error}</p></div><button className="button-secondary" onClick={() => setAttempt((value) => value + 1)}>Retry</button></div>}
      {!loading && !error && !lake && <div className="lake-state"><h2>No lake updates published yet</h2><p>Public patrol activity and area notices will appear here when available.</p></div>}
    </section>}
    {!loading && !error && lake && <section className="civilian-content civilian-grid"><PublicLakeMap lake={lake} /><div className="civilian-side"><section className="public-alerts"><h2>Public alerts</h2>{alerts.length ? alerts.map((alert) => <PublicAlertCard key={`${alert.category}-${alert.published_at}`} alert={alert} />) : <p>No current public safety notices.</p>}</section><PublicPatrolSummary presence={presence} /><details className="public-how"><summary>How LakeSafe works</summary><p>Choose a lake to read notices and published patrol updates. You can browse this information without an account. Operators sign in to manage their assigned lakes and drones.</p></details><p className="field-help">Visiting today? Check posted signs and local guidance.</p></div></section>}
  </main>;
}
