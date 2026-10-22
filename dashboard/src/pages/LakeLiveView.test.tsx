import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LakeLiveView } from "./LakeLiveView";
import { PrincipalProvider } from "../auth/PrincipalProvider";

vi.mock("../components/LakeMap", () => ({
  LakeMap: ({ lakeName, lakeCenter }: { lakeName: string; lakeCenter: { lat: number; lon: number } }) => (
    <div role="region" aria-label={`${lakeName} operator map`} data-center={`${lakeCenter.lat},${lakeCenter.lon}`} />
  ),
}));

const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("LakeLiveView autonomous plan state", () => {
  it.each([
    ["lake-pine", "Pine Lake", 47.587, -122.052],
    ["lake-beaver", "Beaver Lake", 47.585, -121.997],
  ])("loads the persisted identity and map center for %s", async (lakeId, lakeName, centroidLat, centroidLon) => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/riskmap")) return response({ type: "FeatureCollection", features: [] });
      if (url.includes("/alerts")) return response([]);
      return response({});
    }) as unknown as typeof fetch;
    const select = vi.fn(() => ({
      eq: vi.fn(() => ({
        maybeSingle: vi.fn(async () => ({
          data: { name: lakeName, centroid_lat: centroidLat, centroid_lon: centroidLon, station_id: null, drone_inventory_cap: 5, organizations: { station_lat: 47.6, station_lon: -122.1 } },
          error: null,
        })),
      })),
    }));
    const client = {
      auth: {
        getSession: vi.fn(async () => ({ data: { session: { access_token: "token" } } })),
        onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      },
      from: vi.fn(() => ({ select })),
    } as never;
    const request = vi.fn(async () => ({
      user_id: "civilian-1", email: "civilian@example.com", aal: "aal1", account_class: "civilian",
      verification_status: "not_started", reviewer: false, memberships: [],
    }));

    render(<PrincipalProvider client={client} request={request as never}><MemoryRouter initialEntries={[`/lakes/${lakeId}`]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={client} fetcher={fetcher} />} /></Routes></MemoryRouter></PrincipalProvider>);

    expect(await screen.findByRole("heading", { name: lakeName })).toBeVisible();
    expect(await screen.findByRole("region", { name: `${lakeName} operator map` })).toHaveAttribute("data-center", `${centroidLat},${centroidLon}`);
    expect(select).toHaveBeenCalledWith(expect.stringContaining("centroid_lat,centroid_lon"));
    expect(screen.queryByText("Live lake")).not.toBeInTheDocument();
  });

  it("shows real fleet status to a station viewer without safety controls", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/riskmap")) return response({ type: "FeatureCollection", features: [] });
      if (url.includes("/alerts")) return response([]);
      if (url.includes("/zone-plan")) return response({ plan_id: "plan-7", snapshot_id: "snapshot-1", algorithm_version: "risk-zone-v1", source_fresh_through: null, cells: [] });
      if (url.includes("/fleet")) return response({ drones: [] });
      if (url.includes("/safety/status")) return response({ source: "real", autonomy: "degraded", heartbeat_age_seconds: 18, eligible: false, desired_state_version: 4, acknowledged_state_version: 3 });
      return response({});
    }) as unknown as typeof fetch;
    const client = { auth: { getSession: vi.fn(async () => ({ data: { session: { access_token: "token" } } })), onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })) }, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn(async () => ({ data: { station_id: "station-1", drone_inventory_cap: 5, organizations: { station_lat: 47.6, station_lon: -122.1 } } })) })) })) })) } as never;
    const request = vi.fn(async () => ({ user_id: "user-1", email: "officer@example.gov", aal: "aal2", account_class: "officer", verification_status: "verified", reviewer: false, memberships: [{ station_id: "station-1", station_name: "Station", status: "active", roles: ["viewer"], capabilities: ["station.read"] }] }));
    render(<PrincipalProvider client={client} request={request as never}><MemoryRouter initialEntries={["/lakes/lake-1"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={client} accessToken="token" fetcher={fetcher} />} /></Routes></MemoryRouter></PrincipalProvider>);
    expect(await screen.findByText(/reduced real-fleet capacity/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: /real autonomy|safe return/i })).not.toBeInTheDocument();
  });

  it("displays the active plan summary and freshness from station-scoped APIs", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/riskmap")) return response({ type: "FeatureCollection", features: [] });
      if (url.includes("/alerts")) return response([]);
      if (url.includes("/zone-plan")) return response({ plan_id: "plan-7", algorithm_version: "risk-zone-v1", source_fresh_through: "2026-07-29T12:00:00Z", cells: [{ kind: "hotspot" }, { kind: "coverage" }] });
      if (url.includes("/fleet")) return response({ drones: [] });
      return response({});
    }) as unknown as typeof fetch;
    const client = { auth: { getSession: vi.fn(async () => ({ data: { session: { access_token: "token" } } })), onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })) }, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn(async () => ({ data: { station_id: "station-1", drone_inventory_cap: 5, organizations: { station_lat: 47.6, station_lon: -122.1 } } })) })) })) })) } as never;
    const request = vi.fn(async () => ({ user_id: "user-1", email: "officer@example.gov", aal: "aal2", account_class: "officer", verification_status: "verified", reviewer: false, memberships: [{ station_id: "station-1", station_name: "Station", status: "active", roles: ["safety_supervisor"], capabilities: ["station.read"] }] }));
    render(<PrincipalProvider client={client} request={request as never}><MemoryRouter initialEntries={["/lakes/lake-1"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={client} accessToken="token" fetcher={fetcher} />} /></Routes></MemoryRouter></PrincipalProvider>);
    expect(await screen.findByText("Active coverage plan")).toBeVisible();
    expect(screen.getByText("risk-zone-v1")).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/api/stations/station-1/lakes/lake-1/zone-plan"), expect.anything());
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/lake-1/riskmap"), expect.objectContaining({ headers: { Authorization: "Bearer token" } }));
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/lake-1/alerts"), expect.objectContaining({ headers: { Authorization: "Bearer token" } }));
  });

  it("announces a station-scoped plan fetch failure", async () => {
    const fetcher = vi.fn(async (url: string) => {
      if (url.includes("/riskmap")) return response({ type: "FeatureCollection", features: [] });
      if (url.includes("/alerts")) return response([]);
      if (url.includes("/zone-plan") || url.includes("/fleet")) return response({ detail: "Unavailable" }, 503);
      return response({});
    }) as unknown as typeof fetch;
    const client = { auth: { getSession: vi.fn(async () => ({ data: { session: { access_token: "token" } } })), onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })) }, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: vi.fn(async () => ({ data: { station_id: "station-1", drone_inventory_cap: 5, organizations: { station_lat: 47.6, station_lon: -122.1 } } })) })) })) })) } as never;
    const request = vi.fn(async () => ({ user_id: "user-1", email: "officer@example.gov", aal: "aal2", account_class: "officer", verification_status: "verified", reviewer: false, memberships: [{ station_id: "station-1", station_name: "Station", status: "active", roles: ["viewer"], capabilities: ["station.read"] }] }));
    render(<PrincipalProvider client={client} request={request as never}><MemoryRouter initialEntries={["/lakes/lake-1"]}><Routes><Route path="/lakes/:lakeId" element={<LakeLiveView client={client} accessToken="token" fetcher={fetcher} />} /></Routes></MemoryRouter></PrincipalProvider>);
    expect(await screen.findByRole("alert", { name: /operational data error/i })).toHaveTextContent(/could not be loaded/i);
  });
});
