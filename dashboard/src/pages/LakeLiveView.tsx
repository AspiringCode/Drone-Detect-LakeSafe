import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertPanel } from "../components/AlertPanel";
import { DroneRoster } from "../components/DroneRoster";
import { LakeMap, type RiskGeoJSON } from "../components/LakeMap";
import { SimulatedBadge } from "../components/SimulatedBadge";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { connectOperationalPositions, connectPositions } from "../lib/ws";
import { useOrientation } from "../lib/useOrientation";
import type { Alert, Capability, Principal, SimulationState } from "../lib/types";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const wsFor = (lakeId: string) => `${API.replace(/^http/, "ws")}/ws/lakes/${lakeId}/positions`;
type Organization = { station_lat: number; station_lon: number };
type LakeMetadata = { drone_inventory_cap: number; station_id?: string; organizations: Organization | Organization[] | null };

export function hasLakeCapability(principal: Principal | null | undefined, lakeStationId: string | null, capability: Capability): boolean {
  return Boolean(lakeStationId && principal?.aal === "aal2" && principal.memberships.some((item) => item.station_id === lakeStationId && item.status === "active" && item.capabilities.includes(capability)));
}

export function LakeLiveView({ client = supabase, accessToken, fetcher = fetch, connect = connectPositions, connectOperational = connectOperationalPositions }: { client?: SupabaseLike; accessToken?: string; fetcher?: typeof fetch; connect?: typeof connectPositions; connectOperational?: typeof connectOperationalPositions }) {
  const { lakeId = "" } = useParams();
  const principalContext = useOptionalPrincipal();
  const principal = principalContext?.principal;
  const ref = useOrientation();
  const [drones, setDrones] = useState<SimulationState["drones"]>([]);
  const [riskmap, setRiskmap] = useState<RiskGeoJSON | null>(null);
  const [alert, setAlert] = useState<Alert | null>(null);
  const [noLive, setNoLive] = useState(false);
  const [capReached, setCapReached] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [station, setStation] = useState<{ lat: number; lon: number } | null>(null);
  const [inventoryCap, setInventoryCap] = useState<number | null>(null);
  const [lakeStationId, setLakeStationId] = useState<string | null>(null);

  const canReadOperations = hasLakeCapability(principal, lakeStationId, "station.read");
  const canDeploy = hasLakeCapability(principal, lakeStationId, "inventory.manage");
  const canManageAlerts = hasLakeCapability(principal, lakeStationId, "alert.manage");
  useEffect(() => { let active = true; void fetcher(`${API}/api/lakes/${lakeId}/riskmap`).then(async (r) => { if (r.status === 404) return active && setNoLive(true); if (r.ok) setRiskmap(await r.json()); }).catch(() => active && setNoLive(true)); let stop = () => {}; if (canReadOperations) { void (async () => { const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token; if (token && active) stop = connectOperational(wsFor(lakeId), token, (state) => setDrones(state.drones)); })(); } else if (!principalContext) stop = connect(wsFor(lakeId), (state) => setDrones(state.drones)); return () => { active = false; stop(); }; }, [lakeId, fetcher, connect, connectOperational, client, accessToken, canReadOperations, principalContext]);
  useEffect(() => { void fetcher(`${API}/api/lakes/${lakeId}/alerts`).then((r) => r.ok ? r.json() : []).then((alerts: Alert[]) => setAlert(alerts[0] ?? null)); }, [lakeId, fetcher]);
  useEffect(() => {
    let active = true;
    void client.from("lakes").select("station_id,drone_inventory_cap,organizations(station_lat,station_lon)").eq("lake_id", lakeId).maybeSingle().then(({ data, error }: { data: LakeMetadata | null; error: unknown }) => {
      if (error || !data || !active) return;
      const org = Array.isArray(data.organizations) ? data.organizations[0] : data.organizations;
      setLakeStationId(data.station_id ?? null);
      if (!org) return;
      setStation({ lat: org.station_lat, lon: org.station_lon });
      setInventoryCap(data.drone_inventory_cap);
    });
    return () => { active = false; };
  }, [client, lakeId]);

  const atCap = inventoryCap !== null && drones.length >= inventoryCap;
  async function deploy() { if (atCap || !canDeploy) return; setDeploying(true); const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token; const response = await fetcher(`${API}/api/lakes/${lakeId}/drones/deploy`, { method: "POST", headers: { Authorization: `Bearer ${token ?? ""}` } }); setDeploying(false); if (response.status === 409) setCapReached(true); }
  async function demo() { if (!canManageAlerts) return; const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token; const response = await fetcher(`${API}/api/lakes/${lakeId}/demo/trigger`, { method: "POST", headers: { Authorization: `Bearer ${token ?? ""}` } }); if (response.ok) setAlert(await response.json()); }
  async function escalate(id: string) { if (!canManageAlerts) return; const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token; await fetcher(`${API}/api/lakes/${lakeId}/alerts/${id}/escalate`, { method: "POST", headers: { Authorization: `Bearer ${token ?? ""}` } }); }
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
            <AlertPanel alert={alert} onEscalate={canManageAlerts ? escalate : undefined} />
          </section>
          {canDeploy && <section className="panel-card action-card">
            <div className="panel-heading"><div><p className="panel-eyebrow">Controls</p><h2>Operator actions</h2></div></div>
            <button onClick={deploy} disabled={deploying || capReached || atCap}>{capReached || atCap ? "Inventory cap reached" : "Deploy drone"}</button>
            {canManageAlerts && <button className="button-secondary" onClick={demo}>Fire demo trigger</button>}
          </section>}
        </aside>
      </section>
    </main>
  );
}
