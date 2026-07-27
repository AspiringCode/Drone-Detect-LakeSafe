import { describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "./apiClient";

const client = (token = "token") => ({ auth: { getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: token } } }), signOut: vi.fn() } });

describe("apiRequest", () => {
  it("attaches a bearer token while preserving caller headers", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { headers: { "content-type": "application/json" } }));
    await apiRequest("/api/me", { headers: { "X-Request-ID": "r1" } }, client() as never, fetcher);
    const [, init] = fetcher.mock.calls[0];
    expect(init.headers.get("Authorization")).toBe("Bearer token");
    expect(init.headers.get("X-Request-ID")).toBe("r1");
  });

  it("signs out and provides a structured error for 401", async () => {
    const auth = client();
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "expired", detail: "Session expired" }), { status: 401, headers: { "content-type": "application/json" } }));
    await expect(apiRequest("/api/me", undefined, auth as never, fetcher)).rejects.toMatchObject({ status: 401, code: "expired", message: "Session expired" } satisfies Partial<ApiError>);
    expect(auth.auth.signOut).toHaveBeenCalledOnce();
  });
});
