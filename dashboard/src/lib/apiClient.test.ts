import { describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "./apiClient";

const client = (token = "token") => ({ auth: { getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: token } } }), getUser: vi.fn().mockResolvedValue({ data: { user: { id: "user-1" } }, error: null }), signOut: vi.fn() } });

describe("apiRequest", () => {
  it("attaches a bearer token while preserving caller headers", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { headers: { "content-type": "application/json" } }));
    await apiRequest("/api/me", { headers: { "X-Request-ID": "r1" } }, client() as never, fetcher);
    const [, init] = fetcher.mock.calls[0];
    expect(init.headers.get("Authorization")).toBe("Bearer token");
    expect(init.headers.get("X-Request-ID")).toBe("r1");
  });

  it("preserves a Supabase-validated session when the API returns 401", async () => {
    const auth = client();
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "expired", detail: "Session expired" }), { status: 401, headers: { "content-type": "application/json" } }));
    await expect(apiRequest("/api/me", undefined, auth as never, fetcher)).rejects.toMatchObject({ status: 401, code: "expired", message: "Session expired" } satisfies Partial<ApiError>);
    expect(auth.auth.getUser).toHaveBeenCalledOnce();
    expect(auth.auth.signOut).not.toHaveBeenCalled();
  });

  it("signs out after a 401 when Supabase also rejects the session", async () => {
    const auth = client();
    auth.auth.getUser.mockResolvedValue({ data: { user: null }, error: { message: "invalid token" } } as never);
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid bearer token" }), { status: 401, headers: { "content-type": "application/json" } }));
    await expect(apiRequest("/api/me", undefined, auth as never, fetcher)).rejects.toMatchObject({ status: 401 });
    expect(auth.auth.signOut).toHaveBeenCalledOnce();
  });
});
