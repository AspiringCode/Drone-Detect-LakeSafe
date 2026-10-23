import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOrientation } from "../lib/useOrientation";
import { apiRequest } from "../lib/apiClient";
import type { Principal } from "../lib/types";

export function LoginPage({ client = supabase, request = apiRequest }: { client?: SupabaseLike; request?: typeof apiRequest }) {
  const navigate = useNavigate(); const ref = useOrientation();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const { data, error: signInError } = await client.auth.signInWithPassword({ email, password });
      if (signInError) return setError(signInError.message);
      const principal = await request<Principal>("/api/me", undefined, client);
      const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel(data.session?.access_token);
      if (assuranceError) throw assuranceError;
      navigate(assurance?.currentLevel === "aal2" || principal.judge_demo_access === true ? "/lakes" : "/verify-2fa");
    } catch {
      setError("Could not check account access. Please try again.");
    }
  }
  return <main className="auth-page"><section ref={ref} className="auth-card"><h1>Operator access</h1><p>Sign in to your lake operations workspace.</p><form onSubmit={submit}><label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button>Sign in</button></form><p>New operator? <Link to="/signup">Create an account</Link></p></section></main>;
}
