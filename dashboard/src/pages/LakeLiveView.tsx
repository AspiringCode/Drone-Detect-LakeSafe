import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertPanel } from "../components/AlertPanel";
import { DroneRoster } from "../components/DroneRoster";
import { LakeMap, type RiskGeoJSON } from "../components/LakeMap";
import { supabase, type SupabaseLike } from "../lib/supabase";
import { connectOperationalPositions, connectPositions } from "../lib/ws";
import { useOrientation } from "../lib/useOrientation";
import { useNewAlertCue } from "../lib/useNewAlertCue";
import type { Alert, Capability, LatLon, Principal, RealFleetSafetyStatus, RegisteredDrone, SimulationState } from "../lib/types";
import { AppHeader } from "../components/AppHeader";
import { useOptionalPrincipal } from "../auth/PrincipalProvider";
import { changeSimulation, loadRealFleetSafetyStatus, loadRegisteredDrones, requestSafeReturn, setRealAutonomy, type RealDroneChoice, type SimulationAction } from "../lib/fleetData";
import { RealFleetSafetyPanel } from "../components/RealFleetSafetyPanel";
import { ApiError } from "../lib/apiClient";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const wsFor = (lakeId: string) => `${API.replace(/^http/, "ws")}/ws/operations/lakes/${lakeId}`;
type LakeMetadata = { name: string; centroid_lat: number; centroid_lon: number; station_id?: string };

export function hasLakeCapability(principal: Principal | null | undefined, lakeStationId: string | null, capability: Capability): boolean {
  return Boolean(lakeStationId && principal && (principal.aal === "aal2" || principal.judge_demo_access === true) && principal.memberships.some((item) => item.station_id === lakeStationId && item.status === "active" && item.capabilities.includes(capability)));
}

export function LakeLiveView({ client = supabase, accessToken, fetcher = fetch, connect = connectPositions, connectOperational = connectOperationalPositions }: { client?: SupabaseLike; accessToken?: string; fetcher?: typeof fetch; connect?: typeof connectPositions; connectOperational?: typeof connectOperationalPositions }) {
  const { lakeId = "" } = useParams();
  const principalContext = useOptionalPrincipal();
  const principal = principalContext?.principal;
  const ref = useOrientation();
  const [drones, setDrones] = useState<SimulationState["drones"]>([]);
  const [simulationRunning, setSimulationRunning] = useState(false);
  const [riskmap, setRiskmap] = useState<RiskGeoJSON | null>(null);
  const [alert, setAlert] = useState<Alert | null>(null);
  const alertCue = useNewAlertCue(alert);
  const [noLive, setNoLive] = useState(false);
  const [metadataError, setMetadataError] = useState(false);
  const [lakeName, setLakeName] = useState("Lake operations");
  const [lakeCenter, setLakeCenter] = useState<LatLon | null>(null);
  const [lakeStationId, setLakeStationId] = useState<string | null>(null);
  const [registered, setRegistered] = useState<RegisteredDrone[]>([]);
  const [simulationBusy, setSimulationBusy] = useState(false);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [askAboutRealDrones, setAskAboutRealDrones] = useState(false);
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
      stop = connectOperational(wsFor(lakeId), token, (state) => { if (!active) return; setDrones(state.drones); setSimulationRunning(state.simulation_running ?? false); if (state.latest_alert) setAlert(state.latest_alert); });
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
    setMetadataError(false);
    setLakeName("Lake operations");
    setLakeCenter(null);
    setLakeStationId(null);
    void (async () => {
      try {
        const { data, error }: { data: LakeMetadata | null; error: unknown } = await client.from("lakes").select("name,centroid_lat,centroid_lon,station_id").eq("lake_id", lakeId).maybeSingle();
        if (!active) return;
        if (error || !data) throw error ?? new Error("Lake unavailable");
        setLakeName(data.name);
        if (Number.isFinite(data.centroid_lat) && Number.isFinite(data.centroid_lon)) setLakeCenter({ lat: data.centroid_lat, lon: data.centroid_lon });
        setLakeStationId(data.station_id ?? null);
      } catch {
        if (active) setMetadataError(true);
      }
    })();
    return () => { active = false; };
  }, [client, lakeId]);

  useEffect(() => {
    if (!canReadOperations || !lakeStationId) { setRegistered([]); setRealSafety(null); setOperationsDataError(null); return; }
    let active = true;
    void Promise.allSettled([loadRegisteredDrones(lakeId, client, fetcher), loadRealFleetSafetyStatus(lakeStationId, lakeId, client, fetcher)]).then(([registeredResult, realSafetyResult]) => {
      if (!active) return;
      if (registeredResult.status === "fulfilled") setRegistered(registeredResult.value);
      else setOperationsDataError("Registered drones could not be loaded. Live telemetry may still be available.");
      if (realSafetyResult.status === "fulfilled") setRealSafety(realSafetyResult.value);
    });
    return () => { active = false; };
  }, [canReadOperations, lakeStationId, lakeId, client, fetcher]);

  async function simulate(action: SimulationAction, realDrones?: RealDroneChoice) {
    if (!canManageAutonomy) return;
    setAskAboutRealDrones(false);
    setSimulationBusy(true); setSimulationError(null);
    try {
      const result = await changeSimulation(lakeId, action, client, fetcher, realDrones);
      setRiskmap(result.riskmap as RiskGeoJSON);
      setSimulationRunning(result.simulated_drones > 0);
      // Zone changes can move real drones, so their Zone column is refreshed too.
      if (registered.length) setRegistered(await loadRegisteredDrones(lakeId, client, fetcher));
    } catch (error) { setSimulationError(error instanceof Error ? error.message : "The simulation could not be changed."); }
    finally { setSimulationBusy(false); }
  }
  const start = () => registered.length ? setAskAboutRealDrones(true) : void simulate("simulation/start");
  // Test markers are simulated too, but they are not part of the session.
  const waitingDrones = drones.filter((drone) => drone.source === "simulated" && !drone.assigned_zone && !drone.drone_id.endsWith("(test)"));
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
  if (metadataError) return <main className="app-page"><AppHeader active="lakes" contextLabel={lakeName} client={client} /><section className="runtime-unavailable"><h1>Lake information is unavailable</h1><p role="alert" aria-label="Lake information error">Lake information could not be loaded. Return to lakes and reopen this workspace to retry.</p><Link className="button-link" to="/lakes">Return to lakes</Link></section></main>;
  if (noLive) return <main className="app-page"><AppHeader active="lakes" contextLabel={lakeName} client={client} /><section className="runtime-unavailable"><h1>No live data for this lake</h1><p>The operator runtime is unavailable. Return to your lakes to choose another workspace.</p><Link className="button-link" to="/lakes">Return to lakes</Link></section></main>;
  return (
    <main ref={ref} className="app-page live-shell">
      <AppHeader active="lakes" contextLabel={lakeName} client={client} />
      <section className="live-summary">
        <div className="live-heading">
          <div className="live-title-row">
            <nav className="live-context" aria-label="Breadcrumb">
              <Link to="/lakes">Lakes</Link>
              <span aria-hidden="true"> &gt; </span>
            </nav>
            <h1>{lakeName}</h1>
          </div>
          <p className="sr-only" role="alert" aria-label="New alert announcement">{alertCue}</p>
        </div>
      </section>
      <section className="operator-layout" aria-label={`${lakeName} live operations`}>
        <section className="map-card" aria-label="Live lake map">
          <header className="map-heading"><h2>Patrol lookout</h2></header>
          {lakeCenter ? <LakeMap lakeName={lakeName} lakeCenter={lakeCenter} riskmap={riskmap} drones={drones} /> : <div className="map-placeholder" role="status"><h2>Map not available yet</h2><p>Waiting for this lake’s location data.</p></div>}
        </section>
        <aside className="side-panel" aria-label="Live status">
          <section className="panel-card fleet-card" aria-label="Fleet">
            <div className="panel-heading"><h2>Fleet</h2></div>
            {canManageAutonomy && <div className="fleet-actions">
              {simulationRunning ? <>
                <button className="button-secondary" disabled={simulationBusy} onClick={() => void simulate("simulation/drones")}>Add simulated drone</button>
                {/* A waiting drone has no zone until the lake is re-divided, so that becomes the primary action. */}
                <button className={waitingDrones.length ? undefined : "button-secondary"} disabled={simulationBusy} onClick={() => void simulate("zones/regenerate")}>Regenerate zones</button>
                {canManageAlerts && <button className="button-secondary" onClick={() => void demo()}>Simulate detection</button>}
                <button className="button-secondary" disabled={simulationBusy} onClick={() => void simulate("simulation/stop")}>Stop simulation</button>
              </> : <>
                <button className="button-secondary" disabled={simulationBusy} onClick={start}>Start simulation</button>
                {registered.length > 0 && <button className="button-secondary" disabled={simulationBusy} onClick={() => void simulate("zones/regenerate")}>Regenerate zones</button>}
              </>}
            </div>}
            {waitingDrones.length > 0 && <p className="fleet-prompt" role="status">{waitingDrones.length === 1 ? "A new drone is" : `${waitingDrones.length} new drones are`} waiting ashore. Regenerate zones to give {waitingDrones.length === 1 ? "it" : "them"} a patrol area.</p>}
            {simulationError && <p className="form-error" role="alert">{simulationError}</p>}
            <DroneRoster drones={drones} registered={registered} />
          </section>
          <section className="panel-card alert-card" aria-label="Active alert">
            <div className="panel-heading"><h2>Active alert</h2></div>
            <AlertPanel alert={alert} onEscalate={canManageAlerts ? escalate : undefined} />
          </section>
        </aside>
      </section>
      {(operationsDataError || (registered.length > 0 && realSafety)) && <section className="operations-details" aria-label="Lake details and controls">
        {operationsDataError && <p className="operations-data-error" role="alert" aria-label="Operational data error">{operationsDataError}</p>}
        {registered.length > 0 && realSafety && <RealFleetSafetyPanel capabilities={stationCapabilities} status={realSafety} busy={realSafetyBusy} error={realSafetyError} onSetAutonomy={changeRealAutonomy} onRequestSafeReturn={returnRealFleet} />}
      </section>}
      {askAboutRealDrones && <div className="modal-backdrop" onKeyDown={(event) => { if (event.key === "Escape") setAskAboutRealDrones(false); }}>
        <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="real-drones-title">
          <h2 id="real-drones-title">Change real drones’ flight paths?</h2>
          <p>{registered.length === 1 ? "A real drone is" : `${registered.length} real drones are`} on this lake. Changing re-divides the lake for every drone, so {registered.length === 1 ? "its" : "their"} next patrol uses a new zone.</p>
          <div className="modal-actions">
            <button autoFocus onClick={() => void simulate("simulation/start", "replan")}>Change flight paths</button>
            <button className="button-secondary" onClick={() => void simulate("simulation/start", "keep")}>Leave unaffected</button>
            <button className="button-secondary" onClick={() => setAskAboutRealDrones(false)}>Cancel</button>
          </div>
        </div>
      </div>}
    </main>
  );
}
