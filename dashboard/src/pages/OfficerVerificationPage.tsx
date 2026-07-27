import { useState } from "react";
import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";

export function OfficerVerificationPage() {
  const principal = useOptionalPrincipal()?.principal;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function begin() {
    setBusy(true); setError("");
    try { window.location.assign((await apiRequest<{ authorization_url: string }>("/api/verifications/idme/start", { method: "POST" }, supabase)).authorization_url); }
    catch (value) { setError(value instanceof Error ? value.message : "Verification could not be started."); setBusy(false); }
  }
  const state = principal?.verification_status ?? "not_started";
  return <main className="app-page"><AppHeader active="profile" /><section className="workflow-shell"><header className="page-heading"><p className="kicker">Account verification</p><h1>Verify your affiliation</h1><p>Verification confirms U.S. law-enforcement affiliation. It does not grant station access by itself.</p></header><section className="workflow-card"><p className="panel-eyebrow">Current status</p><h2 className={`status-label status-label--${state}`}>{state.replace(/_/g, " ")}</h2>{["pending", "rejected", "expired", "revoked"].includes(state) && <p className="field-help">Your request is {state}. You can retry when eligible.</p>}<button type="button" onClick={begin} disabled={busy}>{busy ? "Opening ID.me…" : state === "verified" ? "Verify again" : "Continue with ID.me"}</button>{error && <p className="form-error" role="alert">{error}</p>}<details><summary>Use manual review instead</summary><p>Manual evidence is a fallback. Accepted files are agency ID, employment letter, or equivalent current-employment evidence. Files are retained for at most 30 days after a decision.</p><Link to="/profile">Return to profile settings</Link></details></section></section></main>;
}
