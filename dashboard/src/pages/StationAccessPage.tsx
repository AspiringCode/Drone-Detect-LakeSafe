import { FormEvent, useEffect, useState } from "react";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";
import { Link } from "react-router-dom";
import { AccountNavigation, AccountStations } from "../components/AccountNavigation";

export function StationAccessPage() {
  const principal = useOptionalPrincipal()?.principal;
  const [notice, setNotice] = useState(""); const [error, setError] = useState(""); const [stations, setStations] = useState<Array<{ station_id: string; name: string }>>([]);
  const verified = principal?.account_class === "officer" && principal.verification_status === "verified" && principal.aal === "aal2";
  const [pending, setPending] = useState<Array<{ id: string; name: string; status: string; kind: string }>>([]);
  const [requestsLoading, setRequestsLoading] = useState(false);
  const [requestsError, setRequestsError] = useState("");
  const [requestAttempt, setRequestAttempt] = useState(0);
  useEffect(() => {
    if (!verified) return;
    let current = true;
    setRequestsLoading(true); setRequestsError("");
    void Promise.all([
      apiRequest<{ requests: Array<{ station_request_id: string; requested_name: string; status: string }> }>("/api/station-requests/mine", {}, supabase),
      apiRequest<{ requests: Array<{ station_join_request_id: string; station_name: string; status: string }> }>("/api/station-join-requests/mine", {}, supabase),
    ]).then(([station, joins]) => { if (current) setPending([
      ...(station.requests ?? []).map((item) => ({ id: item.station_request_id, name: item.requested_name, status: item.status, kind: "New station" })),
      ...(joins.requests ?? []).map((item) => ({ id: item.station_join_request_id, name: item.station_name, status: item.status, kind: "Membership" })),
    ]); }).catch(() => { if (current) setRequestsError("Request status could not be loaded."); })
      .finally(() => { if (current) setRequestsLoading(false); });
    return () => { current = false; };
  }, [verified, requestAttempt]);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  async function submitRequest(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (busy) return; setBusy(true); setError(""); setNotice(""); const form = new FormData(event.currentTarget); try { await apiRequest("/api/station-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), address: form.get("address") }) }, supabase); setNotice("Station request submitted for LakeSafe review."); setRequestAttempt((value) => value + 1); } catch (value) { setError(value instanceof Error ? value.message : "Request failed."); } finally { setBusy(false); } }
  async function search(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (busy) return; setBusy(true); setError(""); setNotice(""); try { const query = encodeURIComponent(String(new FormData(event.currentTarget).get("query") ?? "")); const result = await apiRequest<{ stations: Array<{ station_id: string; name: string }> }>(`/api/stations?query=${query}`, {}, supabase); setStations(result.stations); setSearched(true); } catch (value) { setError(value instanceof Error ? value.message : "Station search failed."); } finally { setBusy(false); } }
  async function join(stationId: string) { if (busy) return; setBusy(true); setError(""); setNotice(""); try { await apiRequest(`/api/stations/${stationId}/join-requests`, { method: "POST" }, supabase); setNotice("Join request submitted to the station administrators."); setRequestAttempt((value) => value + 1); } catch (value) { setError(value instanceof Error ? value.message : "Join request failed."); } finally { setBusy(false); } }
  return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><header className="page-heading"><h1>Your stations</h1><p>View your memberships and station access.</p></header><AccountNavigation active="stations"/><AccountStations/>{!verified ? <section className="touch-panel"><h2>{principal?.judge_demo_access ? "Assigned demo stations" : "Before joining another station"}</h2><p>{principal?.judge_demo_access ? "This demonstration account uses its assigned stations. Open a station above or return to your lakes." : "Joining a station requires current affiliation verification and an authenticated second factor."}</p>{!principal?.judge_demo_access && <Link to={principal?.verification_status === "verified" ? "/verify-2fa" : "/verify-affiliation"}>Review access requirements</Link>}<p><Link to="/lakes">Back to lakes</Link></p></section> : <div className="workflow-grid"><section className="workflow-card"><h2>Find an existing station</h2><form onSubmit={search}><label>Station name or city<input name="query" required /></label><button className="button-secondary" disabled={busy}>{busy ? "Working…" : "Search stations"}</button></form>{stations.length ? <ul className="station-results">{stations.map((station) => <li key={station.station_id}><span>{station.name}</span><button type="button" className="button-secondary" disabled={busy} onClick={() => void join(station.station_id)}>Request to join</button></li>)}</ul> : <p className="field-help">{searched ? "No discoverable stations match your search. Try another station name or city." : "Search returns publicly discoverable station names only."}</p>}</section><section className="workflow-card"><h2>Request a new station</h2><form onSubmit={submitRequest}><label>Station name<input name="name" required maxLength={160}/></label><label>Station address<input name="address" required maxLength={500}/></label><button disabled={busy}>{busy ? "Working…" : "Send for review"}</button></form></section></div>}{verified && <section className="touch-panel"><h2>Your access requests</h2>{requestsLoading ? <p role="status">Loading request status…</p> : requestsError ? <div role="alert"><p>{requestsError}</p><button type="button" className="button-secondary" onClick={() => setRequestAttempt((value) => value + 1)}>Retry request status</button></div> : pending.length ? <ul className="coverage-lakes">{pending.map((item) => <li key={item.id}><div><strong>{item.name}</strong><p>{item.kind} · {item.status.replace(/_/g, " ")}</p></div></li>)}</ul> : <p>No access requests submitted.</p>}</section>}{notice && <p role="status" className="form-success">{notice}</p>}{error && <p role="alert" className="form-error">{error}</p>}</section></main>;
}
