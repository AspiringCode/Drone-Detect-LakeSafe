import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOrientation } from "../lib/useOrientation";

export function VerifyOtpPage({ client = supabase }: { client?: SupabaseLike }) {
  const ref = useOrientation(); const navigate = useNavigate(); const [factorId, setFactorId] = useState(""); const [error, setError] = useState("");
  useEffect(() => { void client.auth.mfa.listFactors().then((result: { data?: { totp?: Array<{ id: string }> }; error?: { message: string } | null }) => { const { data, error: e } = result; if (e || !data?.totp?.[0]) setError(e?.message ?? "No TOTP factor is enrolled for this account."); else setFactorId(data.totp[0].id); }); }, [client]);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!factorId) return; const code = String(new FormData(event.currentTarget).get("code")); const { data: challenge, error: cError } = await client.auth.mfa.challenge({ factorId }); if (cError) return setError(cError.message); const { error: vError } = await client.auth.mfa.verify({ factorId, challengeId: challenge.id, code }); if (vError) return setError(vError.message); navigate("/lakes"); }
  return <main className="auth-page"><section ref={ref} className="auth-card"><p className="kicker">Second factor</p><h1>Verify TOTP code</h1><p>Enter the current six-digit code from your authenticator app.</p><form onSubmit={submit}><label>Authentication code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required /></label>{error && <p className="form-error" role="alert">{error}</p>}<button disabled={!factorId}>Verify code</button></form><p><Link to="/login">Back to sign in</Link></p></section></main>;
}
