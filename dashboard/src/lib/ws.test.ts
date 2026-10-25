import { describe, expect, it, vi } from "vitest";
import { connectOperationalPositions, connectPositions } from "./ws";
import type { SimulationState } from "./types";

class FakeWebSocket {
  onmessage: ((event: { data: string }) => void) | null = null;
  closed = false;
  constructor(public url: string, public protocols?: string | string[]) {}
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
  type Socket = FakeWebSocket & { onclose: (() => void) | null; onopen: (() => void) | null };
  const sockets: Socket[] = [];
  const Ctor = vi.fn((url: string, protocols: string) => { const socket = new FakeWebSocket(url, protocols) as Socket; sockets.push(socket); return socket; }) as unknown as typeof WebSocket;

  it("sends its bearer token only through the WebSocket subprotocol", async () => {
    sockets.length = 0;
    const stop = connectOperationalPositions("wss://test/ws/positions", async () => "secret-token", vi.fn(), undefined, Ctor);
    await vi.waitFor(() => expect(sockets).toHaveLength(1));
    expect(sockets[0].url).toBe("wss://test/ws/positions");
    expect(sockets[0].url).not.toContain("secret-token");
    expect(sockets[0].protocols).toBe("bearer.secret-token");
    stop();
  });

  it("reopens with a fresh token after the API closes it, and stops for good when unsubscribed", async () => {
    vi.useFakeTimers();
    sockets.length = 0;
    const tokens = ["first", "renewed"];
    const onConnection = vi.fn();
    const stop = connectOperationalPositions("wss://test/ws", async () => tokens.shift(), vi.fn(), onConnection, Ctor);
    await vi.waitFor(() => expect(sockets).toHaveLength(1));
    sockets[0].onopen!();
    expect(onConnection).toHaveBeenLastCalledWith(true);
    sockets[0].onclose!();  // API restart or expired token
    expect(onConnection).toHaveBeenLastCalledWith(false);
    await vi.advanceTimersByTimeAsync(1000);
    expect(sockets).toHaveLength(2);
    expect(sockets[1].protocols).toBe("bearer.renewed");
    stop();
    expect(sockets[1].closed).toBe(true);
    sockets[1].onclose!();
    await vi.advanceTimersByTimeAsync(60000);
    expect(sockets).toHaveLength(2);
    vi.useRealTimers();
  });
});
