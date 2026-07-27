import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { apiRequest } from "../lib/apiClient";
import { supabase, type SupabaseLike } from "../lib/supabase";
import type { Principal } from "../lib/types";

type PrincipalContextValue = { principal: Principal | null; loading: boolean; refresh: () => Promise<void> };
const PrincipalContext = createContext<PrincipalContextValue | null>(null);

export function PrincipalProvider({ children, client = supabase, request = apiRequest }: { children: ReactNode; client?: SupabaseLike; request?: typeof apiRequest }) {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    const { data } = await client.auth.getSession();
    if (!data.session) { setPrincipal(null); setLoading(false); return; }
    try { setPrincipal(await request<Principal>("/api/me", undefined, client)); }
    catch { setPrincipal(null); }
    finally { setLoading(false); }
  }, [client, request]);
  useEffect(() => { void refresh(); const { data } = client.auth.onAuthStateChange(() => void refresh()); return () => data.subscription.unsubscribe(); }, [client, refresh]);
  return <PrincipalContext.Provider value={{ principal, loading, refresh }}>{children}</PrincipalContext.Provider>;
}

export function usePrincipal(): PrincipalContextValue {
  const context = useContext(PrincipalContext);
  if (!context) throw new Error("usePrincipal must be used within PrincipalProvider");
  return context;
}
