import type { SimulationState } from "./types";

export function connectPositions(
  url: string,
  onState: (state: SimulationState) => void,
  WebSocketImpl: typeof WebSocket = WebSocket,
): () => void {
  const socket = new WebSocketImpl(url);
  socket.onmessage = (event: MessageEvent) => {
    const state = JSON.parse(event.data as string) as SimulationState;
    onState(state);
  };
  return () => socket.close();
}

/** Operational credentials are negotiated as a WebSocket subprotocol, never in the URL. */
export function connectOperationalPositions(
  url: string,
  token: string,
  onState: (state: SimulationState) => void,
  WebSocketImpl: typeof WebSocket = WebSocket,
): () => void {
  const socket = new WebSocketImpl(url, ["lakesafe-bearer", token]);
  socket.onmessage = (event: MessageEvent) => onState(JSON.parse(event.data as string) as SimulationState);
  return () => socket.close();
}
