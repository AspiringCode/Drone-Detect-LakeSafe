import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { authDestination, safeReturnTo } from "../auth/returnTo";
import { advanceRecoverySession, getRecoverySession } from "../auth/recoverySession";

type RecoverySession = { access_token: string; expires_at?: number; user?: { id: string } };
const validSession = (session: RecoverySession | null) => Boolean(session?.access_token && (!session.expires_at || session.expires_at * 1000 > Date.now()));

export function ForgotPasswordPage({ client = supabase }: { client?: SupabaseLike }) {
  const [params] = useSearchParams();
  const returnTo = safeReturnTo(params.get("returnTo"));
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [sent, setSent] = useState(false);
  const pending = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (pending.current) return;
    const email = String(new FormData(event.currentTarget).get("email")).trim();
    pending.current = true; setBusy(true); setError(""); setSent(false);
    try {
      const { error: resetError } = await client.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}${authDestination("/reset-password", returnTo)}` });
      if (resetError) throw resetError;
      setSent(true);
    } catch { setError("Could not send the reset link. Please try again."); }
    finally { pending.current = false; setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-card"><h1>Reset your password</h1><p>We’ll email a link to choose a new password. Your authenticator will still be required.</p><form onSubmit={submit}><label>Email<input name="email" type="email" autoComplete="email" required /></label>{error && <p className="form-error" role="alert">{error}</p>}{sent && <p role="status">If an account exists for this email, a reset link is on its way. Check your inbox and spam folder.</p>}<button disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button></form><p><Link to={authDestination("/login", returnTo)}>Back to sign in</Link></p></section></main>;
}

export function ResetPasswordPage({ client = supabase }: { client?: SupabaseLike }) {
  const [params] = useSearchParams(); const returnTo = safeReturnTo(params.get("returnTo"));
  const [session, setSession] = useState<RecoverySession | null>(() => client === supabase ? getRecoverySession() : null);
  const recovery = useRef(session);
  function remember(value: RecoverySession | null) { recovery.current = value; setSession(value); }
  const [factorId, setFactorId] = useState("");
  const [factorChecking, setFactorChecking] = useState(false);
  const [factorError, setFactorError] = useState("");
  const [checking, setChecking] = useState(true); const [busy, setBusy] = useState(false); const [done, setDone] = useState(false); const [error, setError] = useState("");
  const pending = useRef(false);
  useEffect(() => {
    let active = true;
    const { data } = client.auth.onAuthStateChange((event: string, next: RecoverySession | null) => {
      if (!active) return;
      if (event === "PASSWORD_RECOVERY") { remember(validSession(next) ? next : null); setChecking(false); }
      else if (["SIGNED_OUT", "SIGNED_IN", "USER_UPDATED"].includes(event)) { remember(null); setChecking(false); }
    });
    void client.auth.getSession().then(() => { if (active) { if (client === supabase) remember(getRecoverySession()); setChecking(false); } }).catch(() => { if (active) { remember(null); setChecking(false); } });
    return () => { active = false; data.subscription.unsubscribe(); };
  }, [client]);
  useEffect(() => {
    let active = true;
    setFactorId(""); setFactorError("");
    if (!session || !client.auth.mfa?.listFactors) return;
    setFactorChecking(true);
    void client.auth.mfa.listFactors().then(({ data, error: cause }: { data?: { totp?: Array<{ id: string; status: string }> }; error?: unknown }) => {
      if (!active) return;
      if (cause) throw cause;
      setFactorId(data?.totp?.find((factor) => factor.status === "verified")?.id ?? "");
    }).catch(() => { if (active) setFactorError("Your authenticator could not be checked. Reload this recovery link or request a new one."); })
      .finally(() => { if (active) setFactorChecking(false); });
    return () => { active = false; };
  }, [client, session?.user?.id, Boolean(session)]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (pending.current) return;
    if (!validSession(session)) { remember(null); return; }
    if (factorChecking || factorError) return;
    const form = new FormData(event.currentTarget); const password = String(form.get("password"));
    if (password !== String(form.get("confirm"))) return setError("Passwords do not match.");
    pending.current = true; setBusy(true); setError("");
    try {
      const { data, error: sessionError } = await client.auth.getSession();
      if (sessionError || !validSession(data.session) || data.session.access_token !== recovery.current?.access_token) { remember(null); return; }
      if (factorId) {
        const previous = recovery.current!;
        const { data: challenge, error: challengeError } = await client.auth.mfa.challenge({ factorId });
        if (challengeError || !challenge?.id) { setError("Could not challenge your authenticator. Please try again."); return; }
        const { data: verified, error: verifyError } = await client.auth.mfa.verify({ factorId, challengeId: challenge.id, code: String(form.get("code")) });
        if (verifyError) { setError("Could not verify your authenticator. Check the code and retry."); return; }
        const { data: next, error: nextError } = await client.auth.getSession();
        if (nextError || !validSession(next.session) || !previous.user?.id || next.session.user?.id !== previous.user.id || verified?.access_token !== next.session.access_token || recovery.current?.access_token !== previous.access_token) { remember(null); return; }
        const { data: assurance, error: assuranceError } = await client.auth.mfa.getAuthenticatorAssuranceLevel(next.session.access_token);
        if (assuranceError || assurance?.currentLevel !== "aal2") { setError("Authenticator verification is required before changing your password."); return; }
        if (client === supabase && !advanceRecoverySession(previous.access_token, next.session)) { remember(null); return; }
        remember(next.session);
      }
      if (!recovery.current || (client === supabase && getRecoverySession()?.access_token !== recovery.current.access_token)) { remember(null); return; }
      const { error: updateError } = await client.auth.updateUser({ password });
      if (updateError) { setError("Could not update your password. Request a new link if this one has expired, or try again."); return; }
      await client.auth.signOut({ scope: "local" });
      setDone(true); remember(null);
    } catch { setError("Could not update your password. Please try again or request a new link."); }
    finally { pending.current = false; setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-card"><h1>Choose a new password</h1>{done ? <p role="status">Password updated. Sign in with your new password and authenticator.</p> : checking ? <p role="status">Checking reset link…</p> : validSession(session) ? <form onSubmit={submit}><label>New password<input name="password" type="password" autoComplete="new-password" minLength={8} required /></label><label>Confirm new password<input name="confirm" type="password" autoComplete="new-password" minLength={8} required /></label>{factorChecking && <p role="status">Checking authenticator requirements…</p>}{factorId && <label>Authentication code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required /></label>}{factorError && <p className="form-error" role="alert">{factorError}</p>}{factorId && <p className="field-help">Use your existing authenticator. A reset link does not remove two-factor protection.</p>}{error && <p className="form-error" role="alert">{error}</p>}<button disabled={busy || factorChecking || Boolean(factorError)}>{busy ? "Updating…" : "Update password"}</button></form> : <><p className="form-error" role="alert">This reset link is expired or invalid. Request a new link to continue.</p><p><Link to={authDestination("/forgot-password", returnTo)}>Request a new reset link</Link></p></>}<p><Link to={authDestination("/login", returnTo)}>Back to sign in</Link></p></section></main>;
}
