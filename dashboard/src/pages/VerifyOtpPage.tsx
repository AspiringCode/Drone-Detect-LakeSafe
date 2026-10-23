import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { useOrientation } from "../lib/useOrientation";
import { apiRequest } from "../lib/apiClient";
import type { Principal } from "../lib/types";

type TotpFactor = { id: string; qrCode: string; secret: string };
type ListedTotpFactor = { id: string; status?: string };

export function VerifyOtpPage({ client = supabase, request = apiRequest }: { client?: SupabaseLike; request?: typeof apiRequest }) {
  const ref = useOrientation();
  const navigate = useNavigate();
  const [factorId, setFactorId] = useState("");
  const [enrollment, setEnrollment] = useState<TotpFactor | null>(null);
  const [error, setError] = useState("");
  const [checkingAccess, setCheckingAccess] = useState(true);

  useEffect(() => {
    let active = true;
    async function findOrEnrollFactor() {
      try {
        const principal = await request<Principal>("/api/me", undefined, client);
        if (!active) return;
        if (principal.judge_demo_access === true) { navigate("/lakes", { replace: true }); return; }
      } catch {
        if (active) { setError("Could not check account access. Please return to sign in and try again."); setCheckingAccess(false); }
        return;
      }
      setCheckingAccess(false);
      const { data, error: listError } = await client.auth.mfa.listFactors() as { data?: { totp?: ListedTotpFactor[] }; error?: { message: string } | null };
      if (!active) return;
      if (listError) return setError(listError.message);

      const verifiedFactor = data?.totp?.find((factor) => factor.status !== "unverified");
      if (verifiedFactor) return setFactorId(verifiedFactor.id);

      const { data: enrolled, error: enrollError } = await client.auth.mfa.enroll({ factorType: "totp", friendlyName: "LakeSafe operator" });
      if (!active) return;
      if (enrollError || !enrolled?.totp) return setError(enrollError?.message ?? "Could not start TOTP enrollment.");
      setFactorId(enrolled.id);
      setEnrollment({ id: enrolled.id, qrCode: enrolled.totp.qr_code, secret: enrolled.totp.secret });
    }

    void findOrEnrollFactor();
    return () => { active = false; };
  }, [client, request, navigate]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!factorId) return;
    setError("");
    const code = String(new FormData(event.currentTarget).get("code"));
    const { data: challenge, error: challengeError } = await client.auth.mfa.challenge({ factorId });
    if (challengeError) return setError(challengeError.message);
    const { error: verifyError } = await client.auth.mfa.verify({ factorId, challengeId: challenge.id, code });
    if (verifyError) return setError(verifyError.message);
    navigate("/lakes");
  }

  const codeForm = <form onSubmit={submit}><label>Authentication code<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" required /></label>{error && <p className="form-error" role="alert">{error}</p>}<button disabled={!factorId}>{enrollment ? "Verify and continue" : "Verify code"}</button></form>;

  return <main className="auth-page"><section ref={ref} className="auth-card">{checkingAccess ? <p role="status">Checking account access…</p> : enrollment ? <><h1>Set up your authenticator</h1><p>Scan this code with an authenticator app, or enter the setup key manually.</p><img className="totp-qr" src={enrollment.qrCode} alt="TOTP QR code for LakeSafe" /><label>Setup key<input readOnly value={enrollment.secret} aria-label="TOTP setup key" /></label>{codeForm}</> : <><h1>Verify TOTP code</h1><p>Enter the current six-digit code from your authenticator app.</p>{codeForm}</>}<p><Link to="/login">Back to sign in</Link></p></section></main>;
}
