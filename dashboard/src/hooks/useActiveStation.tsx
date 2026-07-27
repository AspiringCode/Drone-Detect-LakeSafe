import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { usePrincipal } from "../auth/PrincipalProvider";
import type { StationMembership } from "../lib/types";

const KEY = "lakesafe-active-station";
type Value = { station: StationMembership | null; select: (stationId: string) => void };
const ActiveStationContext = createContext<Value | null>(null);

export function ActiveStationProvider({ children }: { children: ReactNode }) {
  const { principal } = usePrincipal();
  const memberships = principal?.memberships ?? [];
  const [stationId, setStationId] = useState(() => localStorage.getItem(KEY) ?? "");
  useEffect(() => {
    const next = memberships.some((item) => item.station_id === stationId) ? stationId : memberships[0]?.station_id ?? "";
    if (next) localStorage.setItem(KEY, next); else localStorage.removeItem(KEY);
    if (next !== stationId) setStationId(next);
  }, [memberships, stationId]);
  const select = useCallback((id: string) => { if (!memberships.some((item) => item.station_id === id)) return; localStorage.setItem(KEY, id); setStationId(id); }, [memberships]);
  const station = memberships.find((item) => item.station_id === stationId) ?? null;
  const value = useMemo(() => ({ station, select }), [station, select]);
  return <ActiveStationContext.Provider value={value}>{children}</ActiveStationContext.Provider>;
}

export function useActiveStation(): Value {
  const context = useContext(ActiveStationContext);
  if (!context) throw new Error("useActiveStation must be used within ActiveStationProvider");
  return context;
}
