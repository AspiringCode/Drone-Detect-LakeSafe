import { describe, expect, it, vi } from "vitest";
import { loadRealFleetSafetyStatus, loadZonePlan, requestSafeReturn, setRealAutonomy } from "./fleetData";

const client = { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: "token" } } }) } } as never;
const response = (body: unknown) => new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } });

describe("real fleet safety API client", () => {
  it("loads only station-scoped real safety status", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ source: "real", autonomy: "degraded", heartbeat_age_seconds: 16, eligible: false, desired_state_version: 8, acknowledged_state_version: 6 }));
    const status = await loadRealFleetSafetyStatus("station-1", "lake-1", client, fetcher);
    expect(status).toMatchObject({ source: "real", realAutonomy: "degraded", heartbeatAgeSeconds: 16, desiredStateVersion: 8, acknowledgedStateVersion: 6 });
    expect(fetcher.mock.calls[0][0]).toContain("/api/stations/station-1/lakes/lake-1/safety/status");
  });

  it("sends a reason but never flight instructions with safety actions", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(response({ autonomy: "pending_ack" })));
    await setRealAutonomy("station-1", "lake-1", true, "Shift handoff", client, fetcher);
    const [, autonomyInit] = fetcher.mock.calls[0];
    expect(JSON.parse(autonomyInit.body)).toEqual({ enabled: true, reason: "Shift handoff" });
    await requestSafeReturn("station-1", "lake-1", "Weather", client, fetcher);
    const [, returnInit] = fetcher.mock.calls[1];
    expect(JSON.parse(returnInit.body)).toEqual({ reason: "Weather" });
  });
});

describe("zone plan API client", () => {
  it("derives priority, proxy-priority, and baseline coverage counts with attribution", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({
      plan_id: "plan-1", snapshot_id: "snapshot-1", algorithm_version: "risk-zone-v1",
      source_fresh_through: "2026-08-18T00:00:00Z", activity_data_unavailable: false,
      source_attribution: ["King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites"],
      cells: [
        { kind: "hotspot", metadata: { is_proxy: true } },
        { kind: "hotspot", metadata: { is_proxy: false } },
        { kind: "coverage", metadata: { is_proxy: true } },
        { kind: "fallback", metadata: { is_proxy: true } },
      ],
    }));

    const plan = await loadZonePlan("station-1", "lake-pine", client, fetcher);

    expect(plan).toMatchObject({
      priorityCells: 2,
      proxyPriorityCells: 1,
      coverageCells: 1,
      sourceAttribution: ["King County Open Data — Freshwater Swim Beach Data and Water Quality Monitoring Sites"],
    });
  });
});
