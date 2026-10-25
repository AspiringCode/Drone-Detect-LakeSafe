import { FormEvent, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authDestination, safeReturnTo } from "../auth/returnTo";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOrientation } from "../lib/useOrientation";
import { apiRequest } from "../lib/apiClient";
import type { Principal } from "../lib/types";

export function LoginPage({ client = supabase, request = apiRequest }: { client?: SupabaseLike; request?: typeof apiRequest }) {
  const [params] = useSearchParams();
  const returnTo = safeReturnTo(params.get("returnTo"));
  const navigate = useNavigate(); const ref = useOrientation();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState("");
  const [busy, setBusy] = useState(false); const pending = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setBusy(true);
    setError("");
    try {
      const { data, error: signInError } = await client.auth.signInWithPassword({ email, password });
      if (signInError) return setError(signInError.message);
      const principal = await request<Principal>("/api/me", undefined, client);
      const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel(data.session?.access_token);
      if (assuranceError) throw assuranceError;
      navigate(assurance?.currentLevel === "aal2" || principal.judge_demo_access === true ? returnTo : authDestination("/verify-2fa", returnTo));
    } catch {
      setError("Could not check account access. Please try again.");
    } finally { pending.current = false; setBusy(false); }
  }
  return <main className="auth-page"><section ref={ref} className="auth-card"><h1>Sign in to LakeSafe</h1><p>Station operators go to their lake workspace; other accounts go to public lake updates.</p><form onSubmit={submit}><label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form><p><Link to={authDestination("/forgot-password", returnTo)}>Forgot password?</Link></p><p>Need station access? <Link to={authDestination("/signup", returnTo)}>Create an account</Link></p><p><Link to="/">Back to public lakes</Link></p></section></main>;
}
