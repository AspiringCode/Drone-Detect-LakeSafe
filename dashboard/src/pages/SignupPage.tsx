import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOrientation } from "../lib/useOrientation";

type TotpFactor = { id: string; qrCode: string; secret: string };

export function SignupPage({ client = supabase }: { client?: SupabaseLike }) {
  const ref = useOrientation();
  const navigate = useNavigate();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [factor, setFactor] = useState<TotpFactor | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const { data, error: signUpError } = await client.auth.signUp({ email: String(form.get("email")), password: String(form.get("password")) });
    if (signUpError) return setError(signUpError.message);
    if (!data.session) return setMessage("Account created. Confirm your email, then sign in to enroll your authenticator.");
    const { data: enrolled, error: enrollError } = await client.auth.mfa.enroll({ factorType: "totp", friendlyName: "LakeSafe operator" });
    if (enrollError || !enrolled?.totp) return setError(enrollError?.message ?? "Could not start TOTP enrollment.");
    setFactor({ id: enrolled.id, qrCode: enrolled.totp.qr_code, secret: enrolled.totp.secret });
  }

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!factor) return;
    setError("");
    const code = String(new FormData(event.currentTarget).get("code"));
    const { data: challenge, error: challengeError } = await client.auth.mfa.challenge({ factorId: factor.id });
    if (challengeError) return setError(challengeError.message);
    const { error: verifyError } = await client.auth.mfa.verify({ factorId: factor.id, challengeId: challenge.id, code });
    if (verifyError) return setError(verifyError.message);
    navigate("/lakes");
  }

  return <main className="auth-page"><section ref={ref} className="auth-card">{!factor ? <><h1>Create your LakeSafe account</h1><p>New accounts start with civilian access. You can request verification later if you serve a U.S. law-enforcement agency.</p><form onSubmit={submit}><label>Email<input name="email" type="email" autoComplete="email" required /></label><label>Password<input name="password" type="password" autoComplete="new-password" minLength={8} required /></label>{error && <p className="form-error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}<button>Create account</button></form><p><Link to="/login">Back to sign in</Link></p></> : <><h1>Set up your authenticator</h1><p>Scan this code with an authenticator app, or enter the setup key manually.</p><img className="totp-qr" src={factor.qrCode} alt="TOTP QR code for LakeSafe" /><label>Setup key<input readOnly value={factor.secret} aria-label="TOTP setup key" /></label><form onSubmit={verify}><label>Authentication code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required /></label>{error && <p className="form-error" role="alert">{error}</p>}<button>Verify and continue</button></form></>}</section></main>;
}
