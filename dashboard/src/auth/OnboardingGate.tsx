import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";

type OnboardingGateState = "loading" | "signed-out" | "ready";

/**
 * Onboarding deliberately does not require an organization. It is the route
 * an authenticated, MFA-verified operator uses to create their first one.
 */
export function OnboardingGate({ client = supabase }: { client?: SupabaseLike }) {
  const [state, setState] = useState<OnboardingGateState>("loading");

  useEffect(() => {
    let current = true;
    const evaluate = async () => {
      const { data } = await client.auth.getSession();
      if (!data.session) return current && setState("signed-out");

      if (current) setState("ready");
    };

    void evaluate();
    const { data: subscription } = client.auth.onAuthStateChange(() => { void evaluate(); });
    return () => {
      current = false;
      subscription.subscription.unsubscribe();
    };
  }, [client]);

  if (state === "loading") return <main className="auth-loading" aria-live="polite">Checking operator access…</main>;
  if (state === "signed-out") return <Navigate to="/login" replace />;
  return <Outlet />;
}
