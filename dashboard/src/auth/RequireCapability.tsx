import { Navigate, Outlet } from "react-router-dom";
import type { Capability } from "../lib/types";
import { usePrincipal } from "./PrincipalProvider";

export function RequireCapability({ capability }: { capability: Capability }) {
  const { principal, loading } = usePrincipal();
  if (loading) return <main className="auth-loading" aria-live="polite">Checking access…</main>;
  const granted = principal && (principal.aal === "aal2" || principal.judge_demo_access === true) && principal.memberships.some((membership) => membership.status === "active" && membership.capabilities.includes(capability));
  return granted ? <Outlet /> : <Navigate to="/lakes" replace />;
}
