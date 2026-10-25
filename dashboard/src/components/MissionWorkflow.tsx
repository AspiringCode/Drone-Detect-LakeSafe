import { type FormEvent, useEffect, useRef, useState } from "react";
import { apiRequest } from "../lib/apiClient";
import type { SupabaseLike } from "../lib/supabase";

type DroneReference = { inventory_id: string; lake_id?: string | null };
type Zone = { zone_id: string; radius_m: number; is_proxy?: boolean };
type Parameters = { zone_id: string; home_lat: number; home_lon: number; altitude_m: number };
type Preview = { zone_id: string; home: { lat: number; lon: number }; altitude_m: number; waypoint_count: number; mission_hash: string; route: Array<{ lat: number; lon: number }> };
type PatrolCommand = { command_id: string; status: "queued" | "delivered" | "uploaded" | "rejected" | "expired"; detail?: string; expires_at: string };
const json = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function MissionWorkflow({ drone, stationId, client, send = false, onQueued }: {
  drone: DroneReference; stationId: string; client: SupabaseLike; send?: boolean; onQueued?: () => void;
}) {
  const [open, setOpen] = useState(send);
  const [zones, setZones] = useState<Zone[] | null>(null);
  const [zone, setZone] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [altitude, setAltitude] = useState("30");
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ result: Preview; parameters: Parameters } | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const base = `/api/stations/${encodeURIComponent(stationId)}/inventory/${encodeURIComponent(drone.inventory_id)}`;
  useEffect(() => {
    setLatitude(""); setLongitude(""); setAltitude("30"); setPreview(null);
  }, [base, drone.lake_id]);
  useEffect(() => {
    let current = true;
    setZones(null); setPreview(null); setError("");
    if (open) void apiRequest<{ zones: Zone[]; assigned_zone_id?: string | null }>(`${base}/patrol-zones`, {}, client)
      .then((result) => { if (current) { setZones(result.zones); setZone(result.assigned_zone_id ?? result.zones[0]?.zone_id ?? ""); } })
      .catch((cause) => { if (current) setError(cause instanceof Error ? cause.message : "Patrol zones could not be loaded."); });
    return () => { current = false; };
  }, [base, drone.lake_id, open, attempt, client]);
  const parameters = (): Parameters => ({ zone_id: zone, home_lat: Number(latitude), home_lon: Number(longitude), altitude_m: Number(altitude) });
  async function prepare(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true); setPreview(null);
    const values = parameters();
    try { setPreview({ result: await apiRequest<Preview>(`${base}/mission-preview`, json(values), client), parameters: values }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Mission preview is unavailable."); }
    finally { setBusy(false); }
  }
  async function queue() {
    if (!preview) return;
    setBusy(true); setError("");
    try {
      await apiRequest<PatrolCommand>(`${base}/patrol`, json({ ...preview.parameters, reviewed_hash: preview.result.mission_hash }), client);
      onQueued?.();
    } catch (cause) { setPreview(null); setError(cause instanceof Error ? cause.message : "Patrol could not be queued. Preview it again before retrying."); }
    finally { setBusy(false); }
  }
  async function download() {
    if (!formRef.current?.reportValidity()) return;
    setBusy(true); setError("");
    try {
      const text = await apiRequest<string>(`${base}/mission`, json(parameters()), client);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
      link.download = `${zone}.waypoints`; link.click(); URL.revokeObjectURL(link.href);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Mission file could not be prepared."); }
    finally { setBusy(false); }
  }
  const content = <>
    <p className="field-help">One patrol-zone loop, then return to launch. Enter the actual launch point on shore, within 5 km of the zone.</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!zones ? <>{!error && <p role="status">Loading patrol zones…</p>}<button type="button" className="button-secondary" onClick={() => setAttempt((value) => value + 1)}>Retry patrol zones</button></> : !zones.length ? <p>No patrol zones are available. Return to the lake workspace to review its setup.</p> : <form ref={formRef} className="mission-review" onSubmit={(event) => void prepare(event)} aria-busy={busy}>
      <fieldset disabled={busy} onChange={() => setPreview(null)}><legend>Mission details</legend>
        <label>Patrol zone<select name="zone_id" value={zone} required onChange={(event) => setZone(event.target.value)}>{zones.map((item) => <option key={item.zone_id} value={item.zone_id}>{item.zone_id} · {item.radius_m} m radius{item.is_proxy ? " · proxy data" : ""}</option>)}</select></label>
        <label>Home latitude<input name="home_lat" type="number" step="any" min={-90} max={90} value={latitude} required onChange={(event) => setLatitude(event.target.value)}/></label>
        <label>Home longitude<input name="home_lon" type="number" step="any" min={-180} max={180} value={longitude} required onChange={(event) => setLongitude(event.target.value)}/></label>
        <label>Altitude (m)<input name="altitude_m" type="number" step="any" min={5} max={120} value={altitude} required onChange={(event) => setAltitude(event.target.value)}/></label>
      </fieldset>
      <div className="mission-actions"><button type="submit" className="button-secondary" disabled={busy}>{busy ? "Preparing…" : "Preview mission"}</button><button type="button" className="button-secondary" disabled={busy} onClick={() => void download()}>Download .waypoints</button><button type="button" className="button-secondary" disabled={busy} onClick={() => setAttempt((value) => value + 1)}>Refresh zones</button></div>
      {preview && <section className="mission-review" aria-label="Reviewed mission"><h3>Review patrol</h3><dl><div><dt>Zone</dt><dd>{preview.result.zone_id}</dd></div><div><dt>Launch point</dt><dd>{preview.result.home.lat.toFixed(5)}, {preview.result.home.lon.toFixed(5)}</dd></div><div><dt>Altitude</dt><dd>{preview.result.altitude_m} m</dd></div><div><dt>Mission items</dt><dd>{preview.result.waypoint_count}</dd></div></dl>
        {!!preview.result.route?.length && <details><summary>Waypoint coordinates</summary><ol>{preview.result.route.map((point, index) => <li key={index}>{point.lat.toFixed(5)}, {point.lon.toFixed(5)}</li>)}</ol></details>}
        {send ? <><p className="field-help">Queue this reviewed mission for the device. Upload status will appear in the registry. Arming stays with the pilot.</p><button type="button" disabled={busy} onClick={() => void queue()}>{busy ? "Queueing…" : "Queue reviewed patrol"}</button></> : <p className="field-help">Downloading does not send anything to the drone. Review the file in Mission Planner before flight.</p>}
      </section>}
    </form>}
  </>;
  return send ? <section>{content}</section> : <details className="mission-download" onToggle={(event) => setOpen(event.currentTarget.open)}><summary>Download mission</summary>{open && content}</details>;
}

export function PatrolProgress({ droneId, stationId, client, refreshKey }: { droneId: string; stationId: string; client: SupabaseLike; refreshKey?: string | null }) {
  const [command, setCommand] = useState<PatrolCommand | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    const check = async () => {
      try {
        const result = await apiRequest<PatrolCommand | { command: null }>(`/api/stations/${encodeURIComponent(stationId)}/inventory/${encodeURIComponent(droneId)}/patrol-commands/latest`, {}, client);
        if (!current) return;
        const next = "command_id" in result ? result : null;
        setCommand(next); setFailed(false);
        if (next && ["queued", "delivered"].includes(next.status)) timer = setTimeout(() => void check(), 3000);
      } catch { if (current) setFailed(true); }
    };
    void check();
    return () => { current = false; clearTimeout(timer); };
  }, [droneId, stationId, client, refreshKey]);
  if (failed) return <p className="field-help">Patrol status unavailable. Refresh fleet to retry.</p>;
  if (!command) return null;
  const descriptions = { queued: "Queued; waiting for the device", delivered: "Received by device; waiting for upload confirmation", uploaded: "Upload confirmed by device", rejected: "Rejected by device", expired: "Expired without upload confirmation" };
  return <div className="field-help" role="status"><p>Last patrol: {descriptions[command.status]}.</p>{command.detail && <p>{command.detail}</p>}</div>;
}
