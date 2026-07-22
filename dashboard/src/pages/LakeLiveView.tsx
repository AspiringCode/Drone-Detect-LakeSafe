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
import { AppHeader } from "../components/AppHeader";

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
  const lakeName = lakeId === "lake-sammamish" ? "Lake Sammamish" : "Live lake";

  return (
    <main ref={ref} className="app-page live-shell">
      <AppHeader active="operations" contextLabel={lakeName} operationsHref={`/lakes/${lakeId}`} client={client} />
      <section className="live-summary">
        <div className="live-heading">
          <div>
            <nav className="live-context" aria-label="Breadcrumb">
              <Link to="/lakes">Lakes</Link>
              <span aria-hidden="true"> &gt; </span>
              <span aria-current="page">Operations</span>
            </nav>
            <h1>{lakeName}</h1>
          </div>
          <SimulatedBadge source="simulated" />
        </div>
      </section>
      <section className="operator-layout" aria-label={`${lakeName} live operations`}>
        <section className="map-card" aria-label="Live lake map">
          {station && <LakeMap riskmap={riskmap} drones={drones} stationLocation={station} />}
        </section>
        <aside className="side-panel" aria-label="Operations details">
          <section className="panel-card fleet-card">
            <div className="panel-heading">
              <div><p className="panel-eyebrow">Fleet</p><h2>Drone status</h2></div>
              <div className="fleet-capacity" aria-label={`${drones.length} of ${inventoryCap ?? "unknown"} drones deployed`}>
                <span><strong>{drones.length}</strong><small> / {inventoryCap ?? "—"}</small></span>
                {inventoryCap !== null && <span className="fleet-capacity__meter" role="progressbar" aria-label="Fleet capacity" aria-valuemin={0} aria-valuemax={inventoryCap} aria-valuenow={Math.min(drones.length, inventoryCap)}><span style={{ width: `${Math.min(100, (drones.length / inventoryCap) * 100)}%` }} /></span>}
              </div>
            </div>
            {(capReached || atCap) && <div className="fleet-warning" role="alert"><span className="fleet-warning__icon" aria-hidden="true">!</span><span><strong>Fleet capacity reached</strong><small>Inventory cap reached. Deployment is paused.</small></span></div>}
            <DroneRoster drones={drones} />
          </section>
          <section className="panel-card alert-card">
            <div className="panel-heading"><div><p className="panel-eyebrow">Response</p><h2>Active alert</h2></div></div>
            <AlertPanel alert={alert} onEscalate={escalate} />
          </section>
          <section className="panel-card action-card">
            <div className="panel-heading"><div><p className="panel-eyebrow">Controls</p><h2>Operator actions</h2></div></div>
            <button onClick={deploy} disabled={deploying || capReached || atCap}>{capReached || atCap ? "Inventory cap reached" : "Deploy drone"}</button>
            <button className="button-secondary" onClick={demo}>Fire demo trigger</button>
          </section>
        </aside>
      </section>
    </main>
  );
}
