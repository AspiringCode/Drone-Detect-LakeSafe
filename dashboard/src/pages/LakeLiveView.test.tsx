import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LakeLiveView } from "./LakeLiveView";
import { PrincipalProvider } from "../auth/PrincipalProvider";

vi.mock("../components/LakeMap", () => ({
  LakeMap: ({ lakeName, lakeCenter, stationLocation, riskmap }: { lakeName: string; lakeCenter: { lat: number; lon: number }; stationLocation?: unknown; riskmap?: { features: unknown[] } | null }) => (
    <div role="region" aria-label={`${lakeName} operator map`} data-center={`${lakeCenter.lat},${lakeCenter.lon}`} data-station={stationLocation ? "present" : "absent"} data-zones={riskmap?.features?.length ?? 0} />
  ),
}));

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const lakeClient = (metadata: unknown) => ({ auth: { getSession: async () => ({ data: { session: { access_token: "token" } } }), onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }) }, from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: metadata, error: null }) }) }) }) });
const member = (capabilities: string[]) => vi.fn().mockResolvedValue({ aal: "aal2", memberships: [{ station_id: "station", status: "active", capabilities }] });
const view = (client: unknown, request: unknown, fetcher: unknown, connectOperational: unknown = vi.fn(() => () => {})) => render(<PrincipalProvider client={client as never} request={request as never}><MemoryRouter initialEntries={["/lakes/lake-1"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={client as never} fetcher={fetcher as never} connectOperational={connectOperational as never} />} /></Routes></MemoryRouter></PrincipalProvider>);

describe("LakeLiveView", () => {
  it("shows pending stored setup before opening operational updates and supports recheck", async () => {
    let ready = false;
    const connect = vi.fn(() => () => {});
    const fetcher = vi.fn(async (url: string) => response(url.includes("setup-status") ? {setup_status:ready ? "ready" : "queued"} : url.includes("registered-drones") ? {drones:[]} : url.includes("alerts") ? [] : {}));
    view(lakeClient({name:"Lake",centroid_lat:1,centroid_lon:2,station_id:"station"}),member(["station.read"]),fetcher,connect);
    expect(await screen.findByRole("heading", {name:"Lake setup is queued"})).toBeVisible();
    expect(connect).not.toHaveBeenCalled();
    ready = true;
    fireEvent.click(screen.getByRole("button", {name:"Check setup again"}));
    await waitFor(() => expect(connect).toHaveBeenCalledOnce());
  });
  it("starts one simulated drone, adds another and prompts to regenerate zones", async () => {
    let push: (state: unknown) => void = () => {};
    const connectOperational = vi.fn((_url: string, _token: string, onState: (state: unknown) => void) => { push = onState; return () => {}; });
    const status = (zones: number, simulated: number) => response({ simulated_drones: simulated, waiting_drones: 0, real_drones_unaffected: false, zones, riskmap: { type: "FeatureCollection", features: Array.from({ length: zones }, (_, i) => i) } });
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/alerts")) return response([]);
      if (url.includes("/registered-drones")) return response({ drones: [] });
      if (url.includes("/simulation/start")) return status(4, 1);
      if (url.includes("/simulation/drones")) return status(4, 2);
      if (url.includes("/zones/regenerate")) return status(2, 2);
      return response({ type: "FeatureCollection", features: [] });
    });
    const sim = (id: string, zone: string | null) => ({ drone_id: id, pos: { lat: 47.5, lon: -122.1 }, battery: 1, status: zone ? "patrolling" : "idle", assigned_zone: zone, source: "simulated" });
    view(lakeClient({ name: "Canonical Lake", centroid_lat: 47.5, centroid_lon: -122.1, station_id: "station" }), member(["station.read", "autonomy.manage", "alert.manage"]), fetcher, connectOperational);
    expect(await screen.findByText(/Start a simulation, or assign a registered drone/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add simulated drone" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Start simulation" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Start simulation" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/api/lakes/lake-1/simulation/start"), expect.objectContaining({ method: "POST" })));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();  // no real drones, so nothing to ask
    act(() => push({ drones: [sim("lake-1-d0", "cell-0")], conflicts: [], t: 1, simulation_running: true }));
    fireEvent.click(screen.getByRole("button", { name: "Add simulated drone" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/simulation/drones"), expect.anything()));
    act(() => push({ drones: [sim("lake-1-d0", "cell-0"), sim("lake-1-d1", null)], conflicts: [], t: 2, simulation_running: true }));
    expect(screen.getByRole("status")).toHaveTextContent("A new drone is waiting ashore. Regenerate zones to give it a patrol area.");
    expect(screen.getByRole("button", { name: "Regenerate zones" })).not.toHaveClass("button-secondary");
    fireEvent.click(screen.getByRole("button", { name: "Regenerate zones" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Canonical Lake operator map" })).toHaveAttribute("data-zones", "2"));
    act(() => push({ drones: [sim("lake-1-d0", "cell-0"), sim("lake-1-d1", "cell-1")], conflicts: [], t: 3, simulation_running: true }));
    expect(screen.queryByText(/waiting ashore/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop simulation" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Simulate detection" })).toBeVisible();
  });

  it("asks whether starting a simulation should change real drones' flight paths", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/alerts")) return response([]);
      if (url.includes("/registered-drones")) return response({ drones: [{ inventory_id: "real-1", manufacturer: "Holybro", serial: "SN-1", last_heartbeat_at: null, zone_id: "cell-1" }] });
      if (url.includes("/simulation/start")) return response({ simulated_drones: 1, waiting_drones: 0, real_drones_unaffected: true, zones: 4, riskmap: { type: "FeatureCollection", features: [] } });
      return response({ type: "FeatureCollection", features: [] });
    });
    view(lakeClient({ name: "Canonical Lake", centroid_lat: 47.5, centroid_lon: -122.1, station_id: "station" }), member(["station.read", "autonomy.manage", "fleet_safety.manage"]), fetcher);
    expect(await screen.findByText("cell-1")).toBeVisible();  // the real drone's own zone
    await waitFor(() => expect(screen.getByRole("button", { name: "Start simulation" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Start simulation" }));
    expect(screen.getByRole("dialog", { name: "Change real drones’ flight paths?" })).toBeVisible();
    expect(fetcher).not.toHaveBeenCalledWith(expect.stringContaining("/simulation/start"), expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start simulation" }));
    fireEvent.click(screen.getByRole("button", { name: "Leave unaffected" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/simulation/start"), expect.objectContaining({ body: JSON.stringify({ real_drones: "keep" }) })));
  });

  it("has no eyebrow subheadings, coverage plan, source line or page source badge", async () => {
    const fetcher = vi.fn(async (url: string) => response(url.includes("/alerts") ? [] : url.includes("/registered-drones") ? { drones: [] } : {}));
    const { container } = view(lakeClient({ name: "Canonical Lake", centroid_lat: 47.5, centroid_lon: -122.1, station_id: "station" }), member(["station.read"]), fetcher);
    await screen.findByRole("heading", { level: 1, name: "Canonical Lake" });
    expect(container.querySelector(".panel-eyebrow")).toBeNull();
    expect(screen.queryByText(/coverage plan/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Source:/)).not.toBeInTheDocument();
    expect(screen.queryByText("SIMULATED")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start simulation" })).not.toBeInTheDocument();
  });

  it("lists registered real drones and shows a pushed real alert", async () => {
    let push: (state: unknown) => void = () => {};
    const connectOperational = vi.fn((_url: string, _token: string, onState: (state: unknown) => void) => { push = onState; return () => {}; });
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/alerts")) return response([]);
      if (url.includes("/registered-drones")) return response({ drones: [{ inventory_id: "d-1", manufacturer: "Holybro", serial: "SN-1", last_heartbeat_at: null }] });
      if (url.includes("/safety/status")) return response({ source: "real", autonomy: "degraded", heartbeat_age_seconds: 18, eligible: false, desired_state_version: 4, acknowledged_state_version: 3 });
      return response({});
    });
    view(lakeClient({ name: "Drone Test Field", centroid_lat: 47.592, centroid_lon: -122.032, station_id: "station" }), member(["station.read"]), fetcher, connectOperational);
    expect(await screen.findByText("awaiting heartbeat")).toBeVisible();
    expect(screen.getByText("SN-1")).toBeVisible();
    expect(await screen.findByText(/reduced real-fleet capacity/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: /real autonomy|safe return/i })).not.toBeInTheDocument();
    const alert = { alert_id: "alert-real", created_at: "2026-10-22T20:00:00Z", location: { lat: 47.592, lon: -122.032 }, detection_mode: "thermal", drone_id: "d-1", thermal_clip_ref: null, confirmed: true, source: "real", latency_ms: 0 };
    act(() => push({ drones: [{ drone_id: "d-1", pos: { lat: 47.592, lon: -122.032 }, battery: 0.9, status: "patrolling", assigned_zone: null, source: "real" }], conflicts: [], t: 1, latest_alert: alert }));
    expect(screen.queryByText("awaiting heartbeat")).not.toBeInTheDocument();
    expect(screen.getByText(/GPS: 47\.59200, -122\.03200/)).toBeVisible();
    act(()=>push({drones:[],conflicts:[],t:0,alerts:[],latest_alert:null,simulation_running:false}));
    expect(screen.getByText('No active alert.')).toBeVisible();
  });

  it.each(["returned", "thrown"])("explains a %s metadata failure instead of waiting forever", async (kind) => {
    const client = { from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => {
      if (kind === "thrown") throw new TypeError("Failed to fetch");
      return { data: null, error: { message: "permission denied" } };
    } }) }) }) };
    render(<MemoryRouter initialEntries={["/lakes/unavailable"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={client as never} />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("alert", { name: "Lake information error" })).toHaveTextContent("Lake information could not be loaded");
    expect(screen.getByRole("link", { name: "Return to lakes" })).toHaveAttribute("href", "/lakes");
  });

  it("loads the persisted identity and map center without operator access", async () => {
    const select = vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn(async () => ({ data: { name: "Pine Lake", centroid_lat: 47.587, centroid_lon: -122.052, station_id: null }, error: null })) })) }));
    const client = { auth: { getSession: vi.fn(async () => ({ data: { session: { access_token: "token" } } })), onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })) }, from: vi.fn(() => ({ select })) };
    const request = vi.fn(async () => ({ user_id: "civilian-1", aal: "aal1", account_class: "civilian", memberships: [] }));
    view(client, request, vi.fn());
    expect(await screen.findByRole("region", { name: "Pine Lake operator map" })).toHaveAttribute("data-center", "47.587,-122.052");
    expect(select).toHaveBeenCalledWith("name,centroid_lat,centroid_lon,station_id");
  });

  it("announces when registered drones cannot be loaded", async () => {
    const fetcher = vi.fn(async (url: string) => url.includes("/registered-drones") ? response({ detail: "Unavailable" }, 503) : response(url.includes("/alerts") ? [] : {}));
    view(lakeClient({ name: "Canonical Lake", centroid_lat: 47.5, centroid_lon: -122.1, station_id: "station" }), member(["station.read"]), fetcher);
    expect(await screen.findByRole("alert", { name: /operational data error/i })).toHaveTextContent(/could not be loaded/i);
  });
});
