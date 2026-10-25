import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { Polygon, MultiPolygon } from "geojson";
import { AppHeader } from "../components/AppHeader";
import { ShorelinePreview } from "../components/ShorelinePreview";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { useOptionalActiveStation } from "../hooks/useActiveStation";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";
import "./website-touchups.css";

type Candidate = { candidate_id: number; name: string; shoreline: Polygon | MultiPolygon; source: string };
export function AddLakePage() {
  const { stationId = "" } = useParams();
  const navigate = useNavigate();
  const context = useOptionalPrincipal();
  const active = useOptionalActiveStation();
  const admins = context?.principal?.memberships.filter(item => item.status === "active" && item.capabilities.includes("lake.create")) ?? [];
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [searched, setSearched] = useState(false);
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [destination, setDestination] = useState(stationId);
  const [stationName, setStationName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<{ lake_id: string; station_id: string } | null>(null);
  useEffect(() => {
    if (!admins.some(item => item.station_id === destination)) setDestination(admins.find(item => item.station_id === active?.station?.station_id)?.station_id ?? admins[0]?.station_id ?? "");
  }, [context?.principal, destination, active?.station?.station_id]);
  useEffect(() => {
    if (created && admins.some(item => item.station_id === created.station_id)) {
      active?.select(created.station_id);
      navigate(`/lakes/${created.lake_id}`, { replace: true });
    }
  }, [created, context?.principal, navigate]);
  const previewFailed = useCallback(() => { setSelected(null); setError("The shoreline could not be drawn. Select the lake again before continuing."); }, []);
  async function search(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(""); setSelected(null); setCandidates([]); setSearched(false);
    try {
      const result = await apiRequest<{ candidates: Candidate[] }>(`/api/lake-search?query=${encodeURIComponent(query.trim())}`, {}, supabase);
      setCandidates(result.candidates); setSearched(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Lake search is unavailable. Try again."); }
    finally { setBusy(false); }
  }
  async function create(event: FormEvent) {
    event.preventDefault(); if (busy || !selected || created) return;
    setBusy(true); setError("");
    try {
      const result = await apiRequest<{ lake_id: string; station_id: string }>("/api/lake-setups", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: selected.candidate_id, ...(mode === "new" ? { new_station_name: stationName.trim() } : { station_id: destination }) }),
      }, supabase);
      setCreated(result);
      try { await context?.refresh(); }
      catch { setError("Your lake was created, but account access could not refresh. Reload the page to see it in your managed lakes."); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Lake could not be added. Try again."); }
    finally { setBusy(false); }
  }
  if (!admins.length) return <main className="app-page"><AppHeader active="lakes"/><section className="workflow-shell"><h1>Add lake is unavailable</h1><p>An active station administrator can add lakes and create a lake station.</p><Link to="/station-access">Review station access</Link></section></main>;
  return <main className="app-page"><AppHeader active="lakes"/><section className="workflow-shell touch-shell">
    <header className="page-heading touch-heading"><div><h1>Add a lake</h1><p>Find your lake, check its shoreline, then choose its station.</p></div><Link to="/lakes">Back to lakes</Link></header>
    <section className="touch-panel"><h2>Find your lake</h2><p>Search by name. Shoreline search currently covers King County, Washington.</p>
      <form onSubmit={event => void search(event)}><label>Lake name<input name="name" value={query} minLength={2} maxLength={100} required disabled={busy || Boolean(created)} placeholder="e.g. Lake Washington" onChange={event => { setQuery(event.target.value); setSelected(null); setCandidates([]); setSearched(false); }}/></label><button disabled={busy || Boolean(created)}>{busy ? "Working..." : "Search lakes"}</button></form>
      {searched && !candidates.length && <p role="status">No matching shoreline was found. Try another part of the name, or check that the lake is in King County.</p>}
      {!!candidates.length && <fieldset className="lake-search-results" disabled={busy || Boolean(created)}><legend>Select a shoreline to review</legend>{candidates.map(candidate => <label className="choice" key={candidate.candidate_id}><input type="radio" name="candidate" checked={selected?.candidate_id === candidate.candidate_id} onChange={() => { setSelected(candidate); setStationName(`${candidate.name} station`); setError(""); }}/><span><strong>{candidate.name}</strong><span className="field-help"> {candidate.source}</span></span></label>)}</fieldset>}
    </section>
    {selected && <div className="workflow-grid lake-setup-review"><section className="touch-panel"><h2>Review {selected.name}</h2><ShorelinePreview geometry={selected.shoreline} onFailure={previewFailed}/><p className="field-help">Check the shoreline before adding it. Coverage planning starts after creation.</p></section>
      <section className="touch-panel"><h2>Choose a station</h2><form onSubmit={event => void create(event)}><fieldset disabled={busy || Boolean(created)}><legend>Where should this lake belong?</legend><label className="choice"><input type="radio" name="destination" checked={mode === "existing"} onChange={() => setMode("existing")}/>Existing station</label><label className="choice"><input type="radio" name="destination" checked={mode === "new"} onChange={() => setMode("new")}/>New station for this lake</label>
      {mode === "existing" ? <label>Station<select value={destination} onChange={event => setDestination(event.target.value)} required>{admins.map(item => <option key={item.station_id} value={item.station_id}>{item.station_name}</option>)}</select></label> : <><label>New station name<input value={stationName} onChange={event => setStationName(event.target.value)} minLength={2} maxLength={160} required/></label><p className="field-help">You will be the administrator of the new station. Other members must be invited or approved.</p></>}
      <p className="field-help">This creates an operational workspace. It does not publish a public lake page.</p><button disabled={busy || Boolean(created)}>{busy ? "Creating..." : mode === "new" ? "Create station and add lake" : "Add lake to station"}</button></fieldset></form></section></div>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {created && <p role="status">Lake created. Preparing your workspace...</p>}
  </section></main>;
}
