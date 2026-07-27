import { FormEvent, useState } from "react";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";

export function StationAccessPage() {
  const principal = useOptionalPrincipal()?.principal;
  const [notice, setNotice] = useState(""); const [error, setError] = useState("");
  const verified = principal?.account_class === "officer" && principal.verification_status === "verified" && principal.aal === "aal2";
  async function submitRequest(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setError(""); const form = new FormData(event.currentTarget); try { await apiRequest("/api/station-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), address: form.get("address") }) }, supabase); setNotice("Station request submitted for LakeSafe review."); } catch (value) { setError(value instanceof Error ? value.message : "Request failed."); } }
  if (!verified) return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><header className="page-heading"><p className="kicker">Station access</p><h1>Verify before joining a station</h1><p>Station membership is available to current, MFA-protected verified officers.</p></header></section></main>;
  return <main className="app-page"><AppHeader active="profile"/><section className="workflow-shell"><header className="page-heading"><p className="kicker">Station access</p><h1>Find your station</h1><p>Accept an invitation, request to join an existing station, or request a new station.</p></header><div className="workflow-grid"><section className="workflow-card"><h2>Accept an invitation</h2><p>Use the single-use link sent to your verified email address.</p></section><section className="workflow-card"><h2>Request a new station</h2><form onSubmit={submitRequest}><label>Station name<input name="name" required maxLength={160}/></label><label>Station address<input name="address" required maxLength={500}/></label><button>Send for review</button></form>{notice && <p role="status" className="form-success">{notice}</p>}{error && <p role="alert" className="form-error">{error}</p>}</section></div></section></main>;
}
