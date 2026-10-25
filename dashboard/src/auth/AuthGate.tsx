import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";

import { authDestination } from "./returnTo";

type GateState = "loading" | "signed-out" | "ended" | "ready" | "error";

export function AuthGate({ client = supabase }: { client?: SupabaseLike }) {
  const location = useLocation();
  const [state, setState] = useState<GateState>("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    let generation = 0;
    const evaluate = async () => {
      const request = ++generation;
      try {
        const { data, error } = await client.auth.getSession();
        if (!current || request !== generation) return;
        if (error) throw error;
        if (!data.session) return current && setState("signed-out");
        if (current) setState("ready");
      } catch { if (current && request === generation) setState("error"); }
    };
    void evaluate();
    const { data: subscription } = client.auth.onAuthStateChange((event: string) => {
      if (event === "SIGNED_OUT") { ++generation; if (current) setState("ended"); }
      else void evaluate();
    });
    return () => { current = false; subscription.subscription.unsubscribe(); };
  }, [client, attempt]);
  if (state === "error") return <main className="auth-page"><section className="auth-card"><h1>Session unavailable</h1><p className="form-error" role="alert">Could not check your session. Please try again.</p><button onClick={() => { setState("loading"); setAttempt((value) => value + 1); }}>Retry</button></section></main>;
  if (state === "loading") return <main className="auth-loading" aria-live="polite">Preparing operator workspace…</main>;
  if (state === "ended") return <Navigate to="/" replace />;
  if (state === "signed-out") return <Navigate to={authDestination("/login", location.pathname + location.search + location.hash)} replace />;
  return <Outlet />;
}
