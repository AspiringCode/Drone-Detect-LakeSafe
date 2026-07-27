import { describe, expect, it, vi } from "vitest";
import { connectOperationalPositions, connectPositions } from "./ws";
import type { SimulationState } from "./types";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  closed = false;
  constructor(public url: string, public protocols?: string[]) {}
  close() {
    this.closed = true;
  }
}

describe("connectPositions", () => {
  it("parses incoming JSON state and calls onState", () => {
    let created: FakeWebSocket | null = null;
    const Ctor = vi.fn((url: string) => {
      created = new FakeWebSocket(url);
      return created;
    });

    const onState = vi.fn();
    connectPositions("ws://test/ws/positions", onState, Ctor as unknown as typeof WebSocket);

    const state: SimulationState = {
      drones: [
        {
          drone_id: "d1",
          pos: { lat: 47.58, lon: -122.09 },
          battery: 0.9,
          status: "patrolling",
          assigned_zone: "z1-1",
          source: "simulated",
        },
      ],
      conflicts: [],
      t: 1.5,
    };

    created!.onmessage!({ data: JSON.stringify(state) });

    expect(onState).toHaveBeenCalledWith(state);
  });

  it("returns an unsubscribe function that closes the socket", () => {
    let created: FakeWebSocket | null = null;
    const Ctor = vi.fn((url: string) => {
      created = new FakeWebSocket(url);
      return created;
    });

    const unsubscribe = connectPositions(
      "ws://test/ws/positions",
      vi.fn(),
      Ctor as unknown as typeof WebSocket,
    );
    unsubscribe();

    expect(created!.closed).toBe(true);
  });
});

describe("connectOperationalPositions", () => {
  it("sends its bearer token only through the WebSocket subprotocol", () => {
    let created: FakeWebSocket | null = null;
    const Ctor = vi.fn((url: string, protocols: string[]) => (created = new FakeWebSocket(url, protocols)));
    const stop = connectOperationalPositions("wss://test/ws/positions", "secret-token", vi.fn(), Ctor as unknown as typeof WebSocket);
    expect(created!.url).toBe("wss://test/ws/positions");
    expect(created!.url).not.toContain("secret-token");
    expect(created!.protocols).toEqual(["lakesafe-bearer", "secret-token"]);
    stop();
  });
});
