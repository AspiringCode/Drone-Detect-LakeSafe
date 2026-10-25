import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";
import { StationPicker } from "../components/StationPicker";
import { StationMemberTable } from "../components/StationMemberTable";

export function StationAdminPage() {
  const { stationId = "" } = useParams(); const navigate = useNavigate(); const principalContext = useOptionalPrincipal(); const principal = principalContext?.principal;
  const membership = principal?.memberships.find((item) => item.station_id === stationId && item.status === "active"); const allowed = membership?.capabilities.includes("member.manage");
  const [message, setMessage] = useState(""); const [error, setError] = useState(""); const [requests, setRequests] = useState<Array<{ station_join_request_id: string; user_id?: string }>>([]); const [loadingRequests, setLoadingRequests] = useState(false);
  const [busy, setBusy] = useState(false);
  const [requestError, setRequestError] = useState("");
  const [requestAttempt, setRequestAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    setRequests([]); setRequestError(""); setMessage(""); setError("");
    if (allowed) {
      setLoadingRequests(true);
      void apiRequest<{ requests: Array<{station_join_request_id: string; user_id?: string}> }>(`/api/stations/${stationId}/join-requests`, {}, supabase)
        .then(result => { if (!Array.isArray(result.requests)) throw new Error("Membership requests could not be loaded."); if (current) setRequests(result.requests); })
        .catch(() => { if (current) setRequestError("Membership requests could not be loaded."); })
        .finally(() => { if (current) setLoadingRequests(false); });
    }
    return () => { current = false; };
  }, [stationId, allowed, requestAttempt]);
  async function invite(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (busy) return; setBusy(true); setError(""); setMessage(""); try { const email = new FormData(event.currentTarget).get("email"); const result = await apiRequest<{ token: string }>(`/api/stations/${stationId}/invitations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) }, supabase); setMessage(`Invitation created. Share this one-time link securely: ${window.location.origin}/invitations/accept?token=${encodeURIComponent(result.token)}`); } catch (value) { setError(value instanceof Error ? value.message : "Invitation could not be created."); } finally { setBusy(false); } }
  async function decide(requestId: string, decision: "approved" | "rejected") { if (busy) return; setBusy(true); setError(""); setMessage(""); try { await apiRequest(`/api/stations/${stationId}/join-requests/${requestId}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, roles: decision === "approved" ? ["viewer"] : [] }) }, supabase); setMessage(`Request ${decision}.`); setRequestAttempt(value => value + 1); } catch (value) { setError(value instanceof Error ? value.message : "Decision could not be recorded."); } finally { setBusy(false); } }
  if (!allowed || !membership) return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><h1>Station administration is unavailable</h1><p>You need the station administrator capability for this station.</p></section></main>;
  return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><header className="page-heading"><h1>{membership.station_name}</h1><StationPicker page stationId={stationId} capability="member.manage" disabled={busy} onSelect={(id) => navigate(`/stations/${id}/admin`)}/><p>Manage invitations and membership decisions for this station.</p></header><div className="workflow-grid"><StationMemberTable key={stationId} membership={membership} onChanged={principalContext?.refresh}/><section className="workflow-card"><h2>Join requests</h2>{requestError ? <div role="alert"><p className="form-error">{requestError}</p><button className="button-secondary" disabled={loadingRequests} onClick={() => setRequestAttempt(value => value + 1)}>Retry join requests</button></div> : loadingRequests ? <p className="field-help">Loading requests…</p> : requests.length ? <ul className="station-results">{requests.map((request) => <li key={request.station_join_request_id}><span>{request.user_id ?? "Verified officer"}</span><span><button type="button" className="button-secondary" disabled={busy} onClick={() => void decide(request.station_join_request_id, "approved")}>Approve as viewer</button><button type="button" className="button-secondary" disabled={busy} onClick={() => void decide(request.station_join_request_id, "rejected")}>Reject</button></span></li>)}</ul> : <p className="field-help">No membership requests need a decision.</p>}</section><section className="workflow-card"><h2>Invite an officer</h2><form onSubmit={invite}><label>Verified email<input type="email" name="email" required disabled={busy}/></label><button disabled={busy}>{busy ? "Working…" : "Create invitation"}</button></form></section><section className="workflow-card"><h2>Add a lake</h2><p>Add a lake here, or create a separate station for it.</p><Link className="button-link" to={`/stations/${stationId}/lakes/new`}>Add lake</Link></section></div>{message && <p className="field-help" role="status">{message}</p>}{error && <p className="form-error" role="alert">{error}</p>}</section></main>;
}
