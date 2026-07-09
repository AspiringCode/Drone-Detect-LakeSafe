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
