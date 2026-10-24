import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { useOptionalActiveStation } from "../hooks/useActiveStation";
import { apiRequest } from "../lib/apiClient";
import { supabase, type SupabaseLike } from "../lib/supabase";
import type { Lake } from "../lib/types";
import "./website-touchups.css";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface RealDrone {
  inventory_id: string;
  lake_id: string | null;
  lifecycle: string;
  battery_percent: number;
  health: string;
  connectivity: string;
  updated_at: string;
  manufacturer: string | null;
  serial: string | null;
}

const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const message = (value: unknown, fallback: string) => value instanceof Error ? value.message : fallback;

export function DronesPage({ client = supabase, setup = false }: { client?: SupabaseLike; setup?: boolean }) {
  const station = useOptionalActiveStation()?.station ?? null;
  const stationId = station?.station_id ?? "";
  const allowed = station?.capabilities.includes("inventory.manage") ?? false;
  const [drones, setDrones] = useState<RealDrone[]>([]);
  const [lakes, setLakes] = useState<Lake[]>([]);
  const [loading, setLoading] = useState(true);
  const [registered, setRegistered] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [step, setStep] = useState("Register");
  const [selectedDrone, setSelectedDrone] = useState("");
  const requestGeneration = useRef(0);
  const currentStation = useRef(stationId);
  currentStation.current = stationId;

  async function refresh() {
    if (!allowed) return;
    const generation = ++requestGeneration.current;
    setLoading(true);
    setError("");
    try {
      const [inventory, lakeRows] = await Promise.all([
        apiRequest<{ drones: RealDrone[] }>(`/api/stations/${encodeURIComponent(stationId)}/inventory/real`, {}, client),
        client.from("lakes").select("lake_id,station_id,org_id,name,centroid_lat,centroid_lon").order("name"),
      ]);
      if (generation !== requestGeneration.current || currentStation.current !== stationId) return;
      if (lakeRows.error) throw lakeRows.error;
      setDrones(inventory.drones);
      setLakes(((lakeRows.data ?? []) as Lake[]).filter((lake) => lake.station_id === stationId));
    } catch (value) { if (generation === requestGeneration.current && currentStation.current === stationId) setError(message(value, "Drones could not be loaded.")); } finally { if (generation === requestGeneration.current && currentStation.current === stationId) setLoading(false); }
  }
  useEffect(() => { setRegistered(null); setSelectedDrone(""); setStep("Register"); setDrones([]); setLakes([]); setStatus(""); setError(""); void refresh(); return () => { requestGeneration.current++; }; }, [stationId, allowed]);

  async function act(work: () => Promise<unknown>, done: string, fallback: string) {
    setError(""); setStatus("");
    try { await work(); if (currentStation.current !== stationId) return; setStatus(done); await refresh(); } catch (value) { if (currentStation.current === stationId) setError(message(value, fallback)); }
  }
  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    await act(async () => {
      const result = await apiRequest<{ drone_id: string }>(`/api/stations/${encodeURIComponent(stationId)}/inventory/real`, json({
        manufacturer: String(form.get("manufacturer")).trim(), serial: String(form.get("serial")).trim(), public_key: String(form.get("public_key")).trim(),
      }), client);
      if (currentStation.current === stationId) { setRegistered(result.drone_id); setSelectedDrone(result.drone_id); target.reset(); }
    }, "Drone registered. Assign it to a lake, then connect it.", "Drone could not be registered.");
  }
  const assign = (drone: RealDrone, lakeId: string) => act(() => apiRequest(`/api/stations/${encodeURIComponent(stationId)}/inventory/${drone.inventory_id}/lake`, json({ lake_id: lakeId || null }), client), lakeId ? "Drone assigned to the lake." : "Drone removed from its lake.", "Lake assignment failed.");
  const placeTest = (drone: RealDrone) => {
    const lake = lakes.find((item) => item.lake_id === drone.lake_id);
    if (!lake) return;
    void act(() => apiRequest(`/api/stations/${encodeURIComponent(stationId)}/inventory/${drone.inventory_id}/test-position`, json({ lat: lake.centroid_lat, lon: lake.centroid_lon }), client), `Test marker placed at the centre of ${lake.name} for 5 minutes.`, "Test marker could not be placed.");
  };
  const patrol = (drone: RealDrone) => act(() => apiRequest(`/api/stations/${encodeURIComponent(stationId)}/inventory/${drone.inventory_id}/patrol`, json({}), client), "Patrol sent. The drone's Pi uploads it on its next heartbeat; on the ground it waits for the pilot to arm.", "Patrol could not be sent.");
  const retire = (drone: RealDrone) => act(() => apiRequest(`/api/stations/${encodeURIComponent(stationId)}/inventory/${drone.inventory_id}/retire`, { method: "POST" }, client), "Drone retired.", "Drone could not be retired.");

  if (!allowed) return <main className="app-page"><AppHeader active="drones" showStationPicker client={client}/><section className="workflow-shell"><h1>Drone registry is unavailable</h1><p>Choose a station where you are a station administrator.</p></section></main>;
  const lakeName = (id: string | null) => lakes.find((lake) => lake.lake_id === id)?.name ?? "Not assigned";
  const connectIds = [...new Set([...(registered ? [registered] : []), ...drones.map((drone) => drone.inventory_id)])];
  const connectId = connectIds.includes(selectedDrone) ? selectedDrone : connectIds[0] ?? "<drone-id>";
  const inventory = <section className="touch-panel" aria-label="Registered drones">
        <h2>Registered drones</h2>
        {loading ? <p className="field-help">Loading drones…</p> : error ? <p>Fleet information could not be refreshed.</p> : !drones.length ? <div className="fleet-empty"><h3>No real drones are registered to this station yet.</h3><p>Register a drone, assign a lake, then connect its heartbeat.</p>{!setup && <Link className="button-link" to="/drones/setup">Register a drone</Link>}</div> : <ul className="station-results fleet-registry">{drones.map((drone) => <li key={drone.inventory_id}>
          <div><strong>{drone.manufacturer ?? "Drone"} {drone.serial}</strong><p className="field-help">{drone.connectivity} · {drone.health} · {drone.battery_percent}% · {lakeName(drone.lake_id)}</p><details><summary>Device details</summary><p className="field-help">{drone.inventory_id}</p><p className="field-help">Inventory updated: {drone.updated_at && Number.isFinite(Date.parse(drone.updated_at)) ? new Date(drone.updated_at).toLocaleString() : "Not available"}</p></details></div>
          <span>
            <label><span className="sr-only">Lake for {drone.serial}</span><select aria-label={`Lake for ${drone.serial}`} value={drone.lake_id ?? ""} onChange={(event) => void assign(drone, event.target.value)}><option value="">Not assigned</option>{lakes.map((lake) => <option key={lake.lake_id} value={lake.lake_id}>{lake.name}</option>)}</select></label>
            {drone.lake_id && <><button type="button" className="button-secondary" onClick={() => placeTest(drone)}>Place test marker</button><button type="button" className="button-secondary" onClick={() => void patrol(drone)}>Send patrol</button><Link className="button-link" to={`/lakes/${drone.lake_id}`}>Open map</Link></>}
            <button type="button" className="button-secondary" onClick={() => void retire(drone)}>Retire</button>
          </span>
        </li>)}</ul>}
        <p className="field-help">Test markers are SIMULATED for 5 minutes. Only real heartbeats show as REAL.</p>
      </section>;
  return <main className="app-page"><AppHeader active="drones" showStationPicker client={client}/><section className="workflow-shell touch-shell">
    <header className="page-heading touch-heading"><div><h1>{setup ? "Drone setup" : "Drones"}</h1><p>{station?.station_name}</p></div>{setup ? <Link to="/drones">Back to registered drones</Link> : <Link className="button-link button-secondary" to="/drones/setup">Open setup guide</Link>}</header>
    {status && <p className="form-success" role="status">{status}</p>}
    {error && <div className="touch-error" role="alert"><p>{error}</p><button className="button-secondary" onClick={() => void refresh()}>Retry fleet information</button></div>}
    {!setup ? inventory : <>
      <nav className="local-tabs setup-steps" aria-label="Drone setup steps">{["Register", "Assign lake", "Connect"].map((item, index) => <button type="button" key={item} aria-current={step === item ? "step" : undefined} className={step === item ? "is-active" : ""} onClick={() => setStep(item)}><span aria-hidden="true">{index + 1}</span>{item}</button>)}</nav>
      {step === "Register" && <section className="touch-panel setup-form" aria-label="Register a drone">
        <h2>Register a drone</h2>
        <p>On the drone or ground laptop, create its key. Only the public key is pasted here; the private key never leaves the device.</p>
        <CommandBlock command="python drone_link.py keygen --key drone.pem" />
        <form onSubmit={register}>
          <label>Manufacturer<input name="manufacturer" required maxLength={120}/></label>
          <label>Serial number<input name="serial" required maxLength={160}/></label>
          <label>Public key<input name="public_key" required minLength={40} maxLength={200} autoComplete="off" spellCheck={false}/></label>
          <button>Register drone</button>
        </form>
      </section>}
      {step === "Assign lake" && <><p className="field-help">Choose a lake for each registered drone. Only this station’s lakes are available.</p>{inventory}</>}
      {step === "Connect" && <section className="touch-panel" aria-label="Connect a drone">
        <h2>Connect it to the map</h2>
        {connectIds.length > 0 && <label>Drone to connect<select value={connectId} onChange={(event) => setSelectedDrone(event.target.value)}>{connectIds.map((id) => { const drone = drones.find((item) => item.inventory_id === id); return <option key={id} value={id}>{drone?.serial || id}</option>; })}</select></label>}
        <p className="field-help">Commands below use {connectId === "<drone-id>" ? "a placeholder. Register a drone first and replace it with the registered device ID" : `device ${connectId}`}. The private key stays on your device.</p>
        <p>After assigning a lake, run one of these. Mission Planner: forward MAVLink to UDP 14550 on this laptop. On the drone's Raspberry Pi: read the flight controller's serial port.</p>
        <details open><summary>Ground laptop</summary><CommandBlock command={`python mavlink_bridge.py --api ${API} --mavlink udpin:0.0.0.0:14550 --drone 1=${connectId}=drone.pem`} /></details>
        <details><summary>Raspberry Pi</summary><CommandBlock command={`python mavlink_bridge.py --api ${API} --mavlink /dev/serial0 --drone 1=${connectId}=drone.pem`} /></details>
        <details><summary>Test one position without a flight controller</summary><p className="field-help">This sends the example location below. Replace it with your test site. The 1 in bridge commands is the MAVLink system ID.</p><CommandBlock command={`python drone_link.py heartbeat --api ${API} --drone-id ${connectId} --key drone.pem --battery 90 --lat 47.592 --lon -122.0325`} /></details>
        <h3>Verify the connection</h3><p>Return to the registry and check its connection status, then open the assigned lake map. A real marker requires a current heartbeat.</p><Link to="/drones">Check registered drones</Link>
        <p className="field-help">Send patrol uploads a loop of the lake’s patrol zone. Your RC transmitter always overrides it; on the ground the drone waits for the pilot to arm.</p>
      </section>}
    </>}
  </section></main>;
}

function CommandBlock({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => { setCopied(false); setFailed(false); }, [command]);
  async function copy() {
    try { await navigator.clipboard.writeText(command); setCopied(true); setFailed(false); }
    catch { setFailed(true); }
  }
  return <div className="command-block"><pre tabIndex={0}><code>{command}</code></pre><button type="button" className="button-secondary" onClick={() => void copy()}>{copied ? "Copied" : "Copy command"}</button>{failed && <p role="status">Copy unavailable. Select the command to copy it.</p>}</div>;
}
