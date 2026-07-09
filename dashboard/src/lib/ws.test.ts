import { describe, expect, it, vi } from "vitest";
import { connectPositions } from "./ws";
import type { SimulationState } from "./types";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  closed = false;
  constructor(public url: string) {}
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
