import { useState } from "react";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { apiRequest } from "../lib/apiClient";
import { supabase } from "../lib/supabase";
import { AccountNavigation } from "../components/AccountNavigation";

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
  return <main className="app-page"><AppHeader active="profile" /><section className="workflow-shell"><header className="page-heading"><h1>Account access</h1><p>Affiliation verification and station membership are separate.</p></header><AccountNavigation active="access"/><section className="touch-panel"><h2>{principal?.judge_demo_access ? "Demonstration access" : "Affiliation verification"}</h2><p className={`status-label status-label--${state}`}>{state.replace(/_/g, " ")}</p>{principal?.judge_demo_access ? <p>This fictional account has assigned demo access. It does not represent real agency verification.</p> : <>{["pending", "rejected", "expired", "revoked"].includes(state) && <p className="field-help">Your request is {state}. You can retry when eligible.</p>}<p>Verify your U.S. law-enforcement affiliation with ID.me to request operator access.</p><button type="button" onClick={begin} disabled={busy}>{busy ? "Opening ID.me…" : state === "verified" ? "Verify again" : "Continue with ID.me"}</button></>}{error && <p className="form-error" role="alert">{error}</p>}</section></section></main>;
}
