import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertPanel } from "../components/AlertPanel";
import { DroneRoster } from "../components/DroneRoster";
import { LakeMap, type RiskGeoJSON } from "../components/LakeMap";
import { SimulatedBadge } from "../components/SimulatedBadge";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { connectOperationalPositions, connectPositions } from "../lib/ws";
import { useOrientation } from "../lib/useOrientation";
import type { Alert, Capability, FleetDrone, LatLon, Principal, RealFleetSafetyStatus, SimulationState, ZonePlanSummary } from "../lib/types";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { applyReconcileStatus, loadFleet, loadRealFleetSafetyStatus, loadZonePlan, requestCirculation, requestSafeReturn, setRealAutonomy } from "../lib/fleetData";
import { AutonomyControls } from "../components/AutonomyControls";
import { FleetInventoryPanel } from "../components/FleetInventoryPanel";
import { ZonePlanStatus } from "../components/ZonePlanStatus";
import { RealFleetSafetyPanel } from "../components/RealFleetSafetyPanel";
import { ApiError } from "../lib/apiClient";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const wsFor = (lakeId: string) => `${API.replace(/^http/, "ws")}/ws/operations/lakes/${lakeId}`;
type Organization = { station_lat: number; station_lon: number };
type LakeMetadata = { name: string; centroid_lat: number; centroid_lon: number; drone_inventory_cap: number; station_id?: string; organizations: Organization | Organization[] | null };

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
  const [station, setStation] = useState<{ lat: number; lon: number } | null>(null);
  const [inventoryCap, setInventoryCap] = useState<number | null>(null);
  const [lakeName, setLakeName] = useState("Lake operations");
  const [lakeCenter, setLakeCenter] = useState<LatLon | null>(null);
  const [lakeStationId, setLakeStationId] = useState<string | null>(null);
  const [fleet, setFleet] = useState<FleetDrone[]>([]);
  const [zonePlan, setZonePlan] = useState<ZonePlanSummary | null>(null);
  const [pendingCirculationId, setPendingCirculationId] = useState<string | null>(null);
  const [reconciliationId, setReconciliationId] = useState<string | null>(null);
  const [circulationError, setCirculationError] = useState<string | null>(null);
  const [operationsDataError, setOperationsDataError] = useState<string | null>(null);
  const [realSafety, setRealSafety] = useState<RealFleetSafetyStatus | null>(null);
  const [realSafetyBusy, setRealSafetyBusy] = useState(false);
  const [realSafetyError, setRealSafetyError] = useState<string | null>(null);

  const canReadOperations = hasLakeCapability(principal, lakeStationId, "station.read");
  const canManageAlerts = hasLakeCapability(principal, lakeStationId, "alert.manage");
  const canManageAutonomy = hasLakeCapability(principal, lakeStationId, "autonomy.manage");
  const stationCapabilities = lakeStationId ? principal?.memberships.find((item) => item.station_id === lakeStationId && item.status === "active")?.capabilities ?? [] : [];
  useEffect(() => {
    let active = true;
    let stop = () => {};
    setNoLive(false);
    setRiskmap(null);
    setAlert(null);
    setDrones([]);
    if (canReadOperations) void (async () => {
      const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token;
      if (!active) return;
      if (!token) throw new Error("Missing operator session");
      stop = connectOperational(wsFor(lakeId), token, (state) => { if (active) setDrones(state.drones); });
      const options = { headers: { Authorization: `Bearer ${token}` } };
      await Promise.all([
        fetcher(`${API}/api/lakes/${lakeId}/riskmap`, options).then(async (response) => {
          if (response.status === 404) { if (active) setNoLive(true); return; }
          if (!response.ok) throw new Error("Risk map unavailable");
          const data = await response.json();
          if (active) setRiskmap(data);
        }),
        fetcher(`${API}/api/lakes/${lakeId}/alerts`, options).then(async (response) => {
          if (!response.ok) throw new Error("Alerts unavailable");
          const data: Alert[] = await response.json();
          if (active) setAlert(data[0] ?? null);
        }),
      ]);
    })().catch(() => { if (active) setOperationsDataError("Live lookout data could not be loaded. Return to lakes and reopen this workspace to retry."); });
    return () => { active = false; stop(); };
  }, [lakeId, fetcher, connectOperational, client, accessToken, canReadOperations]);
  useEffect(() => {
    let active = true;
    void client.from("lakes").select("name,centroid_lat,centroid_lon,station_id,drone_inventory_cap,organizations(station_lat,station_lon)").eq("lake_id", lakeId).maybeSingle().then(({ data, error }: { data: LakeMetadata | null; error: unknown }) => {
      if (error || !data || !active) return;
      const org = Array.isArray(data.organizations) ? data.organizations[0] : data.organizations;
      setLakeName(data.name);
      if (Number.isFinite(data.centroid_lat) && Number.isFinite(data.centroid_lon)) {
        setLakeCenter({ lat: data.centroid_lat, lon: data.centroid_lon });
      }
      setLakeStationId(data.station_id ?? null);
      if (!org) return;
      setStation({ lat: org.station_lat, lon: org.station_lon });
      setInventoryCap(data.drone_inventory_cap);
    });
    return () => { active = false; };
  }, [client, lakeId]);

  useEffect(() => {
    if (!canReadOperations || !lakeStationId) { setFleet([]); setZonePlan(null); setRealSafety(null); setOperationsDataError(null); return; }
    let active = true;
    void Promise.allSettled([loadFleet(lakeStationId, lakeId, client, fetcher), loadZonePlan(lakeStationId, lakeId, client, fetcher), loadRealFleetSafetyStatus(lakeStationId, lakeId, client, fetcher)]).then(([fleetResult, planResult, realSafetyResult]) => {
      if (!active) return;
      if (fleetResult.status === "fulfilled") setFleet(fleetResult.value);
      if (planResult.status === "fulfilled") setZonePlan(planResult.value);
      if (realSafetyResult.status === "fulfilled") setRealSafety(realSafetyResult.value);
      if (fleetResult.status === "rejected" || planResult.status === "rejected") setOperationsDataError("Operational data could not be loaded. Existing live telemetry may still be available.");
    });
    return () => { active = false; };
  }, [canReadOperations, lakeStationId, lakeId, client, fetcher]);

  async function changeCirculation(droneId: string, request: { eligible: boolean; reason: string }) {
    if (!canManageAutonomy || !lakeStationId) return;
    setPendingCirculationId(droneId);
    setCirculationError(null);
    try {
      const result = await requestCirculation(lakeStationId, lakeId, droneId, request, client, fetcher);
      setReconciliationId(result.reconciliationId);
      setFleet((current) => applyReconcileStatus(current, droneId, result));
    } catch { setCirculationError("The circulation change could not be queued. Try again."); }
    finally { setPendingCirculationId(null); }
  }
  async function changeRealAutonomy(enabled: boolean, reason: string) {
    if (!canManageAutonomy || !lakeStationId) return;
    setRealSafetyBusy(true); setRealSafetyError(null);
    try { setRealSafety(await setRealAutonomy(lakeStationId, lakeId, enabled, reason, client, fetcher)); }
    catch (error) { setRealSafetyError(error instanceof ApiError && error.status === 403 ? "Recent MFA is required before changing real fleet safety policy." : "The real fleet safety policy could not be updated."); }
    finally { setRealSafetyBusy(false); }
  }
  async function returnRealFleet(reason: string) {
    if (!canManageAutonomy || !lakeStationId) return;
    setRealSafetyBusy(true); setRealSafetyError(null);
    try { setRealSafety(await requestSafeReturn(lakeStationId, lakeId, reason, client, fetcher)); }
    catch (error) { setRealSafetyError(error instanceof ApiError && error.status === 403 ? "Recent MFA is required before requesting a fleet safe return." : "The fleet safe-return request could not be sent."); }
    finally { setRealSafetyBusy(false); }
  }
  async function demo() { if (!canManageAlerts) return; const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token; const response = await fetcher(`${API}/api/lakes/${lakeId}/demo/trigger`, { method: "POST", headers: { Authorization: `Bearer ${token ?? ""}` } }); if (response.ok) setAlert(await response.json()); }
  async function escalate(id: string) { if (!canManageAlerts) return; const token = accessToken ?? (await client.auth.getSession()).data.session?.access_token; await fetcher(`${API}/api/lakes/${lakeId}/alerts/${id}/escalate`, { method: "POST", headers: { Authorization: `Bearer ${token ?? ""}` } }); }
  if (noLive) return <main className="app-page"><AppHeader active="operations" contextLabel={lakeName} client={client} /><section className="runtime-unavailable"><h1>No live data for this lake</h1><p>The operator runtime is unavailable. Return to your lakes to choose another workspace.</p><Link className="button-link" to="/lakes">Return to lakes</Link></section></main>;
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
            <p className="live-description">Patrol coverage, fleet telemetry and incident response.</p>
          </div>
          <SimulatedBadge source="simulated" />
        </div>
      </section>
      <section className="operator-layout" aria-label={`${lakeName} live operations`}>
        <section className="map-card" aria-label="Live lake map">
          <header className="map-heading"><h2>Patrol lookout</h2><span>Lake coverage</span></header>
          {lakeCenter ? <LakeMap lakeName={lakeName} lakeCenter={lakeCenter} riskmap={riskmap} drones={drones} stationLocation={station ?? undefined} /> : <div className="map-placeholder" role="status"><h2>Map not available yet</h2><p>Waiting for this lake’s location data.</p></div>}
        </section>
        <aside className="side-panel" aria-label="Operations details">
          {operationsDataError && <p className="operations-data-error" role="alert" aria-label="Operational data error">{operationsDataError}</p>}
          {canReadOperations && <ZonePlanStatus plan={zonePlan} />}
          <section className="panel-card fleet-card">
            <div className="panel-heading">
              <div><p className="panel-eyebrow">Fleet</p><h2>Drone status</h2></div>
              <div className="fleet-capacity" aria-label={`${drones.length} of ${inventoryCap ?? "unknown"} drones deployed`}>
                <span><strong>{drones.length}</strong><small> / {inventoryCap ?? "—"}</small></span>
                {inventoryCap !== null && inventoryCap > 0 && <span className="fleet-capacity__meter" role="progressbar" aria-label="Fleet capacity" aria-valuemin={0} aria-valuemax={inventoryCap} aria-valuenow={Math.min(drones.length, inventoryCap)}><span style={{ width: `${Math.min(100, (drones.length / inventoryCap) * 100)}%` }} /></span>}
              </div>
            </div>
            <DroneRoster drones={drones} />
          </section>
          {canReadOperations && <FleetInventoryPanel drones={fleet} />}
          {canReadOperations && realSafety && <RealFleetSafetyPanel capabilities={stationCapabilities} status={realSafety} busy={realSafetyBusy} error={realSafetyError} onSetAutonomy={changeRealAutonomy} onRequestSafeReturn={returnRealFleet} />}
          <section className="panel-card alert-card">
            <div className="panel-heading"><div><p className="panel-eyebrow">Response</p><h2>Active alert</h2></div></div>
            <AlertPanel alert={alert} onEscalate={canManageAlerts ? escalate : undefined} />
          </section>
          {canManageAlerts && <section className="panel-card action-card">
            <div className="panel-heading"><div><p className="panel-eyebrow">Response</p><h2>Alert simulation</h2></div></div>
            <button className="button-secondary" onClick={demo}>Fire demo trigger</button>
          </section>}
          {canManageAutonomy && <AutonomyControls capabilities={stationCapabilities} drones={fleet} pendingId={pendingCirculationId} reconciliationId={reconciliationId} error={circulationError} onRequest={changeCirculation} />}
        </aside>
      </section>
    </main>
  );
}
