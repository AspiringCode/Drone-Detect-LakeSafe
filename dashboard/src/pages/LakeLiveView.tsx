import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertPanel } from "../components/AlertPanel";
import { DroneRoster } from "../components/DroneRoster";
import { LakeMap, type RiskGeoJSON } from "../components/LakeMap";
import { SimulatedBadge } from "../components/SimulatedBadge";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { connectPositions } from "../lib/ws";
import { useOrientation } from "../lib/useOrientation";
import type { Alert, SimulationState } from "../lib/types";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const wsFor = (lakeId: string) => `${API.replace(/^http/, "ws")}/ws/lakes/${lakeId}/positions`;
type Organization = { station_lat: number; station_lon: number };
type LakeMetadata = { drone_inventory_cap: number; organizations: Organization | Organization[] | null };

export function LakeLiveView({ client = supabase, accessToken, fetcher = fetch, connect = connectPositions }: { client?: SupabaseLike; accessToken?: string; fetcher?: typeof fetch; connect?: typeof connectPositions }) {
  const { lakeId = "" } = useParams();
  const ref = useOrientation();
  const [drones, setDrones] = useState<SimulationState["drones"]>([]);
  const [riskmap, setRiskmap] = useState<RiskGeoJSON | null>(null);
  const [alert, setAlert] = useState<Alert | null>(null);
  const [noLive, setNoLive] = useState(false);
  const [capReached, setCapReached] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [station, setStation] = useState<{ lat: number; lon: number } | null>(null);
  const [inventoryCap, setInventoryCap] = useState<number | null>(null);

  useEffect(() => { let active = true; void fetcher(`${API}/api/lakes/${lakeId}/riskmap`).then(async (r) => { if (r.status === 404) return active && setNoLive(true); if (r.ok) setRiskmap(await r.json()); }).catch(() => active && setNoLive(true)); const stop = connect(wsFor(lakeId), (state) => setDrones(state.drones)); return () => { active = false; stop(); }; }, [lakeId, fetcher, connect]);
  useEffect(() => { void fetcher(`${API}/api/lakes/${lakeId}/alerts`).then((r) => r.ok ? r.json() : []).then((alerts: Alert[]) => setAlert(alerts[0] ?? null)); }, [lakeId, fetcher]);
  useEffect(() => {
    let active = true;
    void client.from("lakes").select("drone_inventory_cap,organizations(station_lat,station_lon)").eq("lake_id", lakeId).maybeSingle().then(({ data, error }: { data: LakeMetadata | null; error: unknown }) => {
      if (error || !data || !active) return;
      const org = Array.isArray(data.organizations) ? data.organizations[0] : data.organizations;
      if (!org) return;
      setStation({ lat: org.station_lat, lon: org.station_lon });
      setInventoryCap(data.drone_inventory_cap);
    });
    return () => { active = false; };
  }, [client, lakeId]);

  const atCap = inventoryCap !== null && drones.length >= inventoryCap;
  async function deploy() { if (atCap) return; setDeploying(true); const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token; const response = await fetcher(`${API}/api/lakes/${lakeId}/drones/deploy`, { method: "POST", headers: { Authorization: `Bearer ${token ?? ""}` } }); setDeploying(false); if (response.status === 409) setCapReached(true); }
  async function demo() { const response = await fetcher(`${API}/api/lakes/${lakeId}/demo/trigger`, { method: "POST" }); if (response.ok) setAlert(await response.json()); }
  async function escalate(id: string) { await fetcher(`${API}/api/lakes/${lakeId}/alerts/${id}/escalate`, { method: "POST" }); }
  if (noLive) return <main className="no-live"><p className="kicker">LakeSafe Initiative</p><h1>No live data for this lake</h1><p>This lake is saved to your organization, but its operator runtime is not active.</p><Link to="/lakes">Return to lakes</Link></main>;
  return <main ref={ref} className="live-shell"><header className="operator-header"><div><p className="kicker">LakeSafe Initiative</p><h1>Live operator view</h1></div><div className="operator-header__actions"><SimulatedBadge source="simulated" /><button onClick={demo}>Fire demo trigger</button><button onClick={deploy} disabled={deploying || capReached || atCap}>{capReached || atCap ? "Inventory cap reached" : "Deploy drone"}</button></div></header>{(capReached || atCap) && <p className="form-error" role="alert">Drone inventory cap reached. Deployment is unavailable for this lake.</p>}<section className="operator-layout">{station && <LakeMap riskmap={riskmap} drones={drones} stationLocation={station} />}<div className="side-panel"><DroneRoster drones={drones} /><AlertPanel alert={alert} onEscalate={escalate} /></div></section></main>;
}
