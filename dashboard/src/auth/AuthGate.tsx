import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";

type GateState = "loading" | "signed-out" | "needs-mfa" | "onboarding" | "ready";

export function AuthGate({ client = supabase }: { client?: SupabaseLike }) {
  const [state, setState] = useState<GateState>("loading");
  useEffect(() => {
    let current = true;
    const evaluate = async () => {
      const { data } = await client.auth.getSession();
      if (!data.session) return current && setState("signed-out");
      const { data: assurance } = await client.auth.mfa.getAuthenticatorAssuranceLevel();
      if (!current) return;
      if (assurance?.currentLevel !== "aal2") return setState("needs-mfa");
      const { data: orgs, error } = await client.from("organizations").select("org_id").limit(1);
      if (!current) return;
      setState(error || !orgs?.length ? "onboarding" : "ready");
    };
    void evaluate();
    const { data: subscription } = client.auth.onAuthStateChange(() => { void evaluate(); });
    return () => { current = false; subscription.subscription.unsubscribe(); };
  }, [client]);
  if (state === "loading") return <main className="auth-loading" aria-live="polite">Preparing operator workspace…</main>;
  if (state === "signed-out") return <Navigate to="/login" replace />;
  if (state === "needs-mfa") return <Navigate to="/verify-2fa" replace />;
  if (state === "onboarding") return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}
