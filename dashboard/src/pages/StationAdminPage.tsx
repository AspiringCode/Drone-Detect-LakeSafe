import { FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";
import { StationMemberTable } from "../components/StationMemberTable";
import { StationRequestQueue } from "../components/StationRequestQueue";

export function StationAdminPage() {
  const { stationId = "" } = useParams(); const principal = useOptionalPrincipal()?.principal;
  const membership = principal?.memberships.find((item) => item.station_id === stationId && item.status === "active"); const allowed = membership?.capabilities.includes("member.manage");
  const [message, setMessage] = useState(""); const [error, setError] = useState("");
  async function invite(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setError(""); try { const email = new FormData(event.currentTarget).get("email"); const result = await apiRequest<{ token: string }>(`/api/stations/${stationId}/invitations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) }, supabase); setMessage(`Invitation created. Share this one-time link securely: ${window.location.origin}/invitations/accept?token=${encodeURIComponent(result.token)}`); } catch (value) { setError(value instanceof Error ? value.message : "Invitation could not be created."); } }
  if (!allowed || !membership) return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><h1>Station administration is unavailable</h1><p>You need the station administrator capability for this station.</p></section></main>;
  return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><header className="page-heading"><p className="kicker">Station administration</p><h1>{membership.station_name}</h1><p>Manage invitations and membership decisions for this station.</p></header><div className="workflow-grid"><StationMemberTable membership={membership}/><StationRequestQueue/><section className="workflow-card"><h2>Invite an officer</h2><form onSubmit={invite}><label>Verified email<input type="email" name="email" required/></label><button>Create invitation</button></form>{message && <p className="field-help" role="status">{message}</p>}{error && <p className="form-error" role="alert">{error}</p>}</section><section className="workflow-card"><h2>Add a lake</h2><p>New lakes are set up for this station only.</p><Link className="button-link" to={`/stations/${stationId}/lakes/new`}>Add lake</Link></section></div></section></main>;
}
