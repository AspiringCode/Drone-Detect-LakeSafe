import type { SupabaseLike } from "./supabase";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function messageFrom(body: unknown, fallback: string): { code: string; message: string } {
  if (typeof body === "object" && body !== null) {
    const value = body as { code?: unknown; detail?: unknown; message?: unknown };
    const message = typeof value.message === "string" ? value.message : typeof value.detail === "string" ? value.detail : fallback;
    return { code: typeof value.code === "string" ? value.code : "request_failed", message };
  }
  return { code: "request_failed", message: fallback };
}

export async function apiRequest<T>(path: string, init: RequestInit = {}, client?: SupabaseLike, fetcher: typeof fetch = fetch): Promise<T> {
  const session = client ? (await client.auth.getSession()).data.session : null;
  const headers = new Headers(init.headers);
  if (session?.access_token) headers.set("Authorization", `Bearer ${session.access_token}`);
  const response = await fetcher(`${API}${path}`, { ...init, headers });
  const contentType = response.headers.get("content-type") ?? "";
  const body: unknown = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    if (response.status === 401 && client?.auth.getUser && client.auth.signOut) {
      try {
        const { data, error } = await client.auth.getUser();
        if (error || !data.user) await client.auth.signOut();
      } catch {
        // A resource-server or network failure must not destroy a session that
        // the identity provider has not actually rejected.
      }
    }
    const parsed = messageFrom(body, `Request failed (${response.status})`);
    throw new ApiError(response.status, parsed.code, parsed.message);
  }
  return body as T;
}
