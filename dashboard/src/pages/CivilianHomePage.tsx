import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PublicAlertCard } from "../components/PublicAlertCard";
import { PublicLakeMap } from "../components/PublicLakeMap";
import { PublicPatrolSummary } from "../components/PublicPatrolSummary";
import { loadPublicAlerts, loadPublicLakes, loadPublicPatrolPresence, type PublicAlert, type PublicFetcher, type PublicLake, type PublicPatrolPresence } from "../lib/publicData";

export function CivilianHomePage({ fetcher = fetch }: { fetcher?: PublicFetcher }) {
  const [lakes, setLakes] = useState<PublicLake[]>([]);
  const [alerts, setAlerts] = useState<PublicAlert[]>([]);
  const [presence, setPresence] = useState<PublicPatrolPresence[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { void (async () => { try { const available = await loadPublicLakes(fetcher); setLakes(available); if (available[0]) { const [nextAlerts, nextPresence] = await Promise.all([loadPublicAlerts(available[0].lake_id, fetcher), loadPublicPatrolPresence(available[0].lake_id, fetcher)]); setAlerts(nextAlerts); setPresence(nextPresence); } } catch (cause) { setError(cause instanceof Error ? cause.message : "Public lake information is temporarily unavailable."); } })(); }, [fetcher]);
  const lake = lakes[0];
  return <main className="civilian-page">
    <header className="civilian-header"><Link className="app-brand" to="/"><span className="app-brand__name">LakeSafe</span><span className="app-brand__mark" /></Link><nav><Link to="/login">Sign in</Link><Link className="button-link" to="/signup">Create account</Link></nav></header>
    <section className="civilian-hero"><p className="kicker">Lake safety, clearly shared</p><h1>Know what’s happening around your lake.</h1><p>Community updates describe general patrol activity and safety notices without exposing operational information.</p></section>
    {error && <p className="form-error civilian-content" role="alert">{error}</p>}
    {lake && <section className="civilian-content civilian-grid"><PublicLakeMap lake={lake} /><div className="civilian-side"><PublicPatrolSummary presence={presence} /><section className="public-alerts"><p className="panel-eyebrow">Area notices</p><h2>Public alerts</h2>{alerts.length ? alerts.map((alert) => <PublicAlertCard key={`${alert.category}-${alert.published_at}`} alert={alert} />) : <p>No current public safety notices.</p>}</section></div></section>}
  </main>;
}
