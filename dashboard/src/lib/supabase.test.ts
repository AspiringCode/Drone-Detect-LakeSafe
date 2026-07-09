import { describe, expect, it, vi } from "vitest";
import { fetchAlerts, subscribeAlerts } from "./supabase";
import type { Alert } from "./types";

function mkAlert(): Alert {
  return {
    alert_id: "a1",
    created_at: "2026-07-06T00:00:00Z",
    location: { lat: 47.58, lon: -122.09 },
    detection_mode: "thermal-cv",
    drone_id: "d1",
    thermal_clip_ref: null,
    confirmed: true,
    source: "simulated",
    latency_ms: 100,
  };
}

describe("subscribeAlerts", () => {
  it("registers a postgres_changes listener and calls onAlert with the new row", () => {
    const alert = mkAlert();
    let handler: ((payload: { new: Alert }) => void) | null = null;

    const channel: any = {
      on: vi.fn((_event: string, _filter: unknown, cb: (payload: { new: Alert }) => void) => {
        handler = cb;
        return channel;
      }),
      subscribe: vi.fn(() => channel),
    };

    const client: any = {
      channel: vi.fn(() => channel),
      removeChannel: vi.fn(),
    };

    const onAlert = vi.fn();
    const unsubscribe = subscribeAlerts(onAlert, client);

    expect(client.channel).toHaveBeenCalled();
    handler!({ new: alert });
    expect(onAlert).toHaveBeenCalledWith(alert);

    unsubscribe();
    expect(client.removeChannel).toHaveBeenCalled();
  });
});

describe("fetchAlerts", () => {
  it("returns rows from the alerts table", async () => {
    const alert = mkAlert();
    const client: any = {
      from: vi.fn(() => ({
        select: vi.fn(() => ({
          order: vi.fn(() => Promise.resolve({ data: [alert], error: null })),
        })),
      })),
    };

    const alerts = await fetchAlerts(client);
    expect(alerts).toEqual([alert]);
  });

  it("throws when supabase returns an error", async () => {
    const client: any = {
      from: vi.fn(() => ({
        select: vi.fn(() => ({
          order: vi.fn(() => Promise.resolve({ data: null, error: new Error("boom") })),
        })),
      })),
    };

    await expect(fetchAlerts(client)).rejects.toThrow("boom");
  });
});
