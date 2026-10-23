import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { useOptionalActiveStation } from "../hooks/useActiveStation";
import { apiRequest } from "../lib/apiClient";
import { supabase, type SupabaseLike } from "../lib/supabase";
import type { Lake } from "../lib/types";

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

export function DronesPage({ client = supabase }: { client?: SupabaseLike }) {
  const station = useOptionalActiveStation()?.station ?? null;
  const stationId = station?.station_id ?? "";
  const allowed = station?.capabilities.includes("inventory.manage") ?? false;
  const [drones, setDrones] = useState<RealDrone[]>([]);
  const [lakes, setLakes] = useState<Lake[]>([]);
  const [loading, setLoading] = useState(true);
  const [registered, setRegistered] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    if (!allowed) return;
    setLoading(true);
    try {
      const [inventory, lakeRows] = await Promise.all([
        apiRequest<{ drones: RealDrone[] }>(`/api/stations/${encodeURIComponent(stationId)}/inventory/real`, {}, client),
        client.from("lakes").select("lake_id,station_id,org_id,name,centroid_lat,centroid_lon").order("name"),
      ]);
      if (lakeRows.error) throw lakeRows.error;
      setDrones(inventory.drones);
      setLakes(((lakeRows.data ?? []) as Lake[]).filter((lake) => lake.station_id === stationId));
    } catch (value) { setError(message(value, "Drones could not be loaded.")); } finally { setLoading(false); }
  }
  useEffect(() => { setRegistered(null); setStatus(""); setError(""); void refresh(); }, [stationId, allowed]);

  async function act(work: () => Promise<unknown>, done: string, fallback: string) {
    setError(""); setStatus("");
    try { await work(); setStatus(done); await refresh(); } catch (value) { setError(message(value, fallback)); }
  }
  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const target = event.currentTarget;
    await act(async () => {
      const result = await apiRequest<{ drone_id: string }>(`/api/stations/${encodeURIComponent(stationId)}/inventory/real`, json({
        manufacturer: String(form.get("manufacturer")).trim(), serial: String(form.get("serial")).trim(), public_key: String(form.get("public_key")).trim(),
      }), client);
      setRegistered(result.drone_id); target.reset();
    }, "Drone registered. Assign it to a lake below, then connect it.", "Drone could not be registered.");
  }
  const assign = (drone: RealDrone, lakeId: string) => act(() => apiRequest(`/api/stations/${encodeURIComponent(stationId)}/inventory/${drone.inventory_id}/lake`, json({ lake_id: lakeId || null }), client), lakeId ? "Drone assigned to the lake." : "Drone removed from its lake.", "Lake assignment failed.");
  const placeTest = (drone: RealDrone) => {
    const lake = lakes.find((item) => item.lake_id === drone.lake_id);
    if (!lake) return;
    void act(() => apiRequest(`/api/stations/${encodeURIComponent(stationId)}/inventory/${drone.inventory_id}/test-position`, json({ lat: lake.centroid_lat, lon: lake.centroid_lon }), client), `Test marker placed at the centre of ${lake.name} for 5 minutes.`, "Test marker could not be placed.");
  };
  const retire = (drone: RealDrone) => act(() => apiRequest(`/api/stations/${encodeURIComponent(stationId)}/inventory/${drone.inventory_id}/retire`, { method: "POST" }, client), "Drone retired.", "Drone could not be retired.");

  if (!allowed) return <main className="app-page"><AppHeader active="drones" showStationPicker client={client}/><section className="workflow-shell"><h1>Drone registry is unavailable</h1><p>Choose a station where you are a station administrator.</p></section></main>;
  const lakeName = (id: string | null) => lakes.find((lake) => lake.lake_id === id)?.name ?? "Not assigned";
  const connectId = registered ?? "<drone-id>";
  return <main className="app-page"><AppHeader active="drones" showStationPicker client={client}/><section className="workflow-shell">
    <header className="page-heading"><h1>Drones</h1><p>Register real drones for {station?.station_name}, assign each to a lake, and check that it reports in.</p></header>
    <div className="workflow-grid">
      <section className="workflow-card" aria-label="Registered drones">
        <p className="panel-eyebrow">Fleet</p><h2>Registered drones</h2>
        {loading ? <p className="field-help">Loading drones…</p> : !drones.length ? <p>No real drones are registered to this station yet.</p> : <ul className="station-results">{drones.map((drone) => <li key={drone.inventory_id}>
          <span><strong>{drone.manufacturer ?? "Drone"} {drone.serial}</strong><br/><small className="field-help">{drone.inventory_id} · {drone.connectivity} · {drone.health} · {drone.battery_percent}% · {lakeName(drone.lake_id)}</small></span>
          <span>
            <label><span className="sr-only">Lake for {drone.serial}</span><select aria-label={`Lake for ${drone.serial}`} value={drone.lake_id ?? ""} onChange={(event) => void assign(drone, event.target.value)}><option value="">Not assigned</option>{lakes.map((lake) => <option key={lake.lake_id} value={lake.lake_id}>{lake.name}</option>)}</select></label>
            {drone.lake_id && <><button type="button" className="button-secondary" onClick={() => placeTest(drone)}>Place test marker</button><Link className="button-link" to={`/lakes/${drone.lake_id}`}>Open map</Link></>}
            <button type="button" className="button-secondary" onClick={() => void retire(drone)}>Retire</button>
          </span>
        </li>)}</ul>}
        <p className="field-help">Test markers show as SIMULATED for 5 minutes. Only real heartbeats show as REAL.</p>
      </section>
      <section className="workflow-card" aria-label="Register a drone">
        <p className="panel-eyebrow">Step 1</p><h2>Register a drone</h2>
        <p>On the drone or ground laptop, create its key. Only the public key is pasted here; the private key never leaves the device.</p>
        <pre className="field-help"><code>python drone_link.py keygen --key drone.pem</code></pre>
        <form onSubmit={register}>
          <label>Manufacturer<input name="manufacturer" required maxLength={120}/></label>
          <label>Serial number<input name="serial" required maxLength={160}/></label>
          <label>Public key<input name="public_key" required minLength={40} maxLength={200} autoComplete="off" spellCheck={false}/></label>
          <button>Register drone</button>
        </form>
      </section>
      <section className="workflow-card" aria-label="Connect a drone">
        <p className="panel-eyebrow">Step 2</p><h2>Connect it to the map</h2>
        <p>After assigning a lake, run one of these. Mission Planner: forward MAVLink to UDP 14550 on this laptop. On the drone's Raspberry Pi: read the flight controller's serial port.</p>
        <pre className="field-help"><code>{`python mavlink_bridge.py --api ${API} --mavlink udpin:0.0.0.0:14550 --drone 1=${connectId}=drone.pem`}</code></pre>
        <pre className="field-help"><code>{`python mavlink_bridge.py --api ${API} --mavlink /dev/serial0 --drone 1=${connectId}=drone.pem`}</code></pre>
        <p className="field-help">The 1 is the drone's MAVLink system ID. No flight controller yet? Send a single position: <code>{`python drone_link.py heartbeat --api ${API} --drone-id ${connectId} --key drone.pem --battery 90 --lat 47.592 --lon -122.0325`}</code></p>
      </section>
    </div>
    {status && <p className="field-help" role="status">{status}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section></main>;
}
