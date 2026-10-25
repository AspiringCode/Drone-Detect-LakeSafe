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

const RECONNECT_START_MS = 1000;
const RECONNECT_MAX_MS = 15000;

/** Operational credentials are negotiated as a WebSocket subprotocol, never in the URL.
 * The API closes the socket when it restarts or the token expires, so it reopens with a fresh token. */
export function connectOperationalPositions(
  url: string,
  getToken: () => Promise<string | undefined>,
  onState: (state: SimulationState) => void,
  onConnection: (live: boolean) => void = () => {},
  WebSocketImpl: typeof WebSocket = WebSocket,
): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let delay = RECONNECT_START_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const retry = () => {
    if (stopped) return;
    onConnection(false);
    timer = setTimeout(() => void open(), delay);
    delay = Math.min(delay * 2, RECONNECT_MAX_MS);
  };
  const open = async () => {
    let token: string | undefined;
    try { token = await getToken(); } catch { return retry(); }
    if (stopped) return;
    if (!token) return retry();
    socket = new WebSocketImpl(url, `bearer.${token}`);
    socket.onopen = () => { delay = RECONNECT_START_MS; onConnection(true); };
    socket.onmessage = (event: MessageEvent) => onState(JSON.parse(event.data as string) as SimulationState);
    socket.onclose = retry;
  };
  void open();
  return () => { stopped = true; clearTimeout(timer); socket?.close(); };
}
