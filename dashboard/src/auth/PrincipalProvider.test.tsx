import { act, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import { PrincipalProvider, usePrincipal } from "./PrincipalProvider";

function Probe({ onMount }: { onMount: () => void }) {
  const { principal, loading } = usePrincipal();
  if (loading) return <p>loading</p>;
  return <Mounted name={principal?.user_id ?? "none"} onMount={onMount} />;
}
function Mounted({ name, onMount }: { name: string; onMount: () => void }) {
  useEffect(onMount, []);
  return <p>{name}</p>;
}

describe("PrincipalProvider", () => {
  it("keeps signed-in pages mounted when Supabase re-emits an auth event", async () => {
    let emit = () => {};
    const client = { auth: {
      getSession: async () => ({ data: { session: { access_token: "t" } } }),
      onAuthStateChange: (listener: () => void) => { emit = listener; return { data: { subscription: { unsubscribe: vi.fn() } } }; },
    } };
    let finishRefresh = () => {};
    const request = vi.fn()
      .mockResolvedValueOnce({ user_id: "admin", memberships: [] })
      .mockImplementationOnce(() => new Promise((resolve) => { finishRefresh = () => resolve({ user_id: "admin", memberships: [] }); }));
    const onMount = vi.fn();
    render(<PrincipalProvider client={client as never} request={request}><Probe onMount={onMount} /></PrincipalProvider>);
    await screen.findByText("admin");
    await act(async () => { emit(); });
    expect(request).toHaveBeenCalledTimes(2);
    expect(screen.getByText("admin")).toBeInTheDocument();
    await act(async () => { finishRefresh(); });
    expect(onMount).toHaveBeenCalledTimes(1);
  });
});
