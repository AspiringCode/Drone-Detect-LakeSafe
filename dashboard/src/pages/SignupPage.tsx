import { FormEvent, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authDestination, safeReturnTo } from "../auth/returnTo";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOrientation } from "../lib/useOrientation";

type TotpFactor = { id: string; qrCode: string; secret: string };

export function SignupPage({ client = supabase }: { client?: SupabaseLike }) {
  const ref = useOrientation();
  const [params] = useSearchParams();
  const returnTo = safeReturnTo(params.get("returnTo"));
  const navigate = useNavigate();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [factor, setFactor] = useState<TotpFactor | null>(null);

  const [busy, setBusy] = useState(false); const pending = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true; setBusy(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      const { data, error: signUpError } = await client.auth.signUp({ email: String(form.get("email")), password: String(form.get("password")) });
      if (signUpError) return setError(signUpError.message);
      if (!data.session) return setMessage("Account created. Confirm your email, then sign in to enroll your authenticator.");
      const { data: enrolled, error: enrollError } = await client.auth.mfa.enroll({ factorType: "totp", friendlyName: "LakeSafe operator" });
      if (enrollError || !enrolled?.totp) return setError(enrollError?.message ?? "Could not start TOTP enrollment.");
      setFactor({ id: enrolled.id, qrCode: enrolled.totp.qr_code, secret: enrolled.totp.secret });
    } catch { setError("Could not create your account or start enrollment. Please try again."); }
    finally { pending.current = false; setBusy(false); }
  }

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!factor || pending.current) return;
    pending.current = true; setBusy(true);
    try {
      setError("");
      const code = String(new FormData(event.currentTarget).get("code"));
      const { data: challenge, error: challengeError } = await client.auth.mfa.challenge({ factorId: factor.id });
      if (challengeError) return setError(challengeError.message);
      const { error: verifyError } = await client.auth.mfa.verify({ factorId: factor.id, challengeId: challenge.id, code });
      if (verifyError) return setError(verifyError.message);
      navigate(returnTo);
    } catch { setError("Could not verify your authenticator. Please try again."); }
    finally { pending.current = false; setBusy(false); }
  }

  return <main className="auth-page"><section ref={ref} className="auth-card">{!factor ? <><h1>Create your LakeSafe account</h1><p>Public lake notices need no account. A new account starts with civilian access: profile settings and the route to request verified station access if you serve a U.S. law-enforcement agency.</p><form onSubmit={submit}><label>Email<input name="email" type="email" autoComplete="email" required /></label><label>Password<input name="password" type="password" autoComplete="new-password" minLength={8} required /></label>{error && <p className="form-error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}<button disabled={busy}>{busy ? "Creating account…" : "Create account"}</button></form><p><Link to={authDestination("/login", returnTo)}>Back to sign in</Link> · <Link to="/">Public lakes</Link></p></> : <><h1>Set up your authenticator</h1><p>Scan this code with an authenticator app, or enter the setup key manually.</p><img className="totp-qr" src={factor.qrCode} alt="TOTP QR code for LakeSafe" /><label>Setup key<input readOnly value={factor.secret} aria-label="TOTP setup key" /></label><form onSubmit={verify}><label>Authentication code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required /></label>{error && <p className="form-error" role="alert">{error}</p>}<button disabled={busy}>{busy ? "Verifying…" : "Verify and continue"}</button></form></>}</section></main>;
}
