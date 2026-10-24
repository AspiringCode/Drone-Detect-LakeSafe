import { describe, expect, it, vi } from "vitest";
import { changeSimulation, loadRealFleetSafetyStatus, loadRegisteredDrones, requestSafeReturn, setRealAutonomy } from "./fleetData";

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

describe("lake simulation API client", () => {
  it("posts session and zone actions to the lake and lists its registered drones", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(response({ simulated_drones: 5, zones: 4, riskmap: { type: "FeatureCollection", features: [] }, drones: [] })));
    expect((await changeSimulation("lake-1", "simulation/start", client, fetcher)).simulated_drones).toBe(5);
    expect(fetcher.mock.calls[0][0]).toContain("/api/lakes/lake-1/simulation/start");
    expect(fetcher.mock.calls[0][1].method).toBe("POST");
    await loadRegisteredDrones("lake-1", client, fetcher);
    expect(fetcher.mock.calls[1][0]).toContain("/api/lakes/lake-1/registered-drones");
  });
});
