import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";

export function InvitationAcceptPage() {
  const [params] = useSearchParams(); const navigate = useNavigate(); const { refresh } = useOptionalPrincipal() ?? { refresh: async () => undefined };
  const token = params.get("token") ?? ""; const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function accept() { if (!token) return setError("This invitation link is incomplete."); setBusy(true); setError(""); try { const result = await apiRequest<{ station_id: string }>("/api/invitations/accept", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) }, supabase); await refresh(); navigate(`/stations/${result.station_id}/admin`); } catch (value) { setError(value instanceof Error ? value.message : "This invitation is unavailable."); } finally { setBusy(false); } }
  return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><section className="workflow-card"><p className="kicker">Station invitation</p><h1>Join a LakeSafe station</h1><p>This single-use invitation is checked against your signed-in, verified email address.</p><button type="button" onClick={accept} disabled={busy || !token}>{busy ? "Accepting…" : "Accept invitation"}</button>{error && <p className="form-error" role="alert">{error}</p>}</section></section></main>;
}
